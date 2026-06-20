# Test Markdown Comparison Summary - 2026-06-16

This document summarizes and compares the current test-related Markdown files under `docs/`.

## Source Documents

| File | Purpose |
|---|---|
| `docs/vulnerable-lab-finding-matrix.md` | Baseline vulnerable-lab scan result before semantic experiments. |
| `docs/vulnerable-lab-finding-matrix-semantic.md` | Broad local embedding semantic-signature scan result. |
| `docs/vulnerable-lab-finding-matrix-keyword-semantic.md` | Keyword-to-embedding semantic expansion scan result. |
| `docs/vulnerable-lab-finding-matrix-2026-06-16.md` | Latest conservative semantic result after allowlist, per-rule thresholds, and action gates. |
| `docs/semantic-improvement-summary.ko.md` | Korean summary comparing baseline and broad semantic-signature results. |
| `docs/keyword-semantic-improvement-summary.ko.md` | Korean summary comparing baseline and keyword-semantic expansion results. |
| `docs/vulnerable-lab-planned-coverage.md` | Planning document that maps 52 vulnerable-lab cases to current or future project scope. |
| `docs/test-scenario-expansion-plan.md` | Scenario design document for the expanded 52-case vulnerable lab. |

## High-Level Comparison

| Result Set | Cases Scanned | Cases With Findings | Detection Rate | Total Findings | Critical | High | Medium | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline matrix | 52 | 12 | 23.1% | 16 | 6 | 8 | 2 | Existing keyword, regex, obfuscation, and rule-based detectors. |
| Broad semantic matrix | 52 | 16 | 30.8% | 20 | 7 | 11 | 2 | Added broad semantic signatures for MCP01 and MCP05. |
| Keyword-semantic matrix | 52 | 14 | 26.9% | 20 | 6 | 12 | 2 | Expanded existing keyword rules into semantic similarity seeds. |
| Latest 2026-06-16 matrix | 52 | 12 | 23.1% | 16 | 6 | 8 | 2 | Conservative semantic settings reduce broad expansion and false-positive risk. |

## Interpretation

The broad semantic experiment produced the highest vulnerable-lab detection count:

```text
12 cases -> 16 cases
23.1% -> 30.8%
```

That improvement came mainly from semantic signatures that were not limited to the current Member 2 MCP03 scope:

| Added Case | Category | Added Finding |
|---|---|---|
| LAB-001 | MCP01 Secret Exposure | `MCP01-semantic_plain_secret_exposure` |
| LAB-002 | MCP01 Secret Exposure | `MCP01-semantic_environment_dump` |
| LAB-029 | MCP05 Command Injection | `MCP05-semantic_command_execution` |
| LAB-030 | MCP05 Command Injection | `MCP05-semantic_command_execution` |

The keyword-semantic experiment improved fewer cases:

```text
12 cases -> 14 cases
23.1% -> 26.9%
```

It added semantic matches based on existing keyword rules, but it also showed false-positive risk in general-language schema fields.

## Case-Level Differences

| Case | Baseline | Broad Semantic | Keyword Semantic | Latest 2026-06-16 | What Changed |
|---|---:|---:|---:|---:|---|
| LAB-001 | 0 | 1 | 0 | 0 | Broad semantic caught plain secret exposure, but latest conservative settings do not include this broad signature path as an effective hit. |
| LAB-002 | 0 | 1 | 0 | 0 | Broad semantic caught environment dumping, but latest conservative settings avoid broad MCP01 semantic expansion. |
| LAB-014 | 0 | 0 | 1 | 0 | Keyword-semantic caught `_meta` poisoning, but latest action-gated allowlist no longer reports it. |
| LAB-019 | 1 | 1 | 2 | 1 | Keyword-semantic added an extra schema-related finding that latest settings suppress. |
| LAB-029 | 0 | 1 | 0 | 0 | Broad semantic caught command execution risk, outside current Member 2 MCP03 focus. |
| LAB-030 | 0 | 1 | 1 | 0 | Broad and keyword-semantic variants caught command-related or schema-like signals, but latest conservative settings suppress them. |
| LAB-037 | 1 | 1 | 2 | 1 | Keyword-semantic added a covert-behavior hit on `Secret Sync`; latest settings suppress that likely noisy semantic expansion. |
| LAB-039 | 1 | 1 | 1 | 1 | Stable detection through `MCP03-privileged_resource_access`. |

## Latest Conservative Semantic Result

The latest result intentionally returns to the baseline-level case count:

```text
Cases with findings: 12
Total findings: 16
```

This is expected because the latest semantic work prioritized precision over recall:

- semantic rule expansion is allowlisted
- only `ignore_previous_instructions` and `tool_priority_manipulation` are expanded from Member 2 keyword rules
- `schema_instruction_poisoning` and `covert_behavior` are excluded from semantic expansion
- per-rule thresholds are used
- action gates must pass before semantic rule findings are created
- benign semantic fixtures were added to verify zero false positives for common `user`, `input`, `request`, and `tool` language

## Project Scope Comparison

`docs/vulnerable-lab-planned-coverage.md` classifies the 52 cases as:

```text
Explicitly planned detection scope: 42
Broader/future coverage cases: 10
```

Planning status by category:

| Category | Cases | Planning Status |
|---|---:|---|
| MCP01 Secret Exposure | 6 | Planned expansion |
| MCP02 Authentication and Authorization | 4 | Broader/future coverage |
| MCP03 Tool Poisoning | 12 | MVP scope |
| MCP04 Supply Chain Risk | 6 | Planned expansion |
| MCP05 Command Injection | 6 | Planned expansion |
| MCP06 Excessive Tool Permissions | 3 | Broader/future coverage |
| MCP07 Data Boundary Violation | 2 | Broader/future coverage |
| MCP08 Audit and Telemetry | 6 | Planned expansion |
| MCP09 Shadow MCP | 6 | Planned expansion |
| MCP10 Denial of Service and Resource Abuse | 1 | Broader/future coverage |

The latest result is strongest where the current implementation is strongest:

| Category | Latest Detected Cases | Total Cases |
|---|---:|---:|
| MCP01 Secret Exposure | 2 | 6 |
| MCP02 Authentication and Authorization | 0 | 4 |
| MCP03 Tool Poisoning | 8 | 12 |
| MCP04 Supply Chain Risk | 0 | 6 |
| MCP05 Command Injection | 0 | 6 |
| MCP06 Excessive Tool Permissions | 1 | 3 |
| MCP07 Data Boundary Violation | 1 | 2 |
| MCP08 Audit and Telemetry | 0 | 6 |
| MCP09 Shadow MCP | 0 | 6 |
| MCP10 Denial of Service and Resource Abuse | 0 | 1 |

## Key Takeaways

1. The broad semantic experiment improves recall the most, but part of that improvement comes from categories outside the current Member 2 MCP03 ownership.
2. The keyword-semantic experiment shows that semantic expansion of existing rules can find paraphrases, but broad rule expansion can also create noisy findings.
3. The latest 2026-06-16 result intentionally favors precision by using allowlists, thresholds, and action gates.
4. The latest result is better suited for a conservative MVP presentation because it avoids overstating semantic coverage.
5. The strongest current coverage remains MCP03 Tool Poisoning, which matches the MVP goal in `Agent.md`.

## Recommended Presentation Framing

For the current project presentation, describe the semantic work as a controlled experiment rather than a finalized broad detector:

```text
We tested semantic similarity as a way to expand keyword and regex detection.
The broad semantic version increased vulnerable-lab recall from 12 to 16 detected cases,
but we narrowed it with allowlists, per-rule thresholds, and action gates to reduce false positives.
The latest conservative version preserves baseline-level precision while keeping the architecture ready
for future semantic expansion.
```

This framing is honest and defensible: the project demonstrates a path toward semantic detection without claiming that the current semantic layer is fully tuned for all MCP categories.
