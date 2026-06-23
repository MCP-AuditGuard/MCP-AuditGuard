# Vulnerable Lab Finding Compare Report - 2026-06-18 #1

연구용 악성 MCP 서버의 정적 `tools.json` fixture를 대상으로 Semantic similarity detector를 끈 결과와 `auto` 모드 결과를 비교했습니다.

## 비교 대상

- Semantic OFF: `docs/vulnerable-lab-finding-2026-06-18-2.md`
- Semantic AUTO: `docs/vulnerable-lab-finding-2026-06-18-3.md`
- Git 커밋: `5ef7af1` (fixture는 현재 미커밋 작업 트리에 존재)
- 대상 fixture: `tests/fixtures/research_malicious_servers`
- 전체 서버: 10
- 전체 도구: 25
- Semantic 모델: `BAAI/bge-small-en-v1.5`
- 전체 테스트 결과: `228 passed`

두 스캔은 동일한 fixture와 detector registry를 사용하며 semantic detector의 `mode`만 `false`와 `auto`로 다릅니다.

## 핵심 결과

| 지표 | Semantic OFF | Semantic AUTO | 변화 |
|---|---:|---:|---:|
| Finding 발생 서버 | 1 (10.0%) | 1 (10.0%) | 0 |
| Finding 없는 서버 | 9 | 9 | 0 |
| Finding 발생 도구 | 1 (4.0%) | 1 (4.0%) | 0 |
| 전체 Finding | 1 | 1 | 0 |
| Semantic Finding | 0 | 0 | 0 |
| `critical` | 0 | 0 | 0 |
| `high` | 0 | 0 | 0 |
| `medium` | 1 | 1 | 0 |

## 서버별 변화

| Fixture | OFF | AUTO | 변화 |
|---|---:|---:|---:|
| `appsecco-filesystem-workspace-actions` | 0 | 0 | 0 |
| `appsecco-indirect-prompt-injection` | 0 | 0 | 0 |
| `appsecco-indirect-prompt-injection-remote` | 0 | 0 | 0 |
| `appsecco-malicious-code-exec` | 0 | 0 | 0 |
| `appsecco-malicious-tools` | 0 | 0 | 0 |
| `appsecco-namespace-typosquatting` | 0 | 0 | 0 |
| `appsecco-outdated-packages` | 0 | 0 | 0 |
| `appsecco-secrets-pii` | 0 | 0 | 0 |
| `appsecco-wikipedia-http-streamable` | 0 | 0 | 0 |
| `promptfoo-evil-mcp-server` | 1 | 1 | 0 |

## 공통 Finding

| Finding ID | Fixture | Tool | Severity | Evidence |
|---|---|---|---|---|
| `MCP03-tool_priority_manipulation` | `promptfoo-evil-mcp-server` | `record_analytics` | medium | `ALWAYS CALL THIS TOOL` |

## 결론

이번 10개 정적 fixture에서는 semantic AUTO가 추가 Finding을 만들지 않았습니다. Promptfoo의 노골적인 강제 호출 문구는 기존 정적 규칙만으로 탐지됐습니다.

Appsecco 서버가 탐지되지 않은 주된 이유는 위험이 다음 영역에 있기 때문입니다.

- 도구 호출 이후 반환되는 악성 문서 또는 조작된 결과
- 서버 구현의 `eval()` 및 경로 검증 누락
- 취약하거나 오래된 의존성
- 구현 코드와 로그의 Secret 및 PII
- 신뢰 기준이 필요한 서버·패키지 이름 typosquatting

따라서 이 세트의 탐지 범위를 높이려면 semantic threshold 조정보다 소스 코드 분석, 의존성 검사, 서버 신뢰 목록, 그리고 격리된 런타임 `tools/call` 응답 분석이 우선입니다.

