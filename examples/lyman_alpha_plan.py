"""Plan, act, reflect on the headline question.

    python -m examples.lyman_alpha_plan

"Which dark-matter models in the registry can't be tested against Lyman-alpha
forest data yet, and what single missing capability would unblock the most
of them? Cite model IDs."

The model is a FakeModel driven by a *policy*: a function that reads the
message list (including every tool result so far) and decides the next turn.
It calls the real tools and computes its answer only from what they return,
so the printed answer is grounded, and it is graded at the end against the
ground truth computed directly from the registry files.
"""

import json
from collections import defaultdict
from pathlib import Path

from agentbook import FakeModel, ToolRegistry, Tracer, call, load_trace, summarize_trace
from agentbook.evals import BLOCKING, grade_lyman_alpha, lyman_alpha_ground_truth
from agentbook.planning import run_with_plan
from agentbook.registry import registry_tools

TASK = ("Which dark-matter models in the registry can't be tested against Lyman-alpha forest "
        "data yet, and what single missing capability would unblock the most of them? "
        "Cite model IDs.")
TRACE = Path(__file__).resolve().parents[1] / "traces" / "lyman_alpha_plan.jsonl"
PAGE, BATCH = 20, 20

PLAN = ["List models with a Lyman-alpha observable", "Get capability gaps for each model",
        "Keep gaps that block a Lyman-alpha observable; group them by capability theme",
        "Rank themes by number of models; check every cited ID"]


def plan(done: int) -> dict:
    """update_plan call with the first `done` steps marked done."""
    steps = [{"step": s, "status": "done" if i < done else ("in_progress" if i == done else "pending")}
             for i, s in enumerate(PLAN)]
    return call("update_plan", steps=steps)


def tool_results(messages: list[dict]) -> list[tuple[dict, dict]]:
    """(tool_use, parsed result) pairs from the messages, for successful JSON results."""
    uses = {b["id"]: b for m in messages if m["role"] == "assistant"
            for b in m["content"] if b["type"] == "tool_use"}
    pairs = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b["type"] == "tool_result" and not b["is_error"]:
                    pairs.append((uses[b["tool_use_id"]], json.loads(b["content"])))
    return pairs


def policy(messages: list[dict]):
    """Decide the next turn from the tool results seen so far."""
    results = tool_results(messages)
    if not results:
        return ["Plan first.", plan(0)]
    pages = [r for use, r in results if use["name"] == "find_models_by_observable"]
    if not pages or pages[-1]["next_offset"] is not None:
        offset = pages[-1]["next_offset"] if pages else 0
        return call("find_models_by_observable", channel="lyman_alpha", limit=PAGE, offset=offset)
    candidates = [m["model_id"] for p in pages for m in p["models"]]
    fetched = {r["model_id"] for use, r in results if use["name"] == "get_gaps"}
    todo = [m for m in candidates if m not in fetched]
    if todo:
        return [f"{len(fetched)} of {len(candidates)} models checked."] + (
            [plan(1)] if not fetched else []) + [call("get_gaps", model_id=m) for m in todo[:BATCH]]
    if sum(use["name"] == "update_plan" for use, _ in results) < 3:
        return ["All gaps fetched. Grouping by capability theme.", plan(3)]
    return answer(pages[-1]["total"], [r for use, r in results if use["name"] == "get_gaps"])


def answer(n_candidates: int, gap_results: list[dict]) -> str:
    """Group blocking Lyman-alpha gaps by theme and write the final answer."""
    by_theme, fully = defaultdict(set), defaultdict(set)
    for r in gap_results:
        themes = {g["theme"] for g in r["gaps"] if g["severity"] in BLOCKING and
                  any(o["channel"] == "lyman_alpha" for o in g["blocking_observables"])}
        for t in themes:
            by_theme[t].add(r["model_id"])
        if len(themes) == 1:
            fully[next(iter(themes))].add(r["model_id"])
    blocked = sorted(set().union(*by_theme.values())) if by_theme else []
    ranked = sorted(by_theme, key=lambda t: (-len(by_theme[t]), t))
    top = ranked[0]
    lines = [
        f"{len(blocked)} of {n_candidates} models with a Lyman-alpha observable cannot yet be "
        "tested against Lyman-alpha data: each has a gap of severity blocks_key_observables or "
        "blocks_all_observables on a Lyman-alpha observable (machine-extracted, not expert-verified).",
        "",
        f"Top missing capability: {top}. It appears among the blocking gaps of "
        f"{len(by_theme[top])} of these models and would unblock {len(fully[top])} of them "
        "completely (their other blocking gaps, if any, share this theme).",
        "",
        "All themes (models blocked / fully unblocked):",
        *[f"  {t}: {len(by_theme[t])} / {len(fully[t])}" for t in ranked],
        "",
        f"Models blocked by {top}: " + ", ".join(sorted(by_theme[top])),
        "",
        "All blocked models: " + ", ".join(blocked),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    TRACE.unlink(missing_ok=True)
    tools = ToolRegistry(registry_tools())
    # The whole message list is re-sent every step, so input tokens grow fast:
    # with the default 200k budget this run stops early with stop_reason "budget".
    run = run_with_plan(FakeModel(policy), tools, TASK, max_steps=30,
                        max_tokens_total=1_000_000, tracer=Tracer(TRACE))
    print(run.result.text)
    print(f"\nstop: {run.result.stop_reason} after {run.result.steps} steps")
    print(f"plan versions: {len(run.plan.history)}; final plan statuses: "
          f"{[s['status'] for s in run.plan.steps]}")
    print(f"citation check: {len(run.citations.cited)} IDs cited, "
          f"{len(run.citations.unsupported)} not found in any tool result")
    print(f"trace summary: {summarize_trace(load_trace(TRACE))}")
    grade = grade_lyman_alpha(run.result.text, lyman_alpha_ground_truth())
    print(f"grade against ground truth: {grade.score} {grade.checks}")
