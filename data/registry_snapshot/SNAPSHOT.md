# Registry snapshot

A small subset of **DarkMatterFM-Registry**
(https://github.com/ioanazelko/darkmatterfm-registry, wiki:
https://ioanazelko.github.io/darkmatterfm-registry/) bundled so that every
example in the book runs offline. It is a fallback: for real work, clone the
registry and set `REGISTRY_DIR` to it.

- Source commit: `3459dc0b4d7cf0538a88fae2a8f743833f195938`
- Cards: 123 of 6145 (102 enriched)
- Built by `scripts/make_snapshot.py` (selection rule in its docstring)
- Layout mirrors the registry: `registry/models/cards/...`, the sliced
  `registry/models/*.jsonl`, `registry/schemas/`, `scripts/validate_schema.py`
- In `capability_gap_roadmap.jsonl`, members are filtered to the snapshot and
  `n_gaps`/`n_models` recomputed; `weight` and the other aggregates are
  full-registry values.
- `REGISTRY_README.md` and `REGISTRY_COPYRIGHT.md` are the registry's own
  README and copyright notice; the copyright terms apply to this subset.

Card content is machine-extracted from paper full texts and is not
expert-verified.
