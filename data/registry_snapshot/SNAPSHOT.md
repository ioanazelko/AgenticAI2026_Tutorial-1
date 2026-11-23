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
- `REGISTRY_README.md` is the registry's README at the source commit.
  `REGISTRY_LICENSE` and `REGISTRY_LICENSE-DATA.md` are the registry's license
  files from commit `070cf6c`, and they apply to this subset:
  `scripts/validate_schema.py` is under the MIT License, everything else
  under CC BY 4.0. Credit the registry as `REGISTRY_LICENSE-DATA.md` describes.

Card content is machine-extracted from paper full texts and is not
expert-verified.
