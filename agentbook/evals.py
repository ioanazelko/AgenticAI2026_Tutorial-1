"""Evaluation: ground truth from the registry's own files, graders, and variance.

The headline question: "Which dark-matter models in the registry can't be
tested against Lyman-alpha forest data yet, and what single missing
capability would unblock the most of them?"

Definition used for the ground truth (`lyman_alpha_ground_truth`):

  A model "can't be tested against Lyman-alpha data yet" if its card has at
  least one observable with channel 'lyman_alpha' AND
  capability_gaps_full.jsonl has a gap for it with severity
  'blocks_all_observables' or 'blocks_key_observables' whose
  blocking_observables include one of those observables.

  The "missing capability" of a gap is its theme in
  capability_gap_roadmap.jsonl. The capability that "would unblock the most"
  is the theme that appears among the blocking gaps of the most models.
  Because a model can have several blocking gaps, we also count how many
  models that theme would unblock completely (all their blocking gaps share it).
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .guardrails import MODEL_ID_RE, find_model_ids
from .registry import Registry, default_registry

BLOCKING = ("blocks_all_observables", "blocks_key_observables")
LYMAN_ALPHA_DEFINITION = (
    "A model can't be tested against Lyman-alpha data yet if its card has an observable with "
    "channel 'lyman_alpha' and capability_gaps_full.jsonl has a gap for it with severity "
    "blocks_all_observables or blocks_key_observables whose blocking_observables include that "
    "observable. A gap's missing capability is its theme in capability_gap_roadmap.jsonl. "
    "The top capability is the theme found among the blocking gaps of the most such models; "
    "n_fully_unblocked counts models whose blocking gaps all share that theme.")


# ------------------------------------------------------------ ground truth


def blocked_models(reg: Registry, channel: str = "lyman_alpha") -> dict[str, list[dict]]:
    """model_id -> its blocking gaps that hit an observable in `channel`."""
    blocked = {}
    for model_id, entry in sorted(reg.index.items()):
        ids = {oid for oid, ch in entry["observables"] if ch == channel}
        record = reg.gaps.get(model_id)
        if not ids or record is None:
            continue
        gaps = [g for g in record["capability_gaps"].get("gaps") or []
                if g["severity"] in BLOCKING and ids & set(g.get("blocking_observables") or [])]
        if gaps:
            blocked[model_id] = gaps
    return blocked


def lyman_alpha_ground_truth(reg: Registry | None = None, channel: str = "lyman_alpha") -> dict:
    """The answer to the headline question, computed directly from the files."""
    reg = reg or default_registry()
    blocked = blocked_models(reg, channel)
    by_theme, fully = defaultdict(set), defaultdict(set)
    for model_id, gaps in blocked.items():
        themes = {reg.theme(model_id, g) or "(no roadmap theme)" for g in gaps}
        for theme in themes:
            by_theme[theme].add(model_id)
        if len(themes) == 1:
            fully[themes.pop()].add(model_id)
    ranking = sorted(by_theme, key=lambda t: (-len(by_theme[t]), t))
    with_channel = [m for m, e in reg.index.items() if any(ch == channel for _, ch in e["observables"])]
    return {
        "question": ("Which dark-matter models in the registry can't be tested against "
                     "Lyman-alpha forest data yet, and what single missing capability would "
                     "unblock the most of them?"),
        "definition": LYMAN_ALPHA_DEFINITION,
        "registry_dir": str(reg.root),
        "n_cards": len(reg.index),
        "n_models_with_channel": len(with_channel),
        "n_blocked": len(blocked),
        "top_capability": ranking[0] if ranking else None,
        "top_capability_n_models": len(by_theme[ranking[0]]) if ranking else 0,
        "top_capability_n_fully_unblocked": len(fully[ranking[0]]) if ranking else 0,
        "themes": [{"theme": t, "n_models": len(by_theme[t]), "n_fully_unblocked": len(fully[t]),
                    "model_ids": sorted(by_theme[t])} for t in ranking],
        "blocked_model_ids": sorted(blocked),
    }


def load_ground_truth(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ----------------------------------------------------------------- graders


@dataclass
class Grade:
    """A score in [0, 1] and the individual checks behind it."""
    score: float
    checks: dict = field(default_factory=dict)


def mentions_theme(answer: str, theme: str, threshold: float = 0.6) -> bool:
    """True if most of the theme's content words (4+ letters) appear in the answer."""
    words = [w for w in re.findall(r"[a-z]{4,}", theme.lower())]
    text = answer.lower()
    return bool(words) and sum(w in text for w in words) / len(words) >= threshold


def grade_lyman_alpha(answer: str, truth: dict) -> Grade:
    """Grade an answer to the headline question against `lyman_alpha_ground_truth`.

    Three checks, equally weighted: the top capability is named; the cited
    model IDs are correct (precision); the number of blocked models is stated.
    Also reports recall of the blocked IDs. A known limitation: an answer that
    lists every theme will pass the first check.
    """
    truth_ids = set(truth["blocked_model_ids"])
    cited = set(find_model_ids(answer))
    right = cited & truth_ids
    without_ids = MODEL_ID_RE.sub(" ", answer)  # digits inside IDs are not counts
    checks = {
        "top_capability_named": mentions_theme(answer, truth["top_capability"]),
        "id_precision": len(right) / len(cited) if cited else 0.0,
        "id_recall": len(right) / len(truth_ids) if truth_ids else 0.0,
        "count_stated": str(truth["n_blocked"]) in re.findall(r"\d+", without_ids),
        "wrong_ids": sorted(cited - truth_ids),
    }
    score = (checks["top_capability_named"] + checks["id_precision"] + checks["count_stated"]) / 3
    return Grade(round(score, 3), checks)


def grade_model_gaps(answer: str, model_id: str, reg: Registry | None = None) -> Grade:
    """Grade an answer to the single-model question: does it name the model's
    gap types and the observables its gaps block?"""
    reg = reg or default_registry()
    gaps = reg.gaps[model_id]["capability_gaps"].get("gaps") or []
    text = answer.lower()
    types = {g["gap_type"] for g in gaps}
    observables = {o for g in gaps for o in g.get("blocking_observables") or []}
    checks = {
        "gap_types_named": sum(t in text for t in types) / len(types) if types else 1.0,
        "observables_named": (sum(o.lower() in text for o in observables) / len(observables)
                              if observables else 1.0),
        "model_id_cited": model_id in answer,
    }
    score = (checks["gap_types_named"] + checks["observables_named"] + checks["model_id_cited"]) / 3
    return Grade(round(score, 3), checks)


def grade_against_roadmap(themes: list[str], reg: Registry | None = None, top_n: int = 5) -> Grade:
    """Compare an agent's ranked list of capability themes with the top of
    capability_gap_roadmap.jsonl (ranked by weight): the overlap fraction."""
    reg = reg or default_registry()
    rows = sorted(reg.roadmap, key=lambda r: -r["weight"])
    reference = list(dict.fromkeys(r["theme"] for r in rows))[:top_n]
    hits = [t for t in themes[:top_n] if t in reference]
    return Grade(round(len(hits) / top_n, 3), {"reference": reference, "hits": hits})


# ---------------------------------------------------------------- variance


@dataclass
class VarianceReport:
    scores: list[float]
    mean: float
    stdev: float
    runs: list = field(repr=False, default_factory=list)


def run_n_times(run: Callable[[int], object], grade: Callable[[object], Grade],
                n: int = 5) -> VarianceReport:
    """Run an agent `n` times (run(i) -> result), grade each result, summarise.

    With a real model the scores vary from run to run; report the spread,
    not just the best run.
    """
    runs = [run(i) for i in range(n)]
    scores = [grade(r).score for r in runs]
    stdev = statistics.stdev(scores) if len(scores) > 1 else 0.0
    return VarianceReport(scores, round(statistics.mean(scores), 3), round(stdev, 3), runs)
