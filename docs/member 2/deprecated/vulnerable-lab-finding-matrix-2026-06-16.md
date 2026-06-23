# Vulnerable Lab Finding Matrix - 2026-06-16

This report was generated after the latest semantic-similarity changes:

- semantic rule expansion is limited by an allowlist
- per-rule thresholds are used
- action gates are applied to semantic rule matches
- benign semantic fixtures were added to guard against false positives

The scan used the current default detector registry against:

```text
vulnerable-lab/expanded-52/*/tools.json
```

## Verification

```bash
pytest tests/integration/test_scan_vulnerable_lab.py
```

Result:

```text
58 passed
```

The full project test suite was also run after installing `uvicorn[standard]`:

```bash
pytest
```

Result:

```text
162 passed
```

## Summary

- Cases scanned: 52
- Cases with findings: 12
- Cases without findings: 40
- Total findings: 16
- critical: 6
- high: 8
- medium: 2
- low: 0
- info: 0

## Category Coverage

| Category | Detected Cases | Total Cases |
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

## Case Matrix

| Case | Scenario | Category | Difficulty | Findings | Finding IDs |
|---|---|---|---|---:|---|
| LAB-001 | `LAB-001-plain-env-secret` | MCP01 Secret Exposure | Low | 0 | - |
| LAB-002 | `LAB-002-print-environment` | MCP01 Secret Exposure | Low | 0 | - |
| LAB-003 | `LAB-003-sensitive-input-schema` | MCP01 Secret Exposure | Medium | 0 | - |
| LAB-004 | `LAB-004-unredacted-report-secret` | MCP01 Secret Exposure | Medium | 0 | - |
| LAB-005 | `LAB-005-file-read-webhook` | MCP01 Secret Exposure | High | 1 | `MCP03-secret_exfiltration` |
| LAB-006 | `LAB-006-calendar-secret-injection` | MCP01 Secret Exposure | High | 1 | `MCP03-secret_exfiltration` |
| LAB-007 | `LAB-007-remote-no-auth` | MCP02 Authentication and Authorization | Low | 0 | - |
| LAB-008 | `LAB-008-optional-token` | MCP02 Authentication and Authorization | Medium | 0 | - |
| LAB-009 | `LAB-009-user-id-authorization` | MCP02 Authentication and Authorization | High | 0 | - |
| LAB-010 | `LAB-010-untrusted-oauth-origin` | MCP02 Authentication and Authorization | High | 0 | - |
| LAB-011 | `LAB-011-hidden-description` | MCP03 Tool Poisoning | Low | 4 | `MCP03-covert_behavior`, `MCP03-ignore_previous_instructions`, `MCP03-secret_exfiltration` |
| LAB-012 | `LAB-012-title-poisoning` | MCP03 Tool Poisoning | Low | 0 | - |
| LAB-013 | `LAB-013-schema-poisoning` | MCP03 Tool Poisoning | Medium | 1 | `MCP03-schema_instruction_poisoning` |
| LAB-014 | `LAB-014-meta-poisoning` | MCP03 Tool Poisoning | Medium | 0 | - |
| LAB-015 | `LAB-015-annotation-mismatch` | MCP03 Tool Poisoning | Medium | 0 | - |
| LAB-016 | `LAB-016-base64-instruction` | MCP03 Tool Poisoning | Medium | 1 | `mcp03-base64-3938062d6cb6` |
| LAB-017 | `LAB-017-zero-width-obfuscation` | MCP03 Tool Poisoning | Medium | 1 | `mcp03-zero-width-d55fb1dd4a8b` |
| LAB-018 | `LAB-018-markdown-hidden-link` | MCP03 Tool Poisoning | Medium | 2 | `MCP03-secret_exfiltration`, `mcp03-md-link-c42453a0ab18` |
| LAB-019 | `LAB-019-forced-tool-use` | MCP03 Tool Poisoning | Medium | 1 | `MCP03-tool_priority_manipulation` |
| LAB-020 | `LAB-020-cross-tool-admin` | MCP03 Tool Poisoning | High | 1 | `MCP03-tool_priority_manipulation` |
| LAB-021 | `LAB-021-multi-tool-exfiltration` | MCP03 Tool Poisoning | High | 1 | `MCP03-secret_exfiltration` |
| LAB-022 | `LAB-022-metadata-rug-pull` | MCP03 Tool Poisoning | High | 0 | - |
| LAB-023 | `LAB-023-npx-latest` | MCP04 Supply Chain Risk | Low | 0 | - |
| LAB-024 | `LAB-024-docker-latest` | MCP04 Supply Chain Risk | Low | 0 | - |
| LAB-025 | `LAB-025-curl-bash` | MCP04 Supply Chain Risk | Medium | 0 | - |
| LAB-026 | `LAB-026-typosquat-package` | MCP04 Supply Chain Risk | Medium | 0 | - |
| LAB-027 | `LAB-027-registry-source-drift` | MCP04 Supply Chain Risk | High | 0 | - |
| LAB-028 | `LAB-028-binary-url-rug-pull` | MCP04 Supply Chain Risk | High | 0 | - |
| LAB-029 | `LAB-029-run-shell-tool` | MCP05 Command Injection | Low | 0 | - |
| LAB-030 | `LAB-030-python-os-system` | MCP05 Command Injection | Low | 0 | - |
| LAB-031 | `LAB-031-subprocess-shell-true` | MCP05 Command Injection | Medium | 0 | - |
| LAB-032 | `LAB-032-node-child-process-exec` | MCP05 Command Injection | Medium | 0 | - |
| LAB-033 | `LAB-033-git-argument-injection` | MCP05 Command Injection | High | 0 | - |
| LAB-034 | `LAB-034-calendar-command-execution` | MCP05 Command Injection | High | 0 | - |
| LAB-035 | `LAB-035-overbroad-filesystem` | MCP06 Excessive Tool Permissions | Low | 0 | - |
| LAB-036 | `LAB-036-calendar-delete-permission` | MCP06 Excessive Tool Permissions | Medium | 0 | - |
| LAB-037 | `LAB-037-read-and-send-permissions` | MCP06 Excessive Tool Permissions | High | 1 | `MCP03-secret_exfiltration` |
| LAB-038 | `LAB-038-external-summarization-api` | MCP07 Data Boundary Violation | Medium | 0 | - |
| LAB-039 | `LAB-039-external-doc-repo-exfiltration` | MCP07 Data Boundary Violation | High | 1 | `MCP03-privileged_resource_access` |
| LAB-040 | `LAB-040-no-audit-destructive` | MCP08 Audit and Telemetry | Low | 0 | - |
| LAB-041 | `LAB-041-report-coverage-gap` | MCP08 Audit and Telemetry | Low | 0 | - |
| LAB-042 | `LAB-042-sensitive-log-exposure` | MCP08 Audit and Telemetry | Medium | 0 | - |
| LAB-043 | `LAB-043-missing-confirmation` | MCP08 Audit and Telemetry | Medium | 0 | - |
| LAB-044 | `LAB-044-chain-without-audit` | MCP08 Audit and Telemetry | High | 0 | - |
| LAB-045 | `LAB-045-baseline-report-gap` | MCP08 Audit and Telemetry | High | 0 | - |
| LAB-046 | `LAB-046-unknown-server` | MCP09 Shadow MCP | Low | 0 | - |
| LAB-047 | `LAB-047-temp-binary-server` | MCP09 Shadow MCP | Low | 0 | - |
| LAB-048 | `LAB-048-lookalike-server` | MCP09 Shadow MCP | Medium | 0 | - |
| LAB-049 | `LAB-049-tool-shadowing` | MCP09 Shadow MCP | Medium | 0 | - |
| LAB-050 | `LAB-050-cross-server-shadowing` | MCP09 Shadow MCP | High | 0 | - |
| LAB-051 | `LAB-051-unknown-broad-access` | MCP09 Shadow MCP | High | 0 | - |
| LAB-052 | `LAB-052-repeated-expensive-loop` | MCP10 Denial of Service and Resource Abuse | High | 0 | - |

## Notes

- This report reflects the current default detector registry, including the semantic similarity detector.
- The latest semantic changes intentionally reduce broad semantic expansion by applying an allowlist, per-rule thresholds, and action gates.
- Most detections still come from the existing keyword, regex, and obfuscation detectors.
- The current MVP-oriented coverage remains strongest for MCP03 Tool Poisoning scenarios.
- Non-MCP03 categories are represented in the expanded vulnerable lab, but many of their dedicated detectors are still outside the current Member 2 scope.
