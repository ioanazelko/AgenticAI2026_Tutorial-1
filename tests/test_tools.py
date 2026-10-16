from agentbook.tools import Tool, ToolError, ToolRegistry, truncate

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 0}},
          "required": ["n"], "additionalProperties": False}


def square(n):
    if n == 13:
        raise ToolError("13 is unlucky; try 12 or 14.")
    if n == 7:
        raise ValueError("boom")
    return {"square": n * n}


REG = ToolRegistry([Tool("square", "Square a number.", SCHEMA, square)], max_output_chars=50)


def test_specs():
    assert REG.specs() == [{"name": "square", "description": "Square a number.", "input_schema": SCHEMA}]


def test_success_is_json():
    content, is_error = REG.call("square", {"n": 3})
    assert not is_error and '"square": 9' in content


def test_errors_become_results():
    assert REG.call("cube", {"n": 1}) == ("Unknown tool 'cube'. Available tools: square.", True)
    content, is_error = REG.call("square", {})
    assert is_error and "'n' is a required property" in content
    content, is_error = REG.call("square", {"n": -1})
    assert is_error and "(n)" in content
    assert REG.call("square", {"n": 13}) == ("13 is unlucky; try 12 or 14.", True)
    assert REG.call("square", {"n": 7}) == ("square failed with ValueError: boom", True)


def test_run_matches_ids():
    block = {"type": "tool_use", "id": "toolu_9", "name": "square", "input": {"n": 2}}
    result = REG.run(block)
    assert result["tool_use_id"] == "toolu_9" and result["is_error"] is False


def test_truncation_is_visible():
    text = truncate("x" * 100, 10)
    assert text.startswith("x" * 10) and "truncated: showing 10 of 100" in text
    content, _ = ToolRegistry([Tool("long", "", {"type": "object"}, lambda: "y" * 200)],
                              max_output_chars=20).call("long", {})
    assert "truncated" in content
