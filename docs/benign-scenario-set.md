# Benign Scenario Sets

This document describes the benign false-positive scenario sets under
`vulnerable-lab/benign-lab/`.

The vulnerable lab checks whether AuditGuard can detect risky MCP metadata. The benign labs check
the opposite question: can AuditGuard avoid flagging normal MCP servers?

There are currently two benign sets:

| Set | Range | Purpose |
| --- | ---: | --- |
| `mcp03-benign-100` | BENIGN-001 to BENIGN-100 | MCP03-focused false-positive controls for security-adjacent words, links, encoding examples, Unicode text, admin terminology, and tool metadata. |
| `general-benign-100` | BENIGN-101 to BENIGN-200 | Market-like normal MCP server examples across common product categories. This set is not designed around detector rules. |

## Current Purpose

AuditGuard currently focuses mainly on MCP03 Tool Poisoning and related obfuscation/encoding
patterns. The first benign set is therefore scoped to MCP03 false-positive testing. The second
benign set broadens the normality check to realistic MCP server types that could exist in a general
marketplace.

Expected result for each benign scenario:

```text
No finding from default MCP03/obfuscation detectors.
```

## Fixture Structure

Each scenario has its own `tools.json` file:

```text
vulnerable-lab/benign-lab/mcp03-benign-100/
  security-doc-language/BENIGN-001-password-policy-summary/tools.json
  benign-ignore-language/BENIGN-011-ignore-empty-rows/tools.json
  ...
  routine-productivity/BENIGN-100-changelog-cleanup/tools.json
```

Each tool contains:

- `name`
- `title`
- `description`
- `inputSchema`
- `annotations`
- `_meta.benign_id`
- `_meta.benign_group`
- `_meta.false_positive_focus`
- `_meta.expected_result`

## Benign Groups

| Group | Count | False-positive risk being tested |
| --- | ---: | --- |
| Security Documentation | 10 | Benign use of words like password, token, secret, credential, and API key. |
| Benign Ignore Language | 10 | Normal uses of "ignore", such as ignoring empty rows or duplicates. |
| Safe Link and Markdown | 10 | Normal Markdown links, image links, citations, and mailto links. |
| Benign Encoded Content | 10 | Harmless base64, URL encoding, HTML entity, hex, ROT13, and escaped JSON examples. |
| Unicode and Multilingual Text | 10 | Normal Unicode, multilingual, fullwidth, accent, emoji, and RTL text. |
| Benign Admin and Permission Language | 10 | Documentation about admin, delete, permissions, audit, and approval without unsafe instruction. |
| Benign Cross-tool Language | 10 | Documentation that mentions multiple tools without instructing the model to call them. |
| Benign Metadata | 10 | Normal `_meta`, schema, annotation, owner, version, and catalog metadata. |
| Benign Secret-like Values | 10 | Fake, masked, dummy, placeholder, and redacted secret-looking values. |
| Routine Productivity Tools | 10 | Everyday summarization, formatting, triage, calendar, FAQ, changelog, and table tools. |

## Evaluation

The integration test `test_benign_lab_false_positive_rate_when_scanner_is_available` scans all
100 benign scenarios with the default detector registry and asserts that the false-positive rate is
at most 5%.

The integration test `test_general_benign_lab_false_positive_rate_when_scanner_is_available` applies
the same 5% false-positive ceiling to the 100 market-like benign scenarios.

This does not prove production readiness by itself, but it gives the team a much stronger precision
signal than the original three-tool `tests/fixtures/benign_tools.json` fixture.
