from agentbook import FakeModel, Tool, ToolRegistry, Tracer, call, load_trace, run_agent, summarize_trace

ECHO = ToolRegistry([Tool("echo", "Echo text.", {"type": "object", "properties": {
    "text": {"type": "string"}}, "required": ["text"]}, lambda text: text.upper())])


def test_done_with_parallel_calls(tmp_path):
    model = FakeModel([[call("echo", text="a"), call("echo", text="b")], "answer"])
    seen = []
    result = run_agent(model, ECHO, "task", tracer=Tracer(tmp_path / "t.jsonl"),
                       on_step=lambda step, messages: seen.append(step))
    assert result.stop_reason == "done" and result.steps == 2 and result.text == "answer"
    results = result.messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_001", "toolu_002"]
    assert [r["content"] for r in results] == ["A", "B"]
    assert seen == [1, 2]
    events = load_trace(tmp_path / "t.jsonl")
    assert [e["event"] for e in events] == ["run_start", "model_call", "tool_call", "tool_call",
                                            "model_call", "run_end"]
    summary = summarize_trace(events)
    assert summary["tool_calls"] == 2 and summary["stop_reason"] == "done"
    assert summary["input_tokens"] + summary["output_tokens"] == result.usage.total_tokens


def test_max_steps():
    model = FakeModel(lambda messages: call("echo", text="again"))
    result = run_agent(model, ECHO, "task", max_steps=3)
    assert result.stop_reason == "max_steps" and result.steps == 3


def test_budget():
    model = FakeModel(lambda messages: call("echo", text="x" * 500))
    result = run_agent(model, ECHO, "task", max_tokens_total=300)
    assert result.stop_reason == "budget" and result.usage.total_tokens >= 300 and result.steps < 10


def test_tool_error_goes_back_to_model():
    model = FakeModel([call("echo"), "gave up"])
    result = run_agent(model, ECHO, "task")
    assert result.messages[2]["content"][0]["is_error"] is True


def test_continue_from_messages():
    first = run_agent(FakeModel(["one"]), ECHO, "task")
    messages = first.messages + [{"role": "user", "content": "more"}]
    second = run_agent(FakeModel(["two"]), ECHO, messages)
    assert [m["role"] for m in second.messages] == ["user", "assistant", "user", "assistant"]
