# Snyk-Aligned MCP03 Evaluation Set 100

This benchmark is separate from `vulnerable-lab`. It is intended for MCP03-only comparison and gap analysis against Snyk Agent Scan's public issue taxonomy.

## Scope

- MCP03 Tool Poisoning only.
- Static MCP `tools.json` metadata fixtures.
- No real secrets, no live network endpoints, and no executable exploit behavior.
- Synthetic examples only; labels are for scanner evaluation.

## Alignment

The category layout follows public Snyk Agent Scan issue categories that overlap with MCP03-style tool metadata risk:

- E001: prompt injection in tool description.
- E002: cross-server tool reference / tool shadowing.
- W001: suspicious words in tool description.
- W021: hidden Unicode characters.

The benchmark also includes MCP03 schema/meta poisoning cases because AuditGuard specifically inspects MCP metadata locations beyond the main description, and benign controls for false-positive measurement.

## Layout

Each scenario has:

- `tools.json`: MCP listTools-style fixture.
- `label.json`: expected label and evaluation metadata.

The top-level `manifest.json` contains all scenario metadata and category counts.

## Category Counts

| Category | Count |
| --- | ---: |
| 01-E001-direct-prompt-injection | 20 |
| 02-E001-indirect-deceptive-instruction | 15 |
| 03-E002-tool-shadowing | 15 |
| 04-W001-suspicious-wording | 10 |
| 05-W021-hidden-unicode | 10 |
| 06-MCP03-schema-meta-poisoning | 15 |
| 07-benign-controls | 15 |
| Total | 100 |

## Suggested Metrics

- MCP03 recall on malicious/risky cases.
- False positive rate on benign controls.
- Per-category recall.
- Location coverage: description, schema, metadata, annotation, title.
- Evidence quality: whether the scanner explains why the case was flagged.

## Interpretation

This benchmark should not be used to claim broad superiority over Snyk Agent Scan. Snyk Agent Scan covers a wider agent-security surface. This set asks a narrower question: how well does AuditGuard handle MCP03 tool-metadata risks that are aligned with Snyk's public MCP issue categories?
