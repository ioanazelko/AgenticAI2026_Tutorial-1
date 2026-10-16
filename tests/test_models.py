import pytest

from agentbook.models import (FakeModel, ModelResponse, Usage, call, from_anthropic_response,
                              from_openai_response, to_openai_messages, to_openai_tools)


def test_fake_model_replays_script_with_ids_and_usage():
    model = FakeModel([["thinking", call("search_models", query="axion")], "final"])
    r1 = model.complete("sys", [{"role": "user", "content": "hi"}], [])
    assert r1.stop_reason == "tool_use"
    assert r1.tool_uses[0] == {"type": "tool_use", "id": "toolu_001", "name": "search_models",
                               "input": {"query": "axion"}}
    assert r1.text == "thinking" and r1.usage.input_tokens > 0 and r1.usage.output_tokens > 0
    r2 = model.complete("sys", [], [])
    assert r2.stop_reason == "end_turn" and r2.text == "final"
    with pytest.raises(RuntimeError, match="exhausted"):
        model.complete("sys", [], [])


def test_fake_model_policy_sees_messages():
    model = FakeModel(lambda messages: f"{len(messages)} messages")
    assert model.complete("", [{"role": "user", "content": "x"}], []).text == "1 messages"
    assert model.requests[0]["messages"][0]["content"] == "x"


def test_fake_model_max_tokens():
    assert FakeModel(["x" * 400]).complete("", [], [], max_tokens=10).stop_reason == "max_tokens"


def test_usage_adds():
    assert (Usage(1, 2) + Usage(3, 4)).total_tokens == 10


MESSAGES = [
    {"role": "user", "content": "Find gaps"},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "t1", "name": "get_gaps", "input": {"model_id": "a_v1"}},
        {"type": "tool_use", "id": "t2", "name": "get_gaps", "input": {"model_id": "b_v1"}}]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
        {"type": "tool_result", "tool_use_id": "t2", "content": "no such model", "is_error": True}]},
]


def test_to_openai_messages():
    out = to_openai_messages("be careful", MESSAGES)
    assert out[0] == {"role": "system", "content": "be careful"}
    assert out[1] == {"role": "user", "content": "Find gaps"}
    assert out[2]["content"] == "Looking."
    assert out[2]["tool_calls"][1] == {"id": "t2", "type": "function", "function": {
        "name": "get_gaps", "arguments": '{"model_id": "b_v1"}'}}
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": "ok"}
    assert out[4] == {"role": "tool", "tool_call_id": "t2", "content": "ERROR: no such model"}
    assert len(out) == 5


def test_to_openai_tools():
    spec = {"name": "f", "description": "d", "input_schema": {"type": "object"}}
    assert to_openai_tools([spec]) == [{"type": "function", "function": {
        "name": "f", "description": "d", "parameters": {"type": "object"}}}]


def test_from_openai_response():
    resp = {"model": "m", "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            "choices": [{"finish_reason": "tool_calls", "message": {
                "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "get_gaps", "arguments": '{"model_id": "x_v1"}'}},
                    {"id": "c2", "type": "function",
                     "function": {"name": "get_gaps", "arguments": "{bad json"}}]}}]}
    r = from_openai_response(resp)
    assert r.stop_reason == "tool_use" and r.usage == Usage(7, 3)
    assert r.tool_uses[0]["input"] == {"model_id": "x_v1"}
    assert r.tool_uses[1]["input"] == {"_invalid_json": "{bad json"}
    text = from_openai_response({"choices": [{"finish_reason": "length",
                                              "message": {"content": "partial"}}]})
    assert text.stop_reason == "max_tokens" and text.text == "partial"
    refused = from_openai_response({"choices": [{"finish_reason": "stop", "message": {
        "content": None, "refusal": "I can't help with that."}}]})
    assert refused.text == "I can't help with that."


def test_from_anthropic_response_keeps_unknown_blocks():
    resp = {"model": "claude", "stop_reason": "tool_use",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                        {"type": "text", "text": "hi"},
                        {"type": "tool_use", "id": "u1", "name": "f", "input": {"a": 1}}]}
    r = from_anthropic_response(resp)
    assert isinstance(r, ModelResponse) and r.stop_reason == "tool_use"
    assert r.content[0]["type"] == "thinking" and r.text == "hi"
    assert r.tool_uses == [{"type": "tool_use", "id": "u1", "name": "f", "input": {"a": 1}}]
    full = dict(resp, stop_reason="model_context_window_exceeded")
    assert from_anthropic_response(full).stop_reason == "max_tokens"
