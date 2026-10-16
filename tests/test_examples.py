"""The three offline examples run and give the results the talk quotes."""

import runpy

from agentbook import ToolRegistry, tool_use_block
from examples import failure_trace
from solutions.models_from_paper import MODELS_FROM_PAPER, models_from_paper


def test_minimal_loop(capsys):
    runpy.run_module("examples.minimal_loop", run_name="__main__")
    out = capsys.readouterr().out
    assert "=== done after 4 steps" in out


def test_lyman_alpha_plan(capsys):
    runpy.run_module("examples.lyman_alpha_plan", run_name="__main__")
    out = capsys.readouterr().out
    assert "stop: done" in out
    assert "0 not found in any tool result" in out
    assert "grade against ground truth: 1.0" in out


def test_failure_trace(tmp_path):
    out = failure_trace.main(tmp_path / "failure.jsonl")
    assert out["ids"].ok                      # the model ID is right...
    assert not out["numbers"].ok              # ...but most numbers have no source


def test_models_from_paper_solution():
    result = models_from_paper("arXiv:2403.15533")
    assert [m["model_id"] for m in result["models"]] == ["2403_15533_sterile_neutrino_strong_freeze_in_v1"]
    tools = ToolRegistry([MODELS_FROM_PAPER])
    bad = tools.run(tool_use_block("t1", "models_from_paper", {"arxiv_id": "9999.99999"}))
    assert bad["is_error"] and "No models from arXiv:9999.99999" in bad["content"]
