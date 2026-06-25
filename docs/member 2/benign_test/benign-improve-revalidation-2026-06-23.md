# Benign Lab 재검증 보고서 - improve

선택안 B 구조 개선 이후 `vulnerable-lab/benign-lab/mcp03-benign-100` 전체 100개 benign fixture를 스캔한 결과입니다.
이번 보고서는 특히 `tool_poisoning.obfuscated_hidden_instruction`가 benign encoded/Unicode 문맥에서 새 오탐을 만들었는지 확인하는 목적입니다.

## 실행 정보

- 실행 일시: `2026-06-23T21:39:34+09:00`
- 브랜치: `feature/member2-tool-poisoning`
- 기준 커밋: `3ad0243`
- 미커밋 작업트리 변경사항: `있음`
- 대상: `vulnerable-lab/benign-lab/mcp03-benign-100` (100개 사례)
- 스캔 방식: `Scanner(create_default_detectors())`
- 적용 구조: `obfuscation detector -> DerivedMetadataText -> ObfuscatedHiddenInstructionDetector -> rule_engine`

## 요약

- 전체 benign 사례: **100개**
- Finding 발생 사례: **1개**
- Finding 없음: **99개**
- 전체 Finding: **1개**
- Detector 오류: **0개**
- 추정 오탐률: **1.00%**
- Semantic Finding: **0개**
- Obfuscation Finding: **1개**
- Obfuscated MCP03 Finding: **0개**

## 핵심 판단

- `tool_poisoning.obfuscated_hidden_instruction` 오탐은 발견되지 않았습니다.
- benign fixture에서 finding이 발생한 사례가 있으므로, 실제 사용자 보고서에서는 이 케이스들을 오탐 후보로 검토해야 합니다.

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

| Category | 건수 |
|---|---:|
| `obfuscation.url_encoding` | 1 |

## Finding 유형 분포

| Finding ID | 건수 |
|---|---:|
| `mcp03-url_encoding-051265efc59e` | 1 |

## Finding 발생 사례

| Benign ID | 그룹 | 시나리오 | Finding 수 | Finding ID |
|---|---|---|---:|---|
| BENIGN-032 | `benign-encoded-content` | `BENIGN-032-url-encoding-doc` | 1 | `mcp03-url_encoding-051265efc59e` |

## Finding 상세

### BENIGN-032 `BENIGN-032-url-encoding-doc`

- 경로: `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json`
- 그룹: `benign-encoded-content`
- Expected result: `No finding from default MCP03/obfuscation detectors.`

| Severity | Confidence | Category | ID | Location | Evidence 요약 |
|---|---|---|---|---|---|
| `medium` | `medium` | `obfuscation.url_encoding` | `mcp03-url_encoding-051265efc59e` | `description` | hello world. |


## Finding 없는 사례

- 총 99개 사례에서 finding이 발생하지 않았습니다.

## 결론

선택안 B 구조 전환으로 새로 추가된 `ObfuscatedHiddenInstructionDetector`는 이번 benign-lab 재검증에서 오탐을 만들지 않았습니다.
다만 benign 전체 기준 finding 발생 사례가 1개 있으므로, 이 사례들은 기존 오탐 관리 대상 또는 별도 allowlist/문맥 필터 후보로 유지해야 합니다.
