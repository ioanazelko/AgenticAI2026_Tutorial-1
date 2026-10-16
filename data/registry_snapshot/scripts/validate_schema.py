#!/usr/bin/env python3
"""Validate a BSM dark-matter model card against the schema.

Usage:
    python scripts/validate_schema.py registry/models/thermal_wdm/example.yaml

Dependencies:
    pip install jsonschema pyyaml referencing
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SCHEMA_FILES = [
    "common.schema.yaml",
    "observable.schema.yaml",
    "constraint.schema.yaml",
    "route.schema.yaml",
    "provenance.schema.yaml",
    "code.schema.yaml",
    "bsm_model.schema.yaml",
]


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"{path} is empty")
    return data


def build_registry(schema_dir: Path) -> tuple[dict, Registry]:
    registry = Registry()
    schemas = {}

    for name in SCHEMA_FILES:
        schema_path = schema_dir / name
        schema = load_yaml(schema_path)
        schema_id = schema.get("$id")
        if not schema_id:
            raise ValueError(f"{schema_path} has no $id")
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(schema_id, resource)
        registry = registry.with_resource(name, resource)
        schemas[name] = schema

    return schemas["bsm_model.schema.yaml"], registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_card", type=Path)
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("registry/schemas"),
        help="Directory containing schema YAML files.",
    )
    args = parser.parse_args()

    model_card = load_yaml(args.model_card)
    # Top-level keys starting with "_" are envelope metadata written by
    # split_outputs.py (shard, paper id, enrichment flags), not card content.
    if isinstance(model_card, dict):
        model_card = {k: v for k, v in model_card.items() if not k.startswith("_")}
    schema, registry = build_registry(args.schema_dir)

    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(model_card), key=lambda e: list(e.path))

    if not errors:
        print(f"VALID: {args.model_card}")
        return 0

    print(f"INVALID: {args.model_card}\n")
    for error in errors:
        path = ".".join(str(p) for p in error.path) or "<root>"
        print(f"- {path}: {error.message}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
