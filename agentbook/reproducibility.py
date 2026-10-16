"""Reproducibility: record what a run depended on, and replay it from its trace.

A trace written by `Tracer` holds every model output and every tool result,
which is enough to run the agent again without the model and, if we want,
without the tools:

    events = last_run(load_trace("traces/failure_trace.jsonl"))
    result = replay_run(events)                            # model and tools replayed
    result = replay_run(events, tools=ToolRegistry(registry_tools()))  # tools re-run live
    diff_traces(events, load_trace(new_path))              # [] when nothing changed

Replaying both reproduces the run exactly. Replaying the model against live
tools answers a different question: would the same decisions have seen the
same data today? A difference there means the registry (or a tool) changed.

`run_metadata` collects what a methods section needs: package versions,
model name and settings, a hash of the tool specs, and the registry's git
commit or, for a directory without git, a fingerprint of its data files.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from .loop import DEFAULT_SYSTEM, AgentResult, run_agent
from .models import FakeModel, ModelResponse, Usage, tool_result_block

# ------------------------------------------------------------------ metadata


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def specs_hash(specs: list[dict]) -> str:
    """A short hash of the tool specs: changes whenever a name, description or schema does."""
    return hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()[:12]


def git_commit(path: str | Path) -> str | None:
    """The git commit checked out at `path` (with '+dirty' if there are local changes)."""
    try:
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", "registry"],
                               capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return head + ("+dirty" if dirty else "")


def data_fingerprint(root: str | Path) -> str:
    """A hash of the registry's jsonl files and the list of card files with their sizes.

    For directories that are not git checkouts, such as the bundled snapshot.
    """
    root = Path(root)
    h = hashlib.sha256()
    models = root / "registry" / "models"
    for path in sorted(models.glob("*.jsonl")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    for path in sorted((models / "cards").rglob("*.yaml")):
        h.update(f"{path.relative_to(root)}:{path.stat().st_size}\n".encode())
    return h.hexdigest()[:12]


def run_metadata(model: Any = None, tools: Any = None, registry_root: str | Path | None = None,
                 **settings: Any) -> dict:
    """What a run depended on, as one dict to log before the run starts.

    `settings` is for anything else worth recording (temperature, effort,
    max_steps, the prompt version).
    """
    info: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
        "packages": {p: _version(p) for p in ("agentbook", "anthropic", "openai", "pyyaml",
                                              "jsonschema") if _version(p)},
        "script": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else None,
    }
    if model is not None:
        info["model_class"] = type(model).__name__
        info["model"] = getattr(model, "model", None) or getattr(model, "name", None)
        extra = getattr(model, "create_kwargs", None)
        if extra:
            info["model_kwargs"] = extra
    if tools is not None:
        specs = tools.specs()
        info["tools"] = [s["name"] for s in specs]
        info["tool_specs_sha256"] = specs_hash(specs)
    if registry_root is not None:
        info["registry_dir"] = _shareable_path(registry_root)
        info["registry_commit"] = git_commit(registry_root)
        info["registry_fingerprint"] = data_fingerprint(registry_root)
    info.update(settings)
    return info


# ------------------------------------------------------------------ replay


class ReplayMismatch(RuntimeError):
    """A replayed run asked for a tool call the recorded run did not make."""


def replay_model(events: list[dict], name: str = "replay") -> FakeModel:
    """A FakeModel that returns the recorded model outputs of one run, in order.

    Token counts and the model name are the recorded ones, so budgets and
    cost estimates come out as they did in the original run.
    """
    script = [ModelResponse(e["output"], e["stop_reason"],
                            Usage(e["input_tokens"], e["output_tokens"]),
                            e.get("model") or name)
              for e in events if e["event"] == "model_call"]
    return FakeModel(script, name=name)


class RecordedTools:
    """Serves the recorded tool results of one run instead of running tools.

    Has the `specs()` and `run()` methods that `run_agent` needs. A request
    that does not match the recording (different id, tool or arguments)
    raises ReplayMismatch rather than guessing.
    """

    def __init__(self, events: list[dict]):
        self.calls = {e["tool_use_id"]: e for e in events if e["event"] == "tool_call"}
        start = next((e for e in events if e["event"] == "run_start"), {})
        self.names = start.get("tools") or sorted({e["name"] for e in self.calls.values()})
        self.used: list[str] = []

    def specs(self) -> list[dict]:
        return [{"name": n, "description": "(replayed from a trace)",
                 "input_schema": {"type": "object"}} for n in self.names]

    def run(self, block: dict) -> dict:
        recorded = self.calls.get(block["id"])
        if recorded is None or recorded["name"] != block["name"] or \
                json.dumps(recorded["input"], sort_keys=True) != json.dumps(block["input"],
                                                                            sort_keys=True):
            raise ReplayMismatch(f"no recorded result for {block['name']}({block['input']}) "
                                 f"with id {block['id']}")
        self.used.append(block["id"])
        return tool_result_block(block["id"], recorded["output"], recorded["is_error"])


def replay_run(events: list[dict], tools: Any = None, tracer=None, **kwargs: Any) -> AgentResult:
    """Run the loop again from a trace of one run.

    The model is always replayed. With `tools=None` the tool results are
    replayed too and the run is reproduced exactly; pass a real ToolRegistry
    to re-execute the tools against today's data.
    """
    start = next(e for e in events if e["event"] == "run_start")
    n_calls = sum(e["event"] == "model_call" for e in events)
    kwargs.setdefault("max_steps", max(n_calls, 1))
    return run_agent(replay_model(events), tools if tools is not None else RecordedTools(events),
                     start["task"], system=start.get("system", DEFAULT_SYSTEM),
                     tracer=tracer, **kwargs)


VOLATILE = {"run_id", "ts", "ms"}


def diff_traces(a: list[dict], b: list[dict], ignore: set[str] = VOLATILE) -> list[str]:
    """Differences between two runs' events, ignoring ids, timestamps and timings.

    Returns human-readable lines; an empty list means the runs match.
    """
    def core(events):
        return [{k: v for k, v in e.items() if k not in ignore} for e in events
                if e["event"] in ("run_start", "model_call", "tool_call", "run_end")]
    ea, eb = core(a), core(b)
    diffs = []
    for i, (x, y) in enumerate(zip(ea, eb)):
        for key in sorted(set(x) | set(y)):
            if x.get(key) != y.get(key):
                where = f"event {i} ({x.get('event')}"
                where += f" {x['name']})" if "name" in x else ")"
                va, vb = _first_difference(x.get(key), y.get(key))
                diffs.append(f"{where}: {key} differs: {va} != {vb}")
    if len(ea) != len(eb):
        diffs.append(f"number of events differs: {len(ea)} != {len(eb)}")
    return diffs


def _first_difference(a: Any, b: Any, width: int = 30) -> tuple[str, str]:
    """Short excerpts of two values around the first character where they differ."""
    ta = " ".join((a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)).split())
    tb = " ".join((b if isinstance(b, str) else json.dumps(b, ensure_ascii=False)).split())
    i = next((k for k, (ca, cb) in enumerate(zip(ta, tb)) if ca != cb), min(len(ta), len(tb)))
    lo = max(0, i - width)
    cut = lambda t: ("..." if lo else "") + t[lo:i + width] + ("..." if i + width < len(t) else "")
    return cut(ta), cut(tb)


def _shareable_path(path: str | Path) -> str:
    """A path safe to keep in a shared trace: relative to the repo when inside it, else with ~."""
    path = Path(path).resolve()
    repo = Path(__file__).resolve().parents[1]
    if path.is_relative_to(repo):
        return str(path.relative_to(repo))
    home = Path.home()
    return "~/" + str(path.relative_to(home)) if path.is_relative_to(home) else str(path)
