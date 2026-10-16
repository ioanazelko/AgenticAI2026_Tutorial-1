# DarkMatterFM BSM registry schemas

This folder contains the JSON Schema/YAML schema files for structured BSM dark-matter model cards.

## Files

- `bsm_model.schema.yaml`: top-level model-card schema.
- `common.schema.yaml`: reusable definitions for parameters, assumptions, validity entries, robustness, relevance, and agent warnings.
- `observable.schema.yaml`: reusable observable-channel entries.
- `constraint.schema.yaml`: reusable constraint entries.
- `route.schema.yaml`: theory-to-observable routing entries.
- `provenance.schema.yaml`: provenance, source, extraction, evidence, review, and versioning metadata.
- `code.schema.yaml`: associated code, repositories, notebooks, environments, validation, and reproducibility metadata.

## Design notes

The top-level schema keeps physics content separate from provenance, computational implementation, and agent-failure-mode warnings.  
Every model card should be able to answer:

1. What is the model?
2. What assumptions make it valid?
3. Which observables and constraints apply?
4. Which routes, codes, emulators, and likelihoods should be used?
5. What is the provenance and review status of each claim?
6. Where could an automated agent make a scientifically dangerous mistake?

## Validation

These schemas use JSON Schema draft 2020-12 syntax while being stored as YAML.
The files were parsed as YAML and checked as draft 2020-12 schemas. Local cross-file `$ref` targets were also checked for existence.
