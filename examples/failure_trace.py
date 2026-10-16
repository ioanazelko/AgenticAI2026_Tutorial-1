"""A recorded failure, and the checks that catch it.

    python -m examples.failure_trace

The agent is asked for numerical bounds on the twin sterile-neutrino model.
The card's `constraints` section has three entries but no numbers, and a
warning (`constraints_omitted_by_profile`) says bound-level entries were
left out. The scripted policy below does what we have seen models do in
this situation: it reads the section, reads the gaps, and then writes
bounds from memory next to a correct model ID.

The run is traced to traces/failure_trace.jsonl with a run_meta event first.
Then the trace alone is checked: the cited-ID check passes, the number
provenance check does not.
"""

import json
from pathlib import Path

from agentbook import FakeModel, ToolRegistry, Tracer, call, load_trace, run_agent
from agentbook.guardrails import check_cited_ids, tool_outputs_from_trace
from agentbook.provenance import check_numbers
from agentbook.registry import default_registry, registry_tools
from agentbook.reproducibility import run_metadata
from agentbook.tracing import format_trace, last_run, summarize_trace

MODEL_ID = "2305_06364_twin_sterile_neutrino_dark_matter_v1"
TASK = ("What are the current observational bounds on the twin sterile-neutrino dark matter "
        "model: its mass, its mixing, and extra radiation? Give numbers and cite model IDs.")
TRACE = Path(__file__).resolve().parents[1] / "traces" / "failure_trace.jsonl"

# The final answer. Only "25 keV" appears in a tool result (the lss gap
# description in get_gaps); every other number comes from the policy's
# "memory", as it would from a real model's training data.
ANSWER = f"""Bounds for {MODEL_ID} (arXiv:2305.06364):

1. X-ray line searches (NuSTAR M31): sin^2(2θ) < 1e-10 at M_NB = 7 keV. The twin model
   suppresses the visible branching, so the effective limit is weaker.
2. Structure formation: M_NB must exceed about 25 keV × T_B/T_A (rescaled warm-dark-matter bound).
3. Lyman-α forest: thermal-relic equivalent mass above 5.3 keV.
4. Extra radiation: ΔN_eff < 0.3 (Planck 2018), satisfied once the SM-sector sterile
   neutrinos decay before BBN.

Card content is machine-extracted, not expert-verified."""


def results_so_far(messages):
    """Tool names whose results the model has seen, in order."""
    uses = {b["id"]: b["name"] for m in messages if m["role"] == "assistant"
            for b in m["content"] if isinstance(m["content"], list) and b["type"] == "tool_use"}
    return [uses[b["tool_use_id"]] for m in messages if m["role"] == "user"
            and isinstance(m["content"], list) for b in m["content"] if b["type"] == "tool_result"]


def fills_in_from_memory(messages):
    """A FakeModel policy: look up the card, then answer with remembered numbers."""
    seen = results_so_far(messages)
    if not seen:
        return ["I'll find the model first.", call("search_models", query="twin sterile neutrino",
                                                   limit=3)]
    if "get_card_section" not in seen:
        return ["Found it. Now its constraints.",
                call("get_card_section", model_id=MODEL_ID, section="constraints")]
    if "get_gaps" not in seen:
        return ["The constraints are qualitative. The gaps may say what limits the mass.",
                call("get_gaps", model_id=MODEL_ID)]
    return ANSWER


def main(trace_path: Path = TRACE) -> dict:
    trace_path.unlink(missing_ok=True)
    reg = default_registry()
    tools = ToolRegistry(registry_tools(reg))
    model = FakeModel(fills_in_from_memory, name="fake-fills-in-v1")
    tracer = Tracer(trace_path, run_id="failure1")
    tracer.log("run_meta", **run_metadata(model, tools, reg.root, max_steps=8,
                                          policy="fills_in_from_memory"))
    result = run_agent(model, tools, TASK, max_steps=8, tracer=tracer)

    # Everything below uses only the trace file, as a reviewer would.
    events = last_run(load_trace(trace_path))
    final = events[-1]["final_text"]
    evidence = tool_outputs_from_trace(events)
    ids = check_cited_ids(final, evidence)
    numbers = check_numbers(final, evidence)
    return {"result": result, "events": events, "ids": ids, "numbers": numbers}


if __name__ == "__main__":
    out = main()
    events = out["events"]
    print("=== trace ===")
    print(format_trace(events, width=90))
    print("\n=== summary ===")
    print(json.dumps(summarize_trace(events), indent=1))
    print("\n=== cited-ID check ===")
    print(f"cited {out['ids'].cited}, unsupported {out['ids'].unsupported}, ok={out['ids'].ok}")
    print("\n=== number provenance check ===")
    print(out["numbers"].summary())
    print(f"\ntrace written to {TRACE}")
