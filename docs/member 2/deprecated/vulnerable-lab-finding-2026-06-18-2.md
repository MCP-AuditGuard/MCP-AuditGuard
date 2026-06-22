# Vulnerable Lab Finding Report - 2026-06-18 #2

Semantic similarity detector를 끈 상태로 연구용 악성 MCP 서버의 정적 `tools.json` fixture 10개를 스캔한 결과입니다.

## 실행 정보

- 실행 일시: 2026-06-18T16:31:53+09:00
- Git 커밋: `5ef7af1` (fixture는 현재 미커밋 작업 트리에 존재)
- 대상: `tests/fixtures/research_malicious_servers/*/tools.json`
- 출처: Appsecco 9개, Promptfoo 1개
- fixture 검증: `pytest tests/integration/test_research_malicious_server_fixtures.py -q`
- 검증 결과: `1 passed`
- 전체 테스트 결과: `228 passed`
- 로컬 임베딩 의미 탐지: `disabled (mode=false)`
- 스캔 방식: 현재 `create_default_detectors()`의 전체 탐지기에서 semantic detector만 비활성화

## 요약

- 전체 서버 fixture: 10
- 전체 도구: 25
- Finding이 하나 이상 발생한 서버: 1
- Finding이 없는 서버: 9
- 전체 Finding: 1
- Semantic Finding: 0
- 탐지된 서버 비율: 10.0%
- 탐지된 도구 비율: 4.0% (1/25)

> 이 결과는 `tools/list` 정적 메타데이터 탐지율입니다. 구현 코드, 의존성, 전송 계층 및 `tools/call` 결과에만 존재하는 위험은 이 fixture 형식으로 탐지할 수 없습니다.

## 심각도 분포

| Severity | Findings |
|---|---:|
| `critical` | 0 |
| `high` | 0 |
| `medium` | 1 |
| `low` | 0 |
| `info` | 0 |

## OWASP Finding 분포

| OWASP | Findings |
|---|---:|
| `MCP03` | 1 |

## 서버별 결과

| Fixture | Source | Tools | Findings | Finding IDs |
|---|---|---:|---:|---|
| `appsecco-filesystem-workspace-actions` | Appsecco | 4 | 0 | - |
| `appsecco-indirect-prompt-injection` | Appsecco | 2 | 0 | - |
| `appsecco-indirect-prompt-injection-remote` | Appsecco | 2 | 0 | - |
| `appsecco-malicious-code-exec` | Appsecco | 1 | 0 | - |
| `appsecco-malicious-tools` | Appsecco | 2 | 0 | - |
| `appsecco-namespace-typosquatting` | Appsecco | 2 | 0 | - |
| `appsecco-outdated-packages` | Appsecco | 5 | 0 | - |
| `appsecco-secrets-pii` | Appsecco | 3 | 0 | - |
| `appsecco-wikipedia-http-streamable` | Appsecco | 3 | 0 | - |
| `promptfoo-evil-mcp-server` | Promptfoo | 1 | 1 | `MCP03-tool_priority_manipulation` |

## Finding 상세

### Promptfoo Evil MCP Server

| Finding ID | Tool | Severity | Confidence | Location | Evidence |
|---|---|---|---|---|---|
| `MCP03-tool_priority_manipulation` | `record_analytics` | medium | medium | `description` | `ALWAYS CALL THIS TOOL` |

Promptfoo의 도구 설명은 모든 작업 이후 해당 도구를 반드시 호출하도록 강제하므로 기존 cross-tool instruction 규칙이 탐지했습니다.

## 정적 메타데이터 한계

- Appsecco 간접 Prompt Injection 2종은 악성 명령이 도구 호출 후 반환되는 문서 내용에 있습니다.
- Appsecco Malicious Tools는 호출 결과에 조작된 상태 정보와 추가 지시문을 삽입합니다.
- Malicious Code Execution은 구현 내부의 `eval()` 사용이 핵심이며 도구 설명만으로 확정하기 어렵습니다.
- Outdated Packages는 의존성 버전 분석이 필요합니다.
- Secrets and PII는 구현 코드와 로그에 민감정보가 있으며 정적 tool metadata에는 노출되지 않습니다.
- Namespace Typosquatting은 신뢰 가능한 서버·패키지 목록과 이름 비교가 필요합니다.

