# Vulnerable Lab Planned Coverage

This document classifies whether each `vulnerable-lab/expanded-52` case is in the current MCP-AuditGuard planned detection scope.

## Classification Basis

The current project plan says:

- MVP focus: MCP03 Tool Poisoning.
- Planned expansion: MCP01, MCP04, MCP05, MCP08, and MCP09.
- Remaining MCP02, MCP06, MCP07, and MCP10 scenarios exist in the lab set as broader MCP security coverage, but are not explicitly listed in the current expansion focus.

The local semantic similarity detector now includes signatures for MCP01, MCP04, MCP05, MCP07, and MCP10, but this document classifies scope from the project plan rather than from current scan output.

## Summary

- Total lab cases: 52
- Explicitly planned detection scope: 42
- Broader/future coverage cases: 10

## Planned Scope By Category

| Category | Cases | Planning Status | Notes |
|---|---:|---|---|
| MCP01 Secret Exposure | 6 | Planned expansion | Covered by secret exposure, exfiltration, redaction, and semantic secret signatures. |
| MCP02 Authentication and Authorization | 4 | Broader/future coverage | Present in lab, but not explicitly listed in current MVP or expansion focus. |
| MCP03 Tool Poisoning | 12 | MVP scope | Primary project focus. |
| MCP04 Supply Chain Risk | 6 | Planned expansion | Present in expansion plan; detector work is still partial. |
| MCP05 Command Injection | 6 | Planned expansion | Present in expansion plan; semantic detector now adds partial coverage. |
| MCP06 Excessive Tool Permissions | 3 | Broader/future coverage | Present in lab, but not explicitly listed in current MVP or expansion focus. |
| MCP07 Data Boundary Violation | 2 | Broader/future coverage | Present in lab; semantic signatures include this as an early extension. |
| MCP08 Audit and Telemetry | 6 | Planned expansion | Present in expansion plan; detector work is still partial. |
| MCP09 Shadow MCP | 6 | Planned expansion | Present in expansion plan; detector work is still partial. |
| MCP10 Denial of Service and Resource Abuse | 1 | Broader/future coverage | Present in lab; semantic signatures include this as an early extension. |

## Case Matrix

| Case | Scenario | Category | Planned Status | Rationale |
|---|---|---|---|---|
| LAB-001 | `LAB-001-plain-env-secret` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-002 | `LAB-002-print-environment` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-003 | `LAB-003-sensitive-input-schema` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-004 | `LAB-004-unredacted-report-secret` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-005 | `LAB-005-file-read-webhook` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-006 | `LAB-006-calendar-secret-injection` | MCP01 Secret Exposure | Planned expansion | MCP01 is explicitly listed in the expansion focus. |
| LAB-007 | `LAB-007-remote-no-auth` | MCP02 Authentication and Authorization | Broader/future coverage | MCP02 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-008 | `LAB-008-optional-token` | MCP02 Authentication and Authorization | Broader/future coverage | MCP02 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-009 | `LAB-009-user-id-authorization` | MCP02 Authentication and Authorization | Broader/future coverage | MCP02 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-010 | `LAB-010-untrusted-oauth-origin` | MCP02 Authentication and Authorization | Broader/future coverage | MCP02 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-011 | `LAB-011-hidden-description` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-012 | `LAB-012-title-poisoning` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-013 | `LAB-013-schema-poisoning` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-014 | `LAB-014-meta-poisoning` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-015 | `LAB-015-annotation-mismatch` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-016 | `LAB-016-base64-instruction` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-017 | `LAB-017-zero-width-obfuscation` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-018 | `LAB-018-markdown-hidden-link` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-019 | `LAB-019-forced-tool-use` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-020 | `LAB-020-cross-tool-admin` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-021 | `LAB-021-multi-tool-exfiltration` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-022 | `LAB-022-metadata-rug-pull` | MCP03 Tool Poisoning | MVP scope | MCP03 Tool Poisoning is the primary MVP focus. |
| LAB-023 | `LAB-023-npx-latest` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-024 | `LAB-024-docker-latest` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-025 | `LAB-025-curl-bash` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-026 | `LAB-026-typosquat-package` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-027 | `LAB-027-registry-source-drift` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-028 | `LAB-028-binary-url-rug-pull` | MCP04 Supply Chain Risk | Planned expansion | MCP04 is explicitly listed in the expansion focus. |
| LAB-029 | `LAB-029-run-shell-tool` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-030 | `LAB-030-python-os-system` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-031 | `LAB-031-subprocess-shell-true` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-032 | `LAB-032-node-child-process-exec` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-033 | `LAB-033-git-argument-injection` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-034 | `LAB-034-calendar-command-execution` | MCP05 Command Injection | Planned expansion | MCP05 is explicitly listed in the expansion focus. |
| LAB-035 | `LAB-035-overbroad-filesystem` | MCP06 Excessive Tool Permissions | Broader/future coverage | MCP06 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-036 | `LAB-036-calendar-delete-permission` | MCP06 Excessive Tool Permissions | Broader/future coverage | MCP06 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-037 | `LAB-037-read-and-send-permissions` | MCP06 Excessive Tool Permissions | Broader/future coverage | MCP06 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-038 | `LAB-038-external-summarization-api` | MCP07 Data Boundary Violation | Broader/future coverage | MCP07 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-039 | `LAB-039-external-doc-repo-exfiltration` | MCP07 Data Boundary Violation | Broader/future coverage | MCP07 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |
| LAB-040 | `LAB-040-no-audit-destructive` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-041 | `LAB-041-report-coverage-gap` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-042 | `LAB-042-sensitive-log-exposure` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-043 | `LAB-043-missing-confirmation` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-044 | `LAB-044-chain-without-audit` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-045 | `LAB-045-baseline-report-gap` | MCP08 Audit and Telemetry | Planned expansion | MCP08 is explicitly listed in the expansion focus. |
| LAB-046 | `LAB-046-unknown-server` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-047 | `LAB-047-temp-binary-server` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-048 | `LAB-048-lookalike-server` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-049 | `LAB-049-tool-shadowing` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-050 | `LAB-050-cross-server-shadowing` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-051 | `LAB-051-unknown-broad-access` | MCP09 Shadow MCP | Planned expansion | MCP09 is explicitly listed in the expansion focus. |
| LAB-052 | `LAB-052-repeated-expensive-loop` | MCP10 Denial of Service and Resource Abuse | Broader/future coverage | MCP10 is represented in the lab, but not explicitly listed in the current MVP or expansion focus. |

## Interpretation

Most vulnerable lab cases are intentionally aligned with current project plans. The strongest alignment is MCP03, because it is the MVP target, followed by MCP01, MCP04, MCP05, MCP08, and MCP09, because they are named in the expansion plan.

MCP02, MCP06, MCP07, and MCP10 should be treated as broader benchmark coverage. They are useful for future product comparison, but they should not be presented as fully planned detector obligations unless the team expands the formal scope.

## Current Implementation Note

Current detectors already provide partial coverage beyond the written plan:

- MCP07 LAB-039 can be caught by `privileged_resource_access`.
- MCP10 has an early semantic signature, but this should be considered experimental until formalized.
- MCP01 and MCP05 now have semantic similarity support when the local embedding model is available.

These implementation details do not change the planning classification above.
