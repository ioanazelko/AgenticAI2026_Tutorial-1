# How the loop works

A walk through `run_agent` in [agentbook/loop.py](agentbook/loop.py) for
readers who have never seen an agent loop. The worked example is
`python -m examples.minimal_loop`, so you can run it and compare.

## The idea

A language model can only read text and write text. It cannot search a
database or run code. An agent is a short program around the model that lets
the model *ask* for an action, performs the action for it, shows it the
result, and asks again, until the model replies without asking for anything.

## Model, agent, reply

- **The model** is the language model itself (Claude, GPT, ...), reached
  through an API. It does one thing: given the conversation so far, it writes
  the next turn. It never runs anything.
- **The agent** is the whole system: the model, the loop below, and the tools.
- **A reply** always means the *model's* reply: what comes back from one call
  to the model (`response` in the code).

Who writes each entry of the message list:

| Entry | `role` | Written by |
|---|---|---|
| The question | `user` | A human, or whoever started the run |
| Text and tool requests | `assistant` | The model (a reply) |
| Tool results | `user` | The loop code, after running the tools |
| The final answer | `assistant` | The model (its last reply, the one with no tool requests) |

The agent's final answer is the model's last reply, passed on by the loop.
The label `assistant` means "written by the model", not "written by the
agent". Tool results go under `user` because the conversation has only two
speakers: the model, and everything outside it.

## Two things to know first

**The model has no memory between calls.** Every call sends everything
again: the `system` prompt (standing instructions), the tool descriptions and
`messages`, the list of turns so far. The message list is the agent's whole
memory: if something is not in it, the model never saw it. This is also why
each call bills more input tokens than the one before.

**A reply is a list of blocks, not a string.** Two kinds matter:

```python
{"type": "text", "text": "I need the model ID first."}
{"type": "tool_use", "id": "toolu_001", "name": "search_models",
 "input": {"query": "sterile neutrino strong freeze-in", "limit": 3}}
```

A `tool_use` block is only a request. The model fills in a form (which tool,
which arguments, a unique ID); your code decides whether and how to run it.
The full message format is in the docstring at the top of
[agentbook/models.py](agentbook/models.py).

## The loop, line by line

This is the core of `run_agent`, shortened (the full version is below):

```python
for step in range(1, max_steps + 1):
    response = call_model(model, system, messages, ...)
    messages.append({"role": "assistant", "content": response.content})
    if not response.tool_uses:  # no tool requests: done
        return finish(response.text, ...)
    results = [call_tool(tools, b, step, tracer)
               for b in response.tool_uses]
    messages.append({"role": "user", "content": results})
```

- `for step in range(1, max_steps + 1)`: at most `max_steps` rounds. A
  confused model could otherwise ask for tools forever, at your expense. When
  the limit is hit the run ends with stop reason `"max_steps"`.
- `call_model(...)`: sends the system prompt, the messages and the tool
  descriptions to the model and returns its reply. It also times the call and
  records it in the trace.
- `messages.append({"role": "assistant", ...})`: saves the reply in the
  history, all of its blocks (rule 1 below).
- `if not response.tool_uses`: if the model asked for no tools, it is done
  and its text is the answer. `finish` packages the final text, the full
  message list, the number of steps, the token usage and the stop reason
  (`"done"`) into an `AgentResult` (rule 2).
- `call_tool(tools, b, step, tracer)`: runs one requested tool. `b` is one
  `tool_use` block. The `ToolRegistry` finds the tool by name, checks the
  arguments against the tool's schema, runs the Python function and wraps the
  output in a `tool_result` block:

  ```python
  {"type": "tool_result", "tool_use_id": "toolu_001",
   "content": "...", "is_error": False}
  ```

  `tracer` is an optional logger that writes every call to a JSONL file;
  `step` tells it which round the call belongs to.
- `messages.append({"role": "user", "content": results})`: sends all the
  results back as the next turn. Then the loop starts again (rule 3).

## Three rules

**1. Append the full assistant reply first.** "Full" means
`response.content` (all blocks), not `response.text` (only the words). Without
the `tool_use` blocks, the next call would contain results that answer
requests with IDs that are not in the history, and the API rejects the call
with an error. Even if it did not, the model would see answers to questions it
has no record of asking. "First" means before checking whether the model is
done, so the final answer is in the message list you return too.

**2. "Done" means no tool requests.** Models often write text *and* request
tools in the same reply ("Found it. Now the observables..." plus two requests).
So "the reply has text" does not mean "the reply is the answer". The only
reliable signal is a reply with no `tool_use` blocks. The API reports the
same thing as `stop_reason`: `"tool_use"` while it wants tools, `"end_turn"`
when it is finished.

**3. Every request gets a result, all in one user message, matched by ID.**
If the model asks for two tools at once, you send back two `tool_result`
blocks in one message, each carrying the `tool_use_id` of the request it
answers. A request without a result is an API error. Anthropic's
documentation also notes that sending results as separate messages teaches
the model to stop making parallel calls.

"Every request" includes the ones that fail. `ToolRegistry.call` in
[agentbook/tools.py](agentbook/tools.py) never raises: an unknown tool name,
invalid arguments or a Python exception all come back as a result with
`is_error: True` and a readable message. The model reads it and can correct
itself on the next step, instead of the whole run crashing.

With OpenRouter, `OpenAIModel` translates this format into OpenAI's, where
each result is its own message with role `tool`. The loop does not change.

## Worked example: `minimal_loop`

The question: *For the sterile-neutrino freeze-in model at stronger coupling,
which observables constrain it, how is each computed, and what is missing?*
The model is a scripted `FakeModel`, so the run is the same every time.

| Step | The model's reply | What the loop does |
|---|---|---|
| 1 | Text + one request: `search_models` | Saves the reply, runs the search, sends back 1 result |
| 2 | Text + two requests: `get_card_section` for `observables` and for `theory_to_observable_routing` | Saves the reply, runs both, sends back both results in **one** user message |
| 3 | Text + one request: `get_gaps` | Saves the reply, runs it, sends back 1 result |
| 4 | Text only: the answer | Saves the reply, finds no requests, calls `finish` with stop reason `"done"` |

At the end the message list has 8 entries, alternating speakers: the
question, then three pairs of (model reply, tool results), then the final
answer. The script prints the list after every step, and the trace is in
`traces/minimal_loop.jsonl`.

## What the short version leaves out

The full `run_agent` also:

- adds up token usage after every step and stops with `"budget"` once the
  total passes `max_tokens_total`;
- calls an optional `on_step(step, messages)` after each round
  (`minimal_loop` uses it to print the message list);
- records the start and end of the run in the trace.

One case it does not handle: a reply cut off by the `max_tokens` limit before
it requests a tool also has no tool requests, so the loop reports `"done"`
with a truncated answer. `response.stop_reason == "max_tokens"` tells the two
apart, but `run_agent` does not check it.
