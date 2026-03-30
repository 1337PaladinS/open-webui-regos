# threshold_eval.py — Threshold Evaluation Tool

## Status: OBSOLETE (Unused in Production)

This file is an Open WebUI Tool that was an early attempt at exposing threshold evaluation to the LLM via tool-calling. It was abandoned because the base model powering RegOS (Nemotron 3 Nano 30B) does not support tool-calling — the LLM never invoked the tool functions.

**Threshold evaluation is now handled by Feature 9 (Integrated Threshold Eval, v0.14.0)**, which is embedded directly inside `graphrag_filter.py`. The filter detects numeric measurements via regex and evaluates them programmatically before the model sees the message — no tool-calling required.

## Why It Remains in the Repository

The Tools-based approach is architecturally superior for a mature product. When RegOS migrates to a model that supports tool-calling (or when the product has delivered successfully and there's bandwidth to redesign), this file will be rewritten from scratch to meet the product's evolved needs. It is retained as a reference for the API surface (check_threshold, list_thresholds, get_breach_summary) and the ThresholdRegistry pattern.

## What It Contains

- `ThresholdRegistry` — loads and indexes `regulatory_thresholds.json` by parameter, section, and type. Fuzzy matching on parameter names.
- `ThresholdEvaluationService.evaluate()` — takes a parameter + value, returns COMPLIANT / BREACH / BORDERLINE with margin and percentage-of-limit.
- `compute_evidence_hash()` — SHA-256 evidence hashing for tamper-detection.
- Three LLM-callable tool functions: `check_threshold`, `list_thresholds`, `get_breach_summary`.

## Current Production Alternative

See `graphrag_filter.py` (v0.14.0+), Section 9 in `REGOS_CHANGELOG.md`. The integrated approach uses regex-based parameter detection in the inlet, evaluates against the same `regulatory_thresholds.json`, injects determinations into LLM context, and appends a compliance badge in the outlet. Works with any model.
