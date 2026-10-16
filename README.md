# Building a Tool-Using Agent

Code for Tutorial 1 of the [Fall School on Agentic AI in Science 2026](https://ai-for-science.org/).

A small, readable agent harness: a model adapter, a tool registry, a 24-line
loop, JSONL traces and checks. The tools work on
[DarkMatterFM-Registry](https://github.com/ioanazelko/darkmatterfm-registry),
6,145 machine-extracted model cards of dark-matter models
([wiki](https://ioanazelko.github.io/darkmatterfm-registry/)). The cards are
machine-extracted, not expert-verified: use them to find things, not as physics.

Everything except `run_live.py` runs offline with no API key: a scripted
`FakeModel` stands in for the model, and a 123-card snapshot of the registry
is bundled in `data/registry_snapshot/`.

## Setup

```bash
git clone [tutorial-repo-url] && cd tutorial1-tool-using-agent
pip install -r requirements.txt
cp .env.example .env        # your key, and REGISTRY_DIR if you clone the full registry
python -m pytest            # offline, a few seconds
```

Python 3.10 or newer.

For the full registry (about 200 MB):

```bash
git clone --depth 1 https://github.com/ioanazelko/darkmatterfm-registry ~/darkmatterfm-registry
```

and set `REGISTRY_DIR=~/darkmatterfm-registry` in `.env`. The first tool call
builds an index of all 6,145 cards, which takes about 30 seconds; later runs
read it from `.cache/`.

## Run it

| Command | What it shows | Talk section |
|---|---|---|
| `python -m examples.minimal_loop` | The loop on one question, the message list after each step, and the trace | 2. The minimal loop |
| `python -m examples.lyman_alpha_plan` | Plan, act, reflect on the Lyman-α question, graded against ground truth | 5. Plan → act → reflect |
| `python -m examples.failure_trace` | A clean-looking run that invents numbers, and the trace checks that catch it | 6. Traces |
| `python -m examples.run_live "your question"` | The same loop with a real model, then the same checks | all |

`run_live.py` uses OpenRouter when `OPENROUTER_API_KEY` is set, otherwise the
Anthropic API (`ANTHROPIC_API_KEY`). Options: `--model`, `--plan` (adds the
planning tool), `--max-steps`, `--budget` (tokens). A run on Claude Sonnet 5
with the default 200k-token budget costs at most about US$0.50.

Traces are written to `traces/`. The three recorded traces from the talk are
already there, so you can read them before running anything.

## Layout

```
agentbook/
  loop.py            run_agent(): the loop and its three exits (done, max_steps, budget)
  models.py          message format, FakeModel, AnthropicModel, OpenAIModel (OpenRouter)
  tools.py           Tool, ToolRegistry: schema checks, errors returned as results, truncation
  registry.py        the registry tools: search_models, get_card_section, get_gaps,
                     find_models_by_observable, validate_card
  tracing.py         JSONL Tracer, load_trace, format_trace, summarize_trace
  guardrails.py      Budget, LoopGuard, check_cited_ids
  provenance.py      check_numbers: every number in an answer must appear in a tool result
  planning.py        the update_plan tool and run_with_plan
  evals.py           Lyman-α ground truth and graders
  reproducibility.py run metadata for traces
examples/            the four scripts above, and my_tools.py for your own tools
solutions/           one solution per exercise
data/                registry snapshot and ground truth
traces/              recorded traces
tests/               pytest, offline
```

## Exercises

See [EXERCISES.md](EXERCISES.md).

## Two ways to run an agent

This repo is the API route: your code runs the loop and you pay per token.
You can also give these tools to Claude Code or Codex and let them run the
loop on your subscription. That is quicker to try, but you give up control of
the loop, the prompts and the trace format. See the talk's section 8.

## Licence

The code is under the [MIT licence](LICENSE). The registry snapshot in
`data/registry_snapshot/` comes from DarkMatterFM-Registry and keeps that
repository's terms; see `data/registry_snapshot/REGISTRY_COPYRIGHT.md`.
