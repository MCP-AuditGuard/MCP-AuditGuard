"""
AuditGuard 사용자 가이드 텍스트.

이 모듈은 Typer 기본 `--help`와 별도로 제공하는 작업 중심 help 문구를 보관한다.
명령어 예시를 `cli.main`이나 `cli.scan`에 직접 두지 않고 분리하면,
CLI entrypoint가 늘어나도 같은 사용 가이드를 재사용할 수 있다.

보안적 의미:
보안 도구는 사용자가 올바른 옵션으로 실행할 수 있어야 효과가 있다.
특히 semantic scan은 로컬 임베딩 모델을 사용하고 기본 scan보다 느릴 수 있으므로,
언제 켜야 하는지 help 문구에서 명확히 안내한다.
"""

AUDITGUARD_HELP_TEXT = """\
MCP-AuditGuard Usage Guide

Purpose
  MCP-AuditGuard scans MCP tool metadata, descriptions, schemas,
  annotations, and baseline changes for Tool Poisoning or suspicious
  metadata tampering.

Basic scan
  auditguard scan --input tools.json
  python -m cli.main scan --input tools.json
  python -m cli.scan scan --input tools.json

Output format
  auditguard scan --input tools.json --format markdown
  auditguard scan --input tools.json --format json

Write a report file
  auditguard scan --input tools.json --output report.md
  auditguard scan --input tools.json --format json --output report.json

Save a baseline
  auditguard scan --input tools.json --save-baseline baseline.json

Compare with a previous baseline
  auditguard scan --input tools-new.json --baseline baseline.json

Semantic Similarity Scan
  auditguard scan --input ./tools.json --enable-semantic --semantic-threshold 0.82
  python -m cli.scan scan --input ./tools.json --enable-semantic --semantic-threshold 0.82
  python -m cli.scan scan --input ./tools.json --enable-semantic --embedding-model-path ./models/all-MiniLM-L6-v2

  Semantic scan detects metadata that is meaningfully similar to known
  Tool Poisoning instructions even when exact keywords are not present.
  It uses a local embedding model and does not send metadata to external APIs.
  It can be slower than the default scan, so enable it when semantic review is needed.

Run local web interface
  auditguard web

Run local web interface for development
  auditguard web --reload

Change web server port
  auditguard web --port 8080

Scan options
  --input, -i              Required path to tools.json.
  --format, -f             Report format: markdown or json.
                           Default: markdown.
  --output, -o             Optional report output path.
  --save-baseline          Optional path to save current metadata baseline.
  --baseline               Optional previous baseline JSON path to compare.
  --enable-semantic        Enable local embedding similarity detection.
  --semantic-threshold     Semantic cosine similarity threshold. Default: 0.82.
  --embedding-model-path   Optional local embedding model path.

Web options
  --host                Web server host. Default: 127.0.0.1.
  --port                Web server port. Default: 8000.
  --reload              Restart automatically when source code changes.

Built-in Typer help
  auditguard --help
  auditguard scan --help
  auditguard web --help
  python -m cli.scan help
"""
