# MCP-AuditGuard Agent Plan

## Project Overview

MCP-AuditGuard is a security inspection tool for detecting MCP Tool Poisoning and suspicious changes in tool metadata.

The tool analyzes MCP tool metadata, including `name`, `title`, `description`, `inputSchema`, `outputSchema`, `annotations`, and `_meta`. It also compares current scan results against a saved baseline to detect metadata changes, newly added tools, removed tools, and possible rug-pull behavior.

The first MVP focuses on OWASP MCP03 Tool Poisoning. After the MVP, each team member extends the scanner toward another OWASP MCP Top 10 category.

## Technical Stack

```text
Python version: Python 3.14
Package manager: pip
CLI framework: Typer
Test framework: pytest
Data validation: pydantic
YAML loading: PyYAML
```

## Development Rules

The team should keep changes small, testable, and easy to review. Each member should work primarily within their assigned area and avoid changing shared interfaces without coordination.

## Branch Strategy

```text
main: Stable version for final presentation or submission.
develop: Shared integration branch for team development.
feature/member1-core-scanner: Member 1 feature branch.
feature/member2-tool-poisoning: Member 2 feature branch.
feature/member3-obfuscation: Member 3 feature branch.
feature/member4-vulnerable-lab: Member 4 feature branch.
feature/member5-cli-report-baseline: Member 5 feature branch.
```

All feature branches should be merged into `develop` through pull requests. The `main` branch should only receive stable changes that are ready for presentation or submission.

## Pull Request Rules

```text
- Keep each pull request focused on one feature, detector, fixture set, or report change.
- Include a short summary of what changed.
- Include the test command or manual verification steps.
- Mention any remaining work or known limitations.
- Run pytest before requesting review.
- Require at least one teammate review before merging into develop.
```

## File Ownership Rules

Each member is responsible for the files listed in their role section. Changes to another member's owned files should be explained in the pull request.

Shared interface files require extra coordination:

```text
- core/models.py
- core/scanner.py
- ToolMetadata model
- Finding model
- Detector interface
```

Changes to these shared interfaces should be discussed with the team before merging because they can affect every detector, report, fixture, and test.

## Testing and Security Rules

```text
- Every new detector should include unit tests.
- CLI, report, and baseline changes should include integration tests when possible.
- Malicious fixtures should produce findings.
- Benign fixtures should not produce excessive false positives.
- Secret-like values must be redacted before being stored in evidence or reports.
- Decoded payloads must also pass through redaction before reporting.
- Real API keys, tokens, passwords, or private credentials must never be committed.
- Test secrets should use FAKE_, TEST_, or DUMMY_ prefixes.
- Scan results should not be uploaded to external servers.
```

## Core Goals

```text
1. Scan MCP tool metadata from fixture files.
2. Detect suspicious instructions in tool descriptions and schemas.
3. Detect obfuscated or encoded poisoning payloads.
4. Redact secrets from evidence and reports.
5. Generate severity and confidence based findings.
6. Save metadata baselines.
7. Compare later scans against baselines.
8. Generate Markdown and JSON reports.
9. Provide vulnerable MCP lab fixtures for testing and demos.
```

## Expected Repository Structure

```text
mcp-auditguard/
  cli/
    scan.py
    baseline.py
    report.py

  core/
    models.py
    scanner.py
    tool_collector.py
    config_loader.py
    baseline_store.py
    diff_engine.py
    redaction.py
    risk_score.py

  detectors/
    tool_poisoning/
      hidden_instruction.py
      schema_poisoning.py
      metadata_poisoning.py
      cross_tool_instruction.py
      markdown_hidden_link.py
    obfuscation/
      unicode_obfuscation.py
      encoded_payload.py
      homoglyph.py
    integrity/
      metadata_hash_change.py
      new_tool_added.py
      suspicious_tool_removed.py

  rules/
    tool_poisoning.yaml
    suspicious_phrases.yaml
    redaction_patterns.yaml

  reports/
    markdown_report.py
    json_report.py

  vulnerable-lab/
    01-hidden-description/
    02-schema-poisoning/
    03-base64-instruction/
    04-zero-width-obfuscation/
    05-metadata-rug-pull/
    06-cross-tool-poisoning/

  tests/
    unit/
    integration/
    fixtures/
```

## Common Data Models

### ToolMetadata

```python
class ToolMetadata(BaseModel):
    server_name: str
    tool_name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    raw: dict[str, Any]
    source: str | None = None
    metadata_hash: str
    collected_at: datetime
```

### Finding

```python
class Finding(BaseModel):
    id: str
    category: str
    owasp: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: Literal["high", "medium", "low"]
    title: str
    target: str
    location: str
    evidence: str
    redacted: bool
    recommendation: str
    fingerprint: str
```

## Team Roles

## Member 1: Core Scanner and Collector

### Primary Responsibility

Member 1 owns the shared foundation used by all other members.

### MVP Tasks

```text
- Define ToolMetadata model.
- Define Finding model.
- Define Detector interface.
- Implement fixture-based tools.json loader.
- Implement initial MCP config loader.
- Implement scan pipeline.
- Implement detector registry.
- Connect common secret redaction.
```

### Owned Files

```text
core/models.py
core/scanner.py
core/tool_collector.py
core/config_loader.py
core/redaction.py
tests/unit/test_models.py
tests/unit/test_scanner.py
```

### Completion Criteria

```text
- tools.json can be loaded into ToolMetadata objects.
- Registered detectors can run through the scanner.
- Scanner returns a list of Finding objects.
- Secret-like strings in evidence are redacted.
```

### Phase 2 Extension

MCP01 Secret Exposure Scanner

```text
- Detect hardcoded tokens in MCP config env values.
- Detect API keys, GitHub PATs, Slack tokens, and AWS keys.
- Detect metadata text that instructs the model to expose secrets.
```

## Member 2: Tool Poisoning Rule Engine

### Primary Responsibility

Member 2 owns the core MCP03 Tool Poisoning detection logic.

### MVP Tasks

```text
- Implement YAML rule loading.
- Implement keyword and regex based detection.
- Detect hidden instructions.
- Detect schema poisoning.
- Detect title poisoning.
- Detect annotations and _meta poisoning.
- Detect basic cross-tool instructions.
- Assign severity and confidence.
```

### Owned Files

```text
detectors/tool_poisoning/hidden_instruction.py
detectors/tool_poisoning/schema_poisoning.py
detectors/tool_poisoning/metadata_poisoning.py
detectors/tool_poisoning/cross_tool_instruction.py
rules/tool_poisoning.yaml
rules/suspicious_phrases.yaml
tests/unit/test_tool_poisoning.py
```

### Completion Criteria

```text
- Malicious instructions in description are detected.
- Malicious instructions in inputSchema field descriptions are detected.
- Suspicious instructions in annotations and _meta are detected.
- Findings include separated severity and confidence values.
```

### Phase 2 Extension

MCP04 Supply Chain Risk Scanner

```text
- Detect npx package@latest usage.
- Detect uvx latest-style execution.
- Detect docker image:latest usage.
- Detect curl | bash patterns.
- Detect direct execution from GitHub raw URLs.
- Warn when lockfiles or pinned versions are missing.
```

## Member 3: Obfuscation and Encoding Detector

### Primary Responsibility

Member 3 owns bypass detection for payloads hidden through encoding or Unicode tricks.

### MVP Tasks

```text
- Detect zero-width Unicode characters.
- Detect suspicious homoglyph usage.
- Detect instructions hidden in HTML comments.
- Detect Markdown hidden links.
- Detect base64 candidate strings.
- Detect URL encoded strings.
- Decode suspicious payloads and reanalyze them.
- Ensure decoded evidence is redacted.
```

### Owned Files

```text
detectors/obfuscation/unicode_obfuscation.py
detectors/obfuscation/encoded_payload.py
detectors/obfuscation/homoglyph.py
detectors/tool_poisoning/markdown_hidden_link.py
tests/unit/test_obfuscation.py
tests/unit/test_encoded_payload.py
```

### Completion Criteria

```text
- Zero-width Unicode in metadata is detected.
- Base64 encoded malicious instructions are detected.
- URL encoded malicious instructions are detected.
- Decoded payload evidence is redacted before reporting.
```

### Phase 2 Extension

MCP05 Command Injection Scanner

```text
- Detect subprocess(..., shell=True).
- Detect os.system, eval, and exec usage.
- Detect Node.js child_process.exec usage.
- Detect user input command concatenation.
- Detect dangerous tool names such as run_command, shell, terminal, and execute.
```

## Member 4: Vulnerable Lab and Test

### Primary Responsibility

Member 4 owns test data, vulnerable fixtures, integration tests, and demo scenarios.

### MVP Tasks

```text
- Create benign tools.json fixtures.
- Create malicious tools.json fixtures.
- Build six vulnerable lab scenarios.
- Write integration tests.
- Measure malicious recall.
- Measure benign false positive rate.
- Write demo attack scenarios.
```

### Owned Files

```text
vulnerable-lab/01-hidden-description/tools.json
vulnerable-lab/02-schema-poisoning/tools.json
vulnerable-lab/03-base64-instruction/tools.json
vulnerable-lab/04-zero-width-obfuscation/tools.json
vulnerable-lab/05-metadata-rug-pull/tools-before.json
vulnerable-lab/05-metadata-rug-pull/tools-after.json
vulnerable-lab/06-cross-tool-poisoning/tools.json
tests/fixtures/benign_tools.json
tests/fixtures/malicious_tools.json
tests/integration/test_scan_vulnerable_lab.py
docs/attack-scenarios.md
```

### Completion Criteria

```text
- Six vulnerable lab scenarios exist.
- Benign and malicious fixtures are clearly separated.
- At least five of six vulnerable labs are detected.
- Benign fixture false positive rate is 20% or lower.
```

### Phase 2 Extension

MCP09 Shadow MCP Detector

```text
- Detect MCP servers not present in an allowlist.
- Collect MCP server lists from multiple client config files.
- Detect unknown server commands.
- Detect suspicious package names.
```

## Member 5: CLI, Report, and Baseline Diff

### Primary Responsibility

Member 5 owns the user-facing workflow: CLI, reports, baselines, and metadata diffing.

### MVP Tasks

```text
- Implement Typer-based CLI.
- Implement scan command.
- Generate Markdown reports.
- Generate JSON reports.
- Generate metadata hashes.
- Save baselines.
- Compare current scans against previous baselines.
- Detect added, removed, and changed tools.
- Generate rug-pull findings for suspicious metadata changes.
```

### Owned Files

```text
cli/scan.py
cli/baseline.py
reports/markdown_report.py
reports/json_report.py
core/baseline_store.py
core/diff_engine.py
core/risk_score.py
tests/unit/test_baseline_store.py
tests/unit/test_diff_engine.py
tests/integration/test_cli_scan.py
```

### Completion Criteria

```text
- CLI scan command works.
- Markdown and JSON reports can be generated.
- Baselines can be saved.
- Later scans can be compared against baselines.
- Description changes generate rug-pull findings.
```

### Phase 2 Extension

MCP08 Audit and Telemetry Checker

```text
- Check whether destructive tools have audit logging.
- Warn when logging configuration is missing.
- Detect logs that may expose unmasked secrets.
- Display audit coverage in reports.
```

## Four-Week MVP Schedule

## Week 1: Shared Foundation

### Member 1

```text
- Implement models.
- Implement scanner skeleton.
- Implement Detector interface.
```

### Member 2

```text
- Design rule YAML structure.
- Draft suspicious phrase rules.
```

### Member 3

```text
- Design obfuscation detector structure.
- Prepare zero-width and base64 samples.
```

### Member 4

```text
- Create initial benign and malicious fixtures.
- Create vulnerable-lab directory structure.
```

### Member 5

```text
- Create CLI skeleton.
- Create Markdown and JSON report skeletons.
```

### Week 1 Completion Criteria

```text
tools.json input -> scanner runs -> empty report can be generated.
```

## Week 2: Basic MCP03 Detection

### Member 1

```text
- Connect scanner with detector registry.
- Apply common redaction to findings.
```

### Member 2

```text
- Implement description, title, schema, annotations, and _meta detection.
```

### Member 3

```text
- Implement HTML comment detection.
- Implement Markdown hidden link detection.
```

### Member 4

```text
- Complete hidden-description lab.
- Complete schema-poisoning lab.
- Draft unit and integration tests.
```

### Member 5

```text
- Implement finding summary report.
- Implement --input, --format, and --output CLI options.
```

### Week 2 Completion Criteria

```text
Hidden instruction fixtures generate MCP03 findings.
Markdown and JSON reports can be printed or written to file.
```

## Week 3: Obfuscation and Vulnerable Lab Completion

### Member 1

```text
- Stabilize scan pipeline.
- Improve exception handling.
```

### Member 2

```text
- Define severity and confidence rules.
- Implement cross-tool instruction detection.
```

### Member 3

```text
- Implement zero-width detection.
- Implement base64 payload detection.
- Implement URL encoded payload detection.
- Connect decoded payload reanalysis.
```

### Member 4

```text
- Complete six vulnerable lab scenarios.
- Add false positive measurement tests.
```

### Member 5

```text
- Implement baseline storage.
- Implement metadata hash generation.
```

### Week 3 Completion Criteria

```text
At least five of six vulnerable lab scenarios are detected.
Benign fixture false positive rate is 20% or lower.
```

## Week 4: Baseline Diff and Integration

### Member 1

```text
- Fix scanner integration bugs.
- Improve config loader behavior.
```

### Member 2

```text
- Tune rules.
- Finalize recommendation messages.
```

### Member 3

```text
- Reduce obfuscation false positives.
- Verify decoded evidence redaction.
```

### Member 4

```text
- Finalize integration tests.
- Document demo scenarios.
```

### Member 5

```text
- Implement baseline diff.
- Report tool additions, removals, and metadata changes.
- Finalize CLI workflow.
```

### Week 4 Completion Criteria

```text
pytest passes.
scan -> report works.
scan -> save baseline works.
baseline comparison -> metadata change finding works.
README usage instructions are ready.
```

## Team Dependencies

```text
Member 1 provides the shared models, scanner, and detector interface.
Member 2 provides the core Tool Poisoning rule engine.
Member 3 depends on Member 2 for decoded payload reanalysis.
Member 4 provides fixtures and vulnerable labs to all members.
Member 5 integrates scanner output into CLI, reports, and baseline diffing.
```

## Recommended Development Order

```text
1. Member 1 finalizes core models and interfaces.
2. Member 4 provides early fixtures.
3. Members 2 and 3 implement detectors in parallel.
4. Member 5 connects scan results to CLI and reports.
5. All members integrate tests and tune findings.
6. Member 5 completes baseline diff workflow.
```

## CLI Examples

```bash
mcp-auditguard scan --input vulnerable-lab/01-hidden-description/tools.json --format markdown
mcp-auditguard scan --input tools.json --save-baseline baseline.json
mcp-auditguard scan --input tools-new.json --baseline baseline.json --output report.md
```

## MVP Evaluation Criteria

```text
Security:
- Detects major MCP03 Tool Poisoning patterns.
- Redacts secret-like values in evidence.
- Detects metadata changes through baseline comparison.

Accuracy:
- Detects at least five of six vulnerable lab scenarios.
- Keeps benign fixture false positive rate at 20% or lower.

Completeness:
- CLI works.
- Markdown and JSON reports work.
- pytest passes.
- Vulnerable lab demo is available.

Extensibility:
- Detector interface supports new modules.
- Project can expand to MCP01, MCP04, MCP05, MCP08, and MCP09.
```

## Final Presentation Assignment

```text
Member 1:
- MCP metadata collection and scan pipeline.

Member 2:
- Tool Poisoning rules, severity, and confidence.

Member 3:
- Obfuscation and encoded payload detection.

Member 4:
- Vulnerable MCP lab and test results.

Member 5:
- CLI, reports, and baseline diff demo.
```
