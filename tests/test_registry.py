import os
import shutil

import pytest

from agentbook import ToolRegistry
from agentbook.registry import STATUS, Registry, SNAPSHOT_DIR, arxiv_id, registry_tools
from agentbook.tools import ToolError

REG = Registry(SNAPSHOT_DIR)
CLEAN = "2403_15533_sterile_neutrino_strong_freeze_in_v1"
PLAIN = "0910_3177_light_hidden_fermion_ovr_eft_v1"


def test_index(tmp_path):
    assert len(REG.index) > 100
    e = REG.index[CLEAN]
    assert e["arxiv"] == "2403.15533" and e["enriched"] and e["family"] == "sterile_neutrino_dark_matter"
    assert arxiv_id("hep-ph9901234") == "hep-ph/9901234"
    # the cached index is rebuilt when a card is edited in place
    root = tmp_path / "reg"
    shutil.copytree(SNAPSHOT_DIR / "registry" / "models" / "cards" / "sterile_neutrino_dark_matter",
                    root / "registry" / "models" / "cards" / "sterile_neutrino_dark_matter")
    reg = Registry(root, cache_dir=tmp_path / "cache")
    path = root / reg.index[CLEAN]["path"]
    path.write_text(path.read_text().replace("name:", "name: EDITED", 1))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert Registry(root, cache_dir=tmp_path / "cache").index[CLEAN]["name"].startswith("EDITED")


def test_search():
    r = REG.search_models("sterile neutrino strong freeze-in", limit=3)
    assert r["models"][0]["model_id"] == CLEAN and len(r["models"]) == 3
    assert r["status"] == STATUS and r["models"][0]["arxiv"] and r["models"][0]["file"]
    fam = REG.search_models("dark", family="warm_dark_matter", limit=50)
    assert all(m["family"] == "warm_dark_matter" for m in fam["models"])


def test_get_card_section():
    r = REG.get_card_section(CLEAN, "observables")
    assert "o_direct_detection" in r["content"]
    assert r["provenance"] == {"file": REG.index[CLEAN]["path"], "arxiv": "2403.15533", "status": STATUS}
    assert r["warnings"][0]["id"] == "strong_freeze_in_temperature_assumption"


def test_missing_section_lists_available():
    with pytest.raises(ToolError, match="not available .*not enriched.*available sections: .*identity"):
        REG.get_card_section(PLAIN, "constraints")
    with pytest.raises(ToolError, match="Unknown model_id"):
        REG.get_card_section("nope_v1", "identity")


def test_get_gaps():
    r = REG.get_gaps(CLEAN)
    assert [g["gap_type"] for g in r["gaps"]] == ["tool", "likelihood"]
    assert r["gaps"][0]["blocking_observables"][0] == {"id": "o_direct_detection", "channel": "direct_detection"}
    assert r["gaps"][0]["theme"] and r["provenance"]["status"] == STATUS
    with pytest.raises(ToolError, match="only enriched cards"):
        REG.get_gaps(PLAIN)


def test_find_models_by_observable():
    r = REG.find_models_by_observable("lyman_alpha", limit=5)
    assert r["total"] > 50 and len(r["models"]) == 5 and r["next_offset"] == 5
    assert all(m["observables"] for m in r["models"])
    with pytest.raises(ToolError, match="Valid channels: .*lyman_alpha"):
        REG.find_models_by_observable("lyman")


def test_get_card_is_big():
    assert len(REG.get_card("2305_06364_twin_sterile_neutrino_dark_matter_v1")) > 30_000


def test_validate_card():
    assert REG.validate_card(REG.get_card(CLEAN))["valid"] is True
    bad = REG.validate_card("model_id: x\nschema_version: model_only_v0\n")
    assert bad["valid"] is False and any("required" in e for e in bad["errors"])
    assert REG.validate_card("a: [unclosed")["errors"][0].startswith("YAML parse error")
    gap = """gaps:
- id: gap_1
  gap_type: tool
  description: No public solver.
  blocking_observables: [o1]
  blocking_routes: [r1]
  proposed_resolution: Write one.
  estimated_effort: small
  severity: minor
"""
    assert REG.validate_card(gap, section="capability_gaps")["valid"] is True
    wrong = REG.validate_card(gap.replace("severity: minor", "severity: fatal"), section="capability_gaps")
    assert wrong["valid"] is False and "fatal" in wrong["errors"][0]


def test_tools_through_registry():
    tools = ToolRegistry(registry_tools(REG, include_get_card=True))
    assert set(tools.tools) == {"search_models", "get_card_section", "get_gaps",
                                "find_models_by_observable", "validate_card", "get_card"}
    content, is_error = tools.call("get_card_section", {"model_id": CLEAN, "section": "bogus"})
    assert is_error and "is not one of" in content
    content, is_error = tools.call("get_card", {"model_id": CLEAN})
    assert not is_error and "truncated" in content
