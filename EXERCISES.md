# Exercises

## 1. Run the loop and read its trace

Run the offline example:

```bash
python -m examples.minimal_loop
```

Then read `traces/minimal_loop.jsonl`. Every line is one event: `run_start`,
then a `model_call` and its `tool_call`s for each step, then `run_end`.

- How many input tokens does each model call bill? Why does the number grow
  every step, although the question never changes?
- Find the step where the model asks for two tools at once. How are the two
  results matched to the two requests?

Now ask a real model the same question and compare its trace with the scripted one:

```bash
python -m examples.run_live
```

## 2. Add a tool

Add a tool that answers "Which models in the registry come from arXiv:2403.15533?"

1. In `examples/my_tools.py`, write a function `models_from_paper(arxiv_id)`.
   `default_registry().index` maps each model ID to an entry whose `"arxiv"`
   field is the paper's arXiv ID.
2. Wrap it in a `Tool`: a name, a description the model will read, and a JSON
   schema for `arxiv_id`. The registry tools in `agentbook/registry.py` show
   the pattern.
3. When nothing matches, raise `ToolError` with a message that tells the model
   what to try next.
4. Add it to `MY_TOOLS` and run
   `python -m examples.run_live "Which models come from arXiv:2403.15533?"`.
   Check in the trace that the model called your tool.

Then try the description: make it vague ("Paper lookup.") and run again. Does
the model still pick your tool?

One solution is in `solutions/models_from_paper.py`.

## 3. Stretch: let the agent write a gap entry

Ask the agent to draft a `capability_gaps` section with one new gap for one
model, in the registry's YAML format, and to call `validate_card` with
`section="capability_gaps"` until it passes. The schema is strict, so expect
the first attempts to fail. Use `--plan` and a budget:

```bash
python -m examples.run_live --plan --budget 150000 \
  "Draft a capability_gaps section with one new gap for 2403_15533_sterile_neutrino_strong_freeze_in_v1 and validate it with validate_card until it passes."
```

Read the trace: how many validation rounds did it take, and what did each
error message tell the model?

## Ideas for the hackathon

- Compare the agent's Lyman-α ranking with `registry/models/capability_gap_roadmap.jsonl`.
- Use a cheaper model (`--model anthropic/claude-haiku-4.5`) for search steps and compare cost and accuracy.
- Send your traces to Langfuse (or any OpenTelemetry backend) and compare runs side by side.
