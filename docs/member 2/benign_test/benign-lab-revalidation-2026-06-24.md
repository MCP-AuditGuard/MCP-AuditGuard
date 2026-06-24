# Benign Lab 재검증 보고서 - 2026-06-24

`vulnerable-lab/benign-lab` 전체 benign fixture를 기본 Detector Registry로 스캔한 결과입니다.
대상은 MCP03 전용 benign control 100개와 general benign 100개, 총 200개 사례입니다.

## 실행 정보

- 실행 일시: `2026-06-24T14:54:23+09:00`
- 브랜치: `feature/member2-tool-poisoning`
- 기준 커밋: `3ad0243`
- 미커밋 작업트리 변경사항: `있음`
- 대상 1: `vulnerable-lab/benign-lab/mcp03-benign-100` (100개 사례)
- 대상 2: `vulnerable-lab/benign-lab/general-benign-100` (100개 사례)
- 스캔 방식: `Scanner(create_default_detectors())`

## 요약

- 전체 benign 사례: **200개**
- Finding 발생 사례: **1개**
- Finding 없음: **199개**
- 전체 Finding: **1개**
- Detector 오류: **0개**
- 추정 오탐률: **0.50%**
- Semantic Finding: **0개**
- Obfuscation Finding: **1개**
- Obfuscated MCP03 Finding: **0개**

## 세트별 요약

| 세트 | 전체 사례 | Finding 발생 사례 | Finding 수 | 추정 오탐률 |
|---|---:|---:|---:|---:|
| `mcp03-benign-100` | 100 | 1 | 1 | 1.00% |
| `general-benign-100` | 100 | 0 | 0 | 0.00% |

## 핵심 판단

- benign fixture에서 finding이 발생한 사례가 있으므로, 아래 사례는 오탐 후보로 검토해야 합니다.
- `tool_poisoning.obfuscated_hidden_instruction` 오탐은 발견되지 않았습니다.

## 심각도 분포

| Severity | Finding 수 |
|---|---:|
| `critical` | 0 |
| `high` | 0 |
| `medium` | 1 |
| `low` | 0 |
| `info` | 0 |

## 신뢰도 분포

| Confidence | Finding 수 |
|---|---:|
| `high` | 0 |
| `medium` | 1 |
| `low` | 0 |

## Finding 카테고리 분포

| Category | Finding 수 |
|---|---:|
| `obfuscation.url_encoding` | 1 |

## Finding 유형 분포

| Finding ID | 건수 |
|---|---:|
| `mcp03-url_encoding-051265efc59e` | 1 |

## Finding 발생 사례

| Benign ID | 세트 | 그룹 | 시나리오 | Finding 수 | 대표 Finding ID |
|---|---|---|---|---:|---|
| BENIGN-032 | `mcp03-benign-100` | `Benign Encoded Content` | `BENIGN-032-url-encoding-doc` | 1 | `mcp03-url_encoding-051265efc59e` |

## Finding 상세

### BENIGN-032 `BENIGN-032-url-encoding-doc`

- 경로: `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json`
- 세트: `mcp03-benign-100`
- 그룹: `Benign Encoded Content`
- Expected result: `No finding from default MCP03/obfuscation detectors.`

| Severity | Confidence | Category | ID | Location | Evidence 요약 |
|---|---|---|---|---|---|
| `medium` | `medium` | `obfuscation.url_encoding` | `mcp03-url_encoding-051265efc59e` | `description` | hello world. |

## Finding 없는 사례

- 총 199개 사례에서 finding이 발생하지 않았습니다.
