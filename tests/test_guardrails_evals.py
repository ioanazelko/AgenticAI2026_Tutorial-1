import json
from pathlib import Path

import pytest

from agentbook import Tool, Usage
from agentbook.evals import (Grade, grade_against_roadmap, grade_lyman_alpha, grade_model_gaps,
                             lyman_alpha_ground_truth, run_n_times)
from agentbook.guardrails import (Budget, BudgetExceeded, LoopGuard, check_cited_ids,
                                  estimate_cost, find_model_ids, repeated_calls)
from agentbook.registry import SNAPSHOT_DIR, Registry

DATA = Path(__file__).resolve().parents[1] / "data"
REG = Registry(SNAPSHOT_DIR)


def test_find_model_ids():
    text = ("See 2305_06364_twin_sterile_neutrino_dark_matter_v1, and "
            "(astro-ph0510088_x4_baryon_sequestration_v1). Not gap_1 or v1.")
    assert find_model_ids(text) == ["2305_06364_twin_sterile_neutrino_dark_matter_v1",
                                    "astro-ph0510088_x4_baryon_sequestration_v1"]


def test_check_cited_ids():
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": '{"model_id": "a_b_v1"}', "is_error": False}]}]
    report = check_cited_ids("Models a_b_v1 and c_d_v2.", messages)
    assert report.supported == ["a_b_v1"] and report.unsupported == ["c_d_v2"] and not report.ok
    assert check_cited_ids("a_b_v1", ['{"x": "a_b_v1"}']).ok


def test_budget_and_cost():
    b = Budget(max_steps=5, max_tokens=100)
    assert b.exceeded(1, Usage(10, 10)) is None
    assert b.exceeded(5, Usage()).startswith("step limit")
    assert b.exceeded(1, Usage(90, 20)).startswith("token budget")
    assert estimate_cost(Usage(1_000_000, 1_000_000), 5, 25) == 30
    b.check(5, [{"role": "assistant", "content": "done"}])  # answered: no raise
    with pytest.raises(BudgetExceeded):
        b.check(5, [{"role": "user", "content": []}])


def test_loop_detection():
    use = {"type": "tool_use", "id": "x", "name": "f", "input": {"a": 1}}
    messages = [{"role": "assistant", "content": [use]}] * 3
    assert repeated_calls(messages) == [{"name": "f", "input": {"a": 1}, "count": 3}]
    guard = LoopGuard([Tool("f", "", {"type": "object"}, lambda a: a)], max_repeats=2)
    assert guard.call("f", {"a": 1}) == ("1", False)
    guard.call("f", {"a": 1})
    content, is_error = guard.call("f", {"a": 1})
    assert is_error and content.startswith("Refused")


def test_ground_truth_files_match_code():
    stored = json.loads((DATA / "ground_truth_lyman_alpha_snapshot.json").read_text(encoding="utf-8"))
    fresh = lyman_alpha_ground_truth(REG)
    for key in ("n_blocked", "top_capability", "blocked_model_ids", "themes"):
        assert stored[key] == fresh[key]
    full = json.loads((DATA / "ground_truth_lyman_alpha.json").read_text(encoding="utf-8"))
    assert full["n_cards"] == 6145 and full["n_blocked"] >= fresh["n_blocked"]


def test_grade_lyman_alpha():
    truth = lyman_alpha_ground_truth(REG)
    ids = truth["blocked_model_ids"]
    good = f"{truth['n_blocked']} models; top: {truth['top_capability']}. " + ", ".join(ids)
    assert grade_lyman_alpha(good, truth).score == 1.0
    bad = grade_lyman_alpha("Boltzmann codes. made_up_model_v1", truth)
    assert bad.score == 0.0 and bad.checks["wrong_ids"] == ["made_up_model_v1"]


def test_other_graders():
    m = "2403_15533_sterile_neutrino_strong_freeze_in_v1"
    assert grade_model_gaps(f"{m}: a tool gap and a likelihood gap on o_direct_detection and "
                            "o_invisible_higgs", m, REG).score == 1.0
    top = [r["theme"] for r in sorted(REG.roadmap, key=lambda r: -r["weight"])]
    assert grade_against_roadmap(list(dict.fromkeys(top)), REG).score == 1.0


def test_run_n_times():
    report = run_n_times(lambda i: i, lambda r: Grade(r / 2), n=3)
    assert report.scores == [0, 0.5, 1.0] and report.mean == 0.5 and report.stdev == 0.5
