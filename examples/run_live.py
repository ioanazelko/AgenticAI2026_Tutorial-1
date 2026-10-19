"""Run the agent with a real model, then check its answer against the trace.

    python -m examples.run_live
    python -m examples.run_live "Which observables constrain the twin sterile-neutrino model?"
    python -m examples.run_live --plan "Which models can't be tested against Lyman-alpha data yet?"

Keys and settings come from the environment or from a .env file in the repo
root (copy .env.example). With OPENROUTER_API_KEY set, the run goes through
OpenRouter; with ANTHROPIC_API_KEY, straight to the Anthropic API.

Every run is traced to traces/live_<time>.jsonl. After the run, two checks
read only the trace: every model ID in the answer must appear in a tool
result, and so must every number.
"""

import argparse
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASK = ("For the sterile-neutrino freeze-in model at stronger coupling, which observables "
                "constrain it, how is each computed, and what is missing?")
DEFAULT_MODELS = {"openrouter": "anthropic/claude-sonnet-5", "anthropic": "claude-sonnet-5"}


def load_env(path: Path = ROOT / ".env") -> None:
    """Read KEY=value lines from .env without overriding variables already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            if value and not value.endswith("..."):  # skip the placeholders from .env.example
                os.environ.setdefault(key.strip(), value)


def make_model(provider: str, name: str | None):
    from agentbook.models import AnthropicModel, OpenAIModel
    name = name or DEFAULT_MODELS[provider]
    if provider == "openrouter":
        return OpenAIModel(name, base_url="https://openrouter.ai/api/v1",
                           api_key=os.environ["OPENROUTER_API_KEY"])
    return AnthropicModel(name)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("task", nargs="?", default=DEFAULT_TASK)
    parser.add_argument("--provider", choices=["openrouter", "anthropic"],
                        default="openrouter" if os.environ.get("OPENROUTER_API_KEY") else "anthropic")
    parser.add_argument("--model", help="model name; default anthropic/claude-sonnet-5 on "
                                        "OpenRouter, claude-sonnet-5 on Anthropic")
    parser.add_argument("--plan", action="store_true", help="add the update_plan tool (plan, act, reflect)")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--budget", type=int, default=200_000, help="stop after this many tokens")
    args = parser.parse_args()
    key = "OPENROUTER_API_KEY" if args.provider == "openrouter" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key):
        parser.exit(1, f"No {key} found. Put OPENROUTER_API_KEY=sk-or-v1-... (your real key) "
                       "in .env, or export it.\n")

    from agentbook import ToolRegistry, Tracer, load_trace, run_agent
    from agentbook.guardrails import check_cited_ids, tool_outputs_from_trace
    from agentbook.planning import run_with_plan
    from agentbook.provenance import check_numbers
    from agentbook.registry import default_registry, registry_tools
    from agentbook.tracing import format_trace, last_run, summarize_trace
    from examples.my_tools import MY_TOOLS

    reg = default_registry()
    print(f"registry: {reg.root} ({len(reg.index)} cards)")
    model = make_model(args.provider, args.model)
    trace = ROOT / "traces" / f"live_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    tools = ToolRegistry(registry_tools(reg) + MY_TOOLS)
    limits = dict(max_steps=args.max_steps, max_tokens_total=args.budget, tracer=Tracer(trace))
    if args.plan:
        result = run_with_plan(model, tools, args.task, **limits).result
    else:
        result = run_agent(model, tools, args.task, **limits)

    events = last_run(load_trace(trace))
    print("\n=== trace ===")
    print(format_trace(events, width=100))
    print(f"\n=== answer ({result.stop_reason} after {result.steps} steps, "
          f"{result.usage.input_tokens} in + {result.usage.output_tokens} out tokens) ===\n")
    print(result.text or "(no answer: the run hit a limit)")

    evidence = tool_outputs_from_trace(events)
    ids = check_cited_ids(result.text, evidence)
    numbers = check_numbers(result.text, evidence)
    print("\n=== checks (from the trace alone) ===")
    print(f"model IDs: {len(ids.cited)} cited, unsupported: {ids.unsupported or 'none'}")
    print(numbers.summary())
    print(f"\nsummary: {summarize_trace(events)}")
    print(f"trace: {trace}")


if __name__ == "__main__":
    main()
