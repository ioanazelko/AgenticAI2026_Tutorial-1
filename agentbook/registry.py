"""Tools over DarkMatterFM-Registry, read in place from REGISTRY_DIR.

REGISTRY_DIR is a clone of https://github.com/ioanazelko/darkmatterfm-registry
(or the bundled snapshot in data/registry_snapshot, the default). Layout:

    registry/models/cards/<family>/<paper>/<model_id>.yaml
    registry/models/capability_gaps_full.jsonl
    registry/models/capability_gap_roadmap.jsonl
    registry/models/ranking_full_ranked.jsonl
    registry/schemas/*.schema.yaml
    scripts/validate_schema.py

Every result carries provenance (file and arXiv id) and the status line
"machine-extracted, not expert-verified". Tools raise ToolError with a
message the model can act on when something is not available.

Use the module-level functions (search_models, get_card_section, ...) for
the default registry, or a Registry object for a specific directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .tools import Tool, ToolError, truncate

CODE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = CODE_DIR / "data" / "registry_snapshot"
STATUS = "machine-extracted, not expert-verified"
INDEX_VERSION = 1
STOPWORDS = {"in", "of", "the", "and", "or", "for", "with", "to", "a", "an", "on", "by", "at", "dark", "matter", "model", "models"}

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def registry_dir() -> Path:
    """REGISTRY_DIR from the environment, or the bundled snapshot."""
    return Path(os.environ.get("REGISTRY_DIR", SNAPSHOT_DIR)).expanduser().resolve()


def arxiv_id(paper_id: str) -> str:
    """'2305_06364' -> '2305.06364'; 'hep-ph9901234' -> 'hep-ph/9901234'."""
    m = re.fullmatch(r"([a-z\-]+)(\d{7})", paper_id)
    return f"{m.group(1)}/{m.group(2)}" if m else paper_id.replace("_", ".")


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Registry:
    """One registry directory: a cached index plus lazily loaded jsonl files."""

    def __init__(self, root: str | Path | None = None, cache_dir: str | Path | None = None):
        self.root = Path(root).expanduser().resolve() if root else registry_dir()
        self.models_dir = self.root / "registry" / "models"
        self.cards_dir = self.models_dir / "cards"
        self.schemas_dir = self.root / "registry" / "schemas"
        if not self.cards_dir.is_dir():
            raise FileNotFoundError(f"No cards under {self.cards_dir}. Set REGISTRY_DIR to a "
                                    "clone of darkmatterfm-registry.")
        cache = cache_dir or os.environ.get("AGENTBOOK_CACHE", CODE_DIR / ".cache")
        key = hashlib.sha1(str(self.root).encode()).hexdigest()[:12]
        self.index_path = Path(cache) / f"index_{key}.json"
        self._index = self._gaps = self._themes = self._ranking = None
        self._validators: dict = {}

    # ---------------------------------------------------------------- index

    @property
    def index(self) -> dict[str, dict]:
        """model_id -> {path, name, family, arxiv, enriched, summary, aliases, observables}."""
        if self._index is None:
            self._index = self._load_or_build_index()
        return self._index

    def _load_or_build_index(self) -> dict[str, dict]:
        files = sorted(self.cards_dir.rglob("*.yaml"))
        # Rebuild when a card is added, removed or edited (count or newest mtime changes).
        mtime = max((p.stat().st_mtime_ns for p in files), default=0)
        if self.index_path.exists():
            try:
                cached = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # unreadable: rebuild
                cached = {}
            if (cached.get("version") == INDEX_VERSION and cached.get("n_files") == len(files)
                    and cached.get("max_mtime_ns") == mtime):
                return cached["models"]
        models = {}
        for path in files:
            card = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
            models[card["model_id"]] = self._index_entry(path, card)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_name(f"{self.index_path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(
            {"version": INDEX_VERSION, "root": str(self.root), "n_files": len(files),
             "max_mtime_ns": mtime, "models": models}), encoding="utf-8")
        os.replace(tmp, self.index_path)  # atomic: a concurrent reader never sees half a file
        return models

    def _index_entry(self, path: Path, card: dict) -> dict:
        identity = card.get("identity") or {}
        source = card.get("_source") or {}
        return {
            "path": str(path.relative_to(self.root)),
            "name": identity.get("name", ""),
            "family": identity.get("family", ""),
            "kind": identity.get("model_kind", ""),
            "aliases": identity.get("aliases") or [],
            "summary": identity.get("short_description") or "",
            "arxiv": arxiv_id(str(source.get("paper_id", ""))),
            "enriched": bool(source.get("enriched")),
            "observables": [[o.get("id"), o.get("channel")] for o in card.get("observables") or []],
        }

    def entry(self, model_id: str) -> dict:
        """The index entry for a model, or a ToolError that suggests how to find the ID."""
        if model_id not in self.index:
            raise ToolError(f"Unknown model_id '{model_id}'. Use search_models to find valid IDs.")
        return self.index[model_id]

    def load_card(self, model_id: str) -> dict:
        """The full card as a dict (envelope keys starting with '_' included)."""
        path = self.root / self.entry(model_id)["path"]
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)

    def provenance(self, model_id: str) -> dict:
        e = self.entry(model_id)
        return {"file": e["path"], "arxiv": e["arxiv"], "status": STATUS}

    # ---------------------------------------------------------- jsonl files

    @property
    def gaps(self) -> dict[str, dict]:
        """model_id -> record from capability_gaps_full.jsonl."""
        if self._gaps is None:
            rows = _read_jsonl(self.models_dir / "capability_gaps_full.jsonl")
            self._gaps = {r["model_id"]: r for r in rows}
        return self._gaps

    @property
    def roadmap(self) -> list[dict]:
        """Rows of capability_gap_roadmap.jsonl (one per gap type and theme)."""
        return _read_jsonl(self.models_dir / "capability_gap_roadmap.jsonl")

    def theme(self, model_id: str, gap: dict) -> str | None:
        """The roadmap's capability theme for one gap entry, if it has one."""
        if self._themes is None:
            self._themes = {(m["model_id"], m["description"]): row["theme"]
                            for row in self.roadmap for m in row["members"]}
        return self._themes.get((model_id, gap["description"]))

    def priority(self, model_id: str) -> float | None:
        """adjusted_priority_score from ranking_full_ranked.jsonl."""
        if self._ranking is None:
            rows = _read_jsonl(self.models_dir / "ranking_full_ranked.jsonl")
            self._ranking = {r["model_id"]: r["triage"].get("adjusted_priority_score")
                             for r in rows}
        return self._ranking.get(model_id)

    # ---------------------------------------------------------------- tools

    def search_models(self, query: str, family: str | None = None, limit: int = 10,
                      enriched_only: bool = False) -> dict:
        """Rank cards by how many query words appear in name, aliases, family and summary."""
        words = [w for w in re.split(r"[^\w]+", query.lower()) if len(w) > 1 and w not in STOPWORDS]
        hits = []
        for model_id, e in self.index.items():
            if (family and e["family"] != family) or (enriched_only and not e["enriched"]):
                continue
            score = _score(words, e, model_id)
            if score > 0 or not words:
                hits.append((-score, model_id))
        hits.sort()
        return {
            "query": query, "total_matches": len(hits),
            "models": [self._hit(mid) for _, mid in hits[:limit]],
            "status": STATUS,
        }

    def _hit(self, model_id: str) -> dict:
        e = self.index[model_id]
        return {"model_id": model_id, "name": e["name"], "family": e["family"],
                "enriched": e["enriched"], "summary": truncate_line(e["summary"], 160),
                "arxiv": e["arxiv"], "file": e["path"]}

    def get_card_section(self, model_id: str, section: str, max_chars: int = 6000) -> dict:
        """One top-level section of a card as YAML, with warnings and provenance."""
        card = self.load_card(model_id)
        if section == "capability_gaps":
            raise ToolError("capability_gaps are not stored in the card; use get_gaps.")
        if section not in card or section.startswith("_"):
            available = [k for k in card if not k.startswith("_")]
            why = "" if self.index[model_id]["enriched"] else " (this card is not enriched)"
            raise ToolError(f"Section '{section}' is not available for {model_id}{why}; "
                            f"available sections: {', '.join(available)}")
        text = yaml.safe_dump(card[section], sort_keys=False, allow_unicode=True, width=100)
        return {
            "model_id": model_id, "section": section,
            "content": truncate(text, max_chars),
            "warnings": _warnings(card),
            "review_status": (card.get("robustness") or {}).get("validation_status"),
            "provenance": self.provenance(model_id),
        }

    def get_card(self, model_id: str) -> str:
        """The whole card as YAML. Deliberately wasteful: 11 to 39 KB per card."""
        return (self.root / self.entry(model_id)["path"]).read_text(encoding="utf-8")

    def get_gaps(self, model_id: str) -> dict:
        """Capability gaps for one enriched model, each with its theme and the
        channels of the observables it blocks."""
        entry = self.entry(model_id)
        record = self.gaps.get(model_id)
        if record is None:
            raise ToolError(f"No capability-gap annotation for {model_id}: only enriched cards "
                            "(2,004 in the full registry) have one. Try get_card_section with "
                            "section 'associated_code' or 'robustness' instead.")
        channel = dict(entry["observables"])
        gaps = []
        for g in record["capability_gaps"].get("gaps") or []:
            gaps.append({
                "id": g["id"], "gap_type": g["gap_type"], "theme": self.theme(model_id, g),
                "severity": g["severity"], "estimated_effort": g.get("estimated_effort"),
                "blocking_observables": [{"id": o, "channel": channel.get(o)}
                                         for o in g.get("blocking_observables") or []],
                "description": g["description"],
                "proposed_resolution": g.get("proposed_resolution"),
            })
        steps = [s["status"] for s in record.get("route_step_status") or []]
        return {
            "model_id": model_id, "name": entry["name"],
            "priority_score": self.priority(model_id),
            "route_steps": {s: steps.count(s) for s in sorted(set(steps))},
            "gaps": gaps,
            "provenance": self.provenance(model_id) | {
                "gaps_file": "registry/models/capability_gaps_full.jsonl"},
        }

    def find_models_by_observable(self, channel: str, limit: int = 50, offset: int = 0) -> dict:
        """Enriched models with at least one observable in `channel` (e.g. 'lyman_alpha')."""
        valid = self.observable_channels()
        if channel not in valid:
            raise ToolError(f"Unknown channel '{channel}'. Valid channels: {', '.join(valid)}")
        matches = [(mid, [oid for oid, ch in e["observables"] if ch == channel])
                   for mid, e in sorted(self.index.items())]
        matches = [(mid, ids) for mid, ids in matches if ids]
        page = matches[offset: offset + limit]
        return {
            "channel": channel, "total": len(matches), "offset": offset,
            "next_offset": offset + limit if offset + limit < len(matches) else None,
            "models": [{"model_id": mid, "name": self.index[mid]["name"],
                        "family": self.index[mid]["family"], "arxiv": self.index[mid]["arxiv"],
                        "observables": ids} for mid, ids in page],
            "status": STATUS,
        }

    def observable_channels(self) -> list[str]:
        """The channel enum from observable.schema.yaml."""
        schema = yaml.safe_load((self.schemas_dir / "observable.schema.yaml").read_text())
        return _find_enum(schema, "channel")

    def validate_card(self, yaml_text: str, section: str | None = None) -> dict:
        """Validate a card (or one section of a card) against the registry's schemas,
        using the registry's own scripts/validate_schema.py."""
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return {"valid": False, "n_errors": 1, "errors": [f"YAML parse error: {e}"]}
        if isinstance(data, dict) and section is None:
            data = {k: v for k, v in data.items() if not k.startswith("_")}
        errors = sorted(self._validator(section).iter_errors(data), key=lambda e: list(e.path))
        messages = [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
                    for e in errors]
        return {"valid": not errors, "n_errors": len(errors), "errors": messages[:20],
                "checked_against": f"bsm_model.schema.yaml{'#/properties/' + section if section else ''}"}

    def _validator(self, section: str | None):
        if section not in self._validators:
            from jsonschema import Draft202012Validator
            script = _load_validate_script(self.root / "scripts" / "validate_schema.py")
            schema, registry = script.build_registry(self.schemas_dir)
            if section is not None:
                if section not in schema["properties"]:
                    raise ToolError(f"Unknown section '{section}'. Valid sections: "
                                    f"{', '.join(schema['properties'])}")
                schema = {"$ref": f"{schema['$id']}#/properties/{section}"}
            self._validators[section] = Draft202012Validator(schema, registry=registry)
        return self._validators[section]

    def section_names(self) -> list[str]:
        """The 31 top-level sections defined by bsm_model.schema.yaml."""
        schema = yaml.safe_load((self.schemas_dir / "bsm_model.schema.yaml").read_text())
        return list(schema["properties"])


# ---------------------------------------------------------------- helpers


def _score(words: list[str], e: dict, model_id: str) -> int:
    strong = _words(" ".join([e["name"], *e["aliases"]]))
    medium = _words(f"{e['family']} {model_id}")
    weak = _words(e["summary"])
    return sum(3 * _has(strong, w) + 2 * _has(medium, w) + _has(weak, w) for w in words)


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^\w]+", text.lower()) if w}


def _has(words: set[str], w: str) -> bool:
    """Whole-word match; words of 4+ letters also match as a prefix ('neutrino' -> 'neutrinos').
    Plain substring matching made 'in' match almost every card."""
    return w in words or (len(w) >= 4 and any(x.startswith(w) for x in words))


def truncate_line(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _warnings(card: dict) -> list[dict]:
    warnings = (card.get("agent_failure_modes") or {}).get("warnings") or []
    return [{"id": w.get("id"), "severity": w.get("severity"), "warning": w.get("warning")}
            for w in warnings]


def _find_enum(schema, key: str) -> list[str]:
    """Find the enum of the first property called `key` anywhere in a schema."""
    if isinstance(schema, dict):
        props = schema.get("properties") or {}
        if key in props and "enum" in props[key]:
            return props[key]["enum"]
        children = schema.values()
    elif isinstance(schema, list):
        children = schema
    else:
        return []
    for child in children:
        found = _find_enum(child, key)
        if found:
            return found
    return []


@lru_cache(maxsize=4)
def _load_validate_script(path: Path):
    """Import the registry's own validate_schema.py so we use exactly its logic."""
    spec = importlib.util.spec_from_file_location("registry_validate_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------ default registry + tools


@lru_cache(maxsize=4)
def _registry_for(root: str) -> Registry:
    return Registry(root)


def default_registry() -> Registry:
    """The Registry for REGISTRY_DIR (or the snapshot), created once."""
    return _registry_for(str(registry_dir()))


def search_models(query: str, family: str | None = None, limit: int = 10,
                  enriched_only: bool = False) -> dict:
    return default_registry().search_models(query, family, limit, enriched_only)


def get_card_section(model_id: str, section: str) -> dict:
    return default_registry().get_card_section(model_id, section)


def get_card(model_id: str) -> str:
    return default_registry().get_card(model_id)


def get_gaps(model_id: str) -> dict:
    return default_registry().get_gaps(model_id)


def find_models_by_observable(channel: str, limit: int = 50, offset: int = 0) -> dict:
    return default_registry().find_models_by_observable(channel, limit, offset)


def validate_card(yaml_text: str, section: str | None = None) -> dict:
    return default_registry().validate_card(yaml_text, section)


def registry_tools(reg: Registry | None = None, include_get_card: bool = False) -> list[Tool]:
    """The registry tools as Tool objects: pass them to ToolRegistry(...)."""
    reg = reg or default_registry()
    sections = reg.section_names()
    tools = [
        Tool("search_models",
             "Search the dark-matter model registry by keywords in model names, aliases, family "
             "and summary. Returns up to `limit` hits (id, name, family, arXiv id, whether the "
             "card is enriched) and the total number of matches. Use it to find model IDs; it "
             "does not return observables or gaps.",
             {"type": "object", "properties": {
                 "query": {"type": "string", "description": "Keywords, e.g. 'sterile neutrino'."},
                 "family": {"type": "string", "description": "Exact family, e.g. 'warm_dark_matter'."},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                 "enriched_only": {"type": "boolean", "default": False,
                                   "description": "Only cards with observables, constraints and gaps."}},
              "required": ["query"], "additionalProperties": False},
             reg.search_models),
        Tool("get_card_section",
             "Return one top-level section of a model card as YAML (units are given per "
             "parameter), plus the card's agent_failure_modes warnings and provenance. Only "
             "enriched cards have 'observables', 'constraints' and "
             "'theory_to_observable_routing'. Long sections are truncated.",
             {"type": "object", "properties": {
                 "model_id": {"type": "string"},
                 "section": {"type": "string", "enum": sections}},
              "required": ["model_id", "section"], "additionalProperties": False},
             reg.get_card_section),
        Tool("get_gaps",
             "Return the capability gaps of one enriched model: what is missing (tool, likelihood, "
             "derivation, simulation, theory, data, calibration, emulator), its capability theme, "
             "severity, effort, the observables it blocks (with their channel) and a proposed "
             "resolution. Severity 'blocks_all_observables' or 'blocks_key_observables' means the "
             "model cannot yet be tested on those observables.",
             {"type": "object", "properties": {"model_id": {"type": "string"}},
              "required": ["model_id"], "additionalProperties": False},
             reg.get_gaps),
        Tool("find_models_by_observable",
             "List enriched models that predict at least one observable in a channel, with the "
             "IDs of those observables. Paginated: pass `offset` = next_offset for more.",
             {"type": "object", "properties": {
                 "channel": {"type": "string", "enum": reg.observable_channels()},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                 "offset": {"type": "integer", "minimum": 0, "default": 0}},
              "required": ["channel"], "additionalProperties": False},
             reg.find_models_by_observable),
        Tool("validate_card",
             "Validate YAML against the registry's JSON Schema. With `section` (e.g. "
             "'capability_gaps'), validate only that section's content. Returns valid and a list "
             "of errors as 'path: message'.",
             {"type": "object", "properties": {
                 "yaml_text": {"type": "string"},
                 "section": {"type": "string", "enum": sections}},
              "required": ["yaml_text"], "additionalProperties": False},
             reg.validate_card),
    ]
    if include_get_card:
        tools.append(Tool("get_card", "Return a whole model card as YAML.",
                          {"type": "object", "properties": {"model_id": {"type": "string"}},
                           "required": ["model_id"], "additionalProperties": False},
                          reg.get_card))
    return tools
