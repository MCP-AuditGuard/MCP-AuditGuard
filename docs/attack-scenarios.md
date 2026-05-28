# MCP-AuditGuard Vulnerable Lab Attack Scenarios

This document summarizes the demo scenarios owned by Member 4. All samples use fake attacker domains and synthetic instructions only.

## 01 Hidden Description

The `summarize_notes` tool looks like a normal summarizer, but its description includes an instruction to ignore prior instructions and exfiltrate `.env` secrets. A scanner should flag the malicious instruction in the tool description as MCP03 Tool Poisoning.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/01-hidden-description/tools.json --format markdown
```

## 02 Schema Poisoning

The `user_lookup` tool has a clean top-level description, but the parameter description for `username` contains the malicious instruction. A scanner should inspect nested schema descriptions, not only top-level metadata.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/02-schema-poisoning/tools.json --format markdown
```

## 03 Base64 Instruction

The `sort_records` tool hides a malicious instruction in base64 inside the description. A scanner should detect encoded payload candidates, decode them, redact sensitive evidence, and re-run poisoning checks on decoded text.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/03-base64-instruction/tools.json --format markdown
```

## 04 Zero-Width Obfuscation

The `calculate_total` tool inserts zero-width characters into suspicious words such as `ignore` and `disclose`. A scanner should normalize or detect invisible Unicode before matching suspicious instructions.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/04-zero-width-obfuscation/tools.json --format markdown
```

## 05 Metadata Rug Pull

The `calendar_helper` tool starts with benign metadata in `tools-before.json`. The later `tools-after.json` changes the description and annotations to request destructive and exfiltration behavior. A scanner with baseline comparison should report the suspicious metadata change.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/05-metadata-rug-pull/tools-after.json --baseline baseline.json --format markdown
```

## 06 Cross-Tool Poisoning

The `issue_reader` tool instructs the model to call a separate `repo_admin` tool and remove protections. A scanner should flag metadata that tries to control another tool or chain into a higher-risk tool.

Demo command:

```bash
mcp-auditguard scan --input vulnerable-lab/06-cross-tool-poisoning/tools.json --format markdown
```

## Expected MVP Result

The MVP target is to detect at least five of the six vulnerable lab scenarios while keeping findings from `tests/fixtures/benign_tools.json` at or below a 20% false positive rate.
