# General Benign Scenario Set

This document describes the 100 market-like benign scenarios under
`vulnerable-lab/benign-lab/general-benign-100/`.

Unlike `mcp03-benign-100`, this set is not built around specific detector rules. It models normal MCP
server types that could plausibly exist in a public or enterprise MCP marketplace. Its purpose is to
support a more objective false-positive check for AuditGuard's market usefulness.

Expected result for each scenario:

```text
No finding from default detectors.
```

## Fixture Structure

Each scenario has its own `tools.json` file:

```text
vulnerable-lab/benign-lab/general-benign-100/
  filesystem-document-productivity/BENIGN-101-workspace-file-index/tools.json
  developer-workflow/BENIGN-111-repository-issue-lister/tools.json
  ...
  monitoring-audit-observability/BENIGN-200-on-call-schedule-view/tools.json
```

Each tool contains:

- `name`
- `title`
- `description`
- `inputSchema`
- `annotations`
- `_meta.benign_id`
- `_meta.benign_set`
- `_meta.market_group`
- `_meta.market_context`
- `_meta.expected_result`
- `_meta.rationale`

## Market Groups

| Group | Count | Why this matters |
| --- | ---: | --- |
| Filesystem and Document Productivity | 10 | Common file, document, note, and workspace helpers. |
| Developer Workflow | 10 | Git, issue, pull request, CI, package, and code review helpers. |
| Calendar, Email, and Contacts | 10 | Scheduling, inbox, contact, and communication tools. |
| Database, Analytics, and BI | 10 | Read-only dashboards, catalogs, metrics, and reporting tools. |
| Cloud and SaaS Admin Read-only | 10 | Normal admin dashboards for resources, users, billing, policy, and logs. |
| Search, Knowledge, and RAG | 10 | Enterprise search, knowledge base, glossary, source, and training helpers. |
| Design, Media, and Content | 10 | Asset, transcript, CMS, localization, and content workflow tools. |
| Commerce, CRM, and Support | 10 | Customer, support, product catalog, order, and account workflow tools. |
| Data Transformation and ETL | 10 | CSV, schema, import, conversion, and scheduled data workflow helpers. |
| Monitoring, Audit, and Observability | 10 | Uptime, alert, log, incident, SLO, trace, and on-call tools. |

## Evaluation

The integration test `test_general_benign_lab_false_positive_rate_when_scanner_is_available` scans
all 100 general benign scenarios with the default detector registry and asserts that the
false-positive rate is at most 5%.

This set is intended to complement vulnerable scenarios. Vulnerable cases measure recall; this
benign set measures whether AuditGuard stays quiet on ordinary MCP server metadata.
