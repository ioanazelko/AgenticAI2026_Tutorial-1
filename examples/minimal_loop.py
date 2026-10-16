"""The minimal loop answers a single-model question.

    python -m examples.minimal_loop

The model is a FakeModel with a fixed script, so this runs offline and gives
the same output every time. The tools are real: they read the registry
snapshot (or REGISTRY_DIR). The message list is printed after each step and
the run is traced to traces/minimal_loop.jsonl.

To ask the same question to a real model, use examples/run_live.py.
"""

from pathlib import Path

from agentbook import FakeModel, ToolRegistry, Tracer, call, format_messages, print_trace, run_agent
from agentbook.registry import registry_tools

MODEL_ID = "2403_15533_sterile_neutrino_strong_freeze_in_v1"
TASK = ("For the sterile-neutrino freeze-in model at stronger coupling, which observables "
        "constrain it, how is each computed, and what is missing?")
TRACE = Path(__file__).resolve().parents[1] / "traces" / "minimal_loop.jsonl"

script = [
    # step 1: find the model ID
    ["I need the model ID first.", call("search_models", query="sterile neutrino strong freeze-in", limit=3)],
    # step 2: two sections at once (two tool_use blocks in one turn)
    ["Found it. Now the observables and how each is computed.",
     call("get_card_section", model_id=MODEL_ID, section="observables"),
     call("get_card_section", model_id=MODEL_ID, section="theory_to_observable_routing")],
    # step 3: what is missing
    ["Both observables share one route. Now the capability gaps.", call("get_gaps", model_id=MODEL_ID)],
    # step 4: the answer, built only from the three tool results above
    f"""Model {MODEL_ID} (arXiv:2403.15533; machine-extracted, not expert-verified).

Observables:
1. o_direct_detection (direct_detection): Higgs-singlet mixing mediates spin-independent
   scattering on nucleons. sigma_SI comes from an analytic Higgs-portal formula (route
   r_low_reheat_portal, step s2) in (lambda, theta, m_2).
2. o_invisible_higgs (collider): h -> NN for M between about 1 and 6 GeV. BR_inv comes from an
   analytic width formula (step s3) valid for M < m_h/2.
Both need the relic abundance first: step s1 solves the paper's Boltzmann equations in the
Boltzmann-suppressed regime (T_R < M).

What is missing (get_gaps):
- gap_1 (tool, blocks_key_observables, medium effort): no public Boltzmann solver covers
  freeze-in with T_R below the dark-matter mass, so neither observable can be evaluated
  on a relic-consistent parameter space outside the paper.
- gap_2 (likelihood, degrades_precision, small effort): direct-detection limits are cited
  but not ingested as a machine-readable likelihood.

Caveat from the card: it covers only the low-temperature freeze-in branch.""",
]

if __name__ == "__main__":
    TRACE.unlink(missing_ok=True)
    tools = ToolRegistry(registry_tools())

    def show(step, messages):
        print(f"\n=== after step {step}: {len(messages)} messages ===")
        print(format_messages(messages))

    result = run_agent(FakeModel(script), tools, TASK, tracer=Tracer(TRACE), on_step=show)
    print(f"\n=== {result.stop_reason} after {result.steps} steps, "
          f"{result.usage.total_tokens} tokens (faked) ===\n")
    print(result.text)
    print(f"\n=== trace: {TRACE} ===")
    print_trace(TRACE)
