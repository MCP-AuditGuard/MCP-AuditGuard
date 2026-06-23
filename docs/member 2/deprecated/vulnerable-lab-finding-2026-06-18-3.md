# Vulnerable Lab Finding Report - 2026-06-18 #3

기본 Detector Registry와 로컬 임베딩 의미 유사도 탐지를 사용하여 연구용 악성 MCP 서버의 정적 `tools.json` fixture 10개를 스캔한 결과입니다.

## 실행 정보

- 실행 일시: 2026-06-18T16:31:53+09:00
- Git 커밋: `5ef7af1` (fixture는 현재 미커밋 작업 트리에 존재)
- 대상: `tests/fixtures/research_malicious_servers/*/tools.json`
- 출처: Appsecco 9개, Promptfoo 1개
- fixture 검증: `pytest tests/integration/test_research_malicious_server_fixtures.py -q`
- 검증 결과: `1 passed`
- 전체 테스트 결과: `228 passed`
- 로컬 임베딩 의미 탐지: `active (mode=auto)`
- 임베딩 모델: `BAAI/bge-small-en-v1.5`
- 로컬 모델 상태: 사용 가능
- 스캔 방식: 현재 `create_default_detectors()`에 등록된 전체 탐지기

## 요약

- 전체 서버 fixture: 10
- 전체 도구: 25
- Finding이 하나 이상 발생한 서버: 1
- Finding이 없는 서버: 9
- 전체 Finding: 1
- Semantic Finding: 0
- 탐지된 서버 비율: 10.0%
- 탐지된 도구 비율: 4.0% (1/25)

> AUTO 실행에서 로컬 모델이 실제로 로드됐지만 threshold를 넘은 semantic match는 없었습니다. 이는 모델 비활성화나 로딩 실패로 인한 결과가 아닙니다.

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

| Fixture | Source | Tools | Findings | Semantic Findings | Finding IDs |
|---|---|---:|---:|---:|---|
| `appsecco-filesystem-workspace-actions` | Appsecco | 4 | 0 | 0 | - |
| `appsecco-indirect-prompt-injection` | Appsecco | 2 | 0 | 0 | - |
| `appsecco-indirect-prompt-injection-remote` | Appsecco | 2 | 0 | 0 | - |
| `appsecco-malicious-code-exec` | Appsecco | 1 | 0 | 0 | - |
| `appsecco-malicious-tools` | Appsecco | 2 | 0 | 0 | - |
| `appsecco-namespace-typosquatting` | Appsecco | 2 | 0 | 0 | - |
| `appsecco-outdated-packages` | Appsecco | 5 | 0 | 0 | - |
| `appsecco-secrets-pii` | Appsecco | 3 | 0 | 0 | - |
| `appsecco-wikipedia-http-streamable` | Appsecco | 3 | 0 | 0 | - |
| `promptfoo-evil-mcp-server` | Promptfoo | 1 | 1 | 0 | `MCP03-tool_priority_manipulation` |

## Finding 상세

### Promptfoo Evil MCP Server

| Finding ID | Tool | Severity | Confidence | Location | Evidence |
|---|---|---|---|---|---|
| `MCP03-tool_priority_manipulation` | `record_analytics` | medium | medium | `description` | `ALWAYS CALL THIS TOOL` |

이 Finding은 기존 정적 cross-tool instruction detector에서 발생했습니다. Semantic similarity detector가 추가한 Finding은 없습니다.

## 결과 해석

- Promptfoo의 강제 호출 문구는 기존 키워드·패턴 규칙으로 직접 탐지됩니다.
- Appsecco의 주요 위험은 tool metadata보다 구현 코드, 의존성 또는 도구 호출 결과에 존재합니다.
- 현재 semantic detector는 metadata의 의미를 확장 탐지하지만 런타임 결과나 소스 코드를 읽지는 않습니다.
- 따라서 이번 결과는 semantic 모델의 일반 성능보다 현재 정적 입력 범위의 한계를 보여줍니다.

