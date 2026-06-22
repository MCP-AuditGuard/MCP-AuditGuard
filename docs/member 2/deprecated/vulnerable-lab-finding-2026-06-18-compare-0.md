# Vulnerable Lab Finding Compare Report - 2026-06-18 #0

Semantic similarity detector를 끈 보고서와 `auto` 모드로 켠 보고서를 비교한 결과입니다.

## 비교 대상

- Semantic off: `docs/vulnerable-lab-finding-2026-06-18-0.md`
- Semantic on: `docs/vulnerable-lab-finding-2026-06-18-1.md`
- Git 커밋: `5ef7af1`
- 대상 fixture: `vulnerable-lab/expanded-112`
- 전체 사례: 112
- 공통 테스트 결과: `123 passed`
- Semantic 모델: `BAAI/bge-small-en-v1.5`

두 보고서는 같은 커밋, fixture, 정적 탐지기를 사용하며 semantic detector 활성화 여부만 다릅니다.

## 핵심 결과

| 지표 | Semantic off | Semantic on | 변화 |
|---|---:|---:|---:|
| Finding 발생 사례 | 65 (58.0%) | 67 (59.8%) | +2 cases, +1.8%p |
| Finding 없는 사례 | 47 | 45 | -2 |
| 카테고리 정합 사례 | 54 (48.2%) | 58 (51.8%) | +4 cases, +3.6%p |
| 카테고리 불일치 Finding만 있는 사례 | 11 | 9 | -2 |
| 전체 Finding | 95 | 127 | +32, +33.7% |
| Semantic Finding | 0 | 32 | +32 |
| `_meta.expected_signal` Finding | 23 | 23 | 0 |

Semantic detector는 총 32개 Finding을 추가했지만, 완전히 새롭게 탐지된 사례는 2개였습니다. 나머지는 이미 정적 또는 난독화 탐지기가 찾은 사례에 의미 기반 Finding을 추가한 결과입니다.

## 분포 변화

### Severity

| Severity | Semantic off | Semantic on | 변화 |
|---|---:|---:|---:|
| critical | 29 | 30 | +1 |
| high | 54 | 85 | +31 |
| medium | 10 | 10 | 0 |
| low | 2 | 2 | 0 |
| info | 0 | 0 | 0 |

### OWASP

| OWASP | Semantic off | Semantic on | 변화 |
|---|---:|---:|---:|
| MCP01 | 29 | 30 | +1 |
| MCP03 | 56 | 85 | +29 |
| MCP04 | 6 | 6 | 0 |
| MCP05 | 4 | 6 | +2 |

추가 Finding은 MCP03에 집중됐습니다. 현재 semantic signature가 `ignore_previous_instructions`, `covert_behavior`, `schema_instruction_poisoning`을 중심으로 구성돼 있기 때문입니다.

### 난이도별 사례 탐지

| Difficulty | Off: Any | On: Any | 변화 | Off: Aligned | On: Aligned | 변화 |
|---|---:|---:|---:|---:|---:|---:|
| Low | 21 | 22 | +1 | 17 | 20 | +3 |
| Medium | 23 | 24 | +1 | 22 | 23 | +1 |
| High | 21 | 21 | 0 | 15 | 15 | 0 |

High 난이도에서는 새로운 사례 탐지나 사례 단위 카테고리 정합성 개선이 없었습니다. Semantic Finding이 추가되기는 했지만 이미 탐지된 사례의 근거를 보강하는 역할에 머물렀습니다.

## 새로 탐지된 사례

Semantic을 켰을 때 off 상태에서 Finding이 없던 2개 사례가 새로 탐지됐습니다.

| Case | Scenario | Difficulty | 추가 Finding | 의미 점수와 근거 |
|---|---|---|---|---|
| LAB-015 | `LAB-015-title-ignore-policy` | Low | `MCP03-semantic_keyword_ignore_previous_instructions` | 0.765, title `Ignore Policy Backup` |
| LAB-034 | `LAB-034-meta-poisoning` | Medium | `MCP03-semantic_keyword_ignore_previous_instructions` | 0.779, `meta.operator_note`의 공격자 지시 우선 문구 |

LAB-034는 정적 키워드가 정확히 일치하지 않는 공격 의도를 의미적으로 탐지한 좋은 사례입니다. LAB-015는 탐지 목적에는 부합하지만 점수가 낮고 제목만 사용하므로 정상 문맥에서도 재현될 가능성을 검토해야 합니다.

## 카테고리 정합성이 새로 생긴 사례

사례의 fixture 카테고리와 일치하는 Finding이 없었다가 semantic으로 정합 Finding을 얻은 사례는 4개입니다.

| Case | Off aligned | On aligned | 주요 효과 |
|---|---:|---:|---|
| LAB-015 | 0 | 1 | 제목의 정책 무시 의미 탐지 |
| LAB-028 | 0 | 2 | NFKC/leet 변형된 ignore 의미 탐지 |
| LAB-029 | 0 | 1 | 토큰 간격이 변형된 시스템 지시 탐지 |
| LAB-034 | 0 | 1 | `_meta` 공격자 우선 지시 탐지 |

LAB-028과 LAB-029는 off 상태에서도 MCP01 Finding이 있었지만 fixture 목표인 MCP03 Finding은 없었습니다. Semantic을 켜면서 탐지 카테고리가 의도와 맞아졌습니다.

## 변경된 전체 사례

112개 중 21개 사례에서 Finding 수가 변했고, 91개 사례는 동일했습니다. Finding이 제거되거나 탐지 사례가 감소한 경우는 없습니다.

| Case | Scenario | Off | On | Aligned off | Aligned on | 추가된 Semantic Finding |
|---|---|---:|---:|---:|---:|---|
| LAB-002 | `LAB-002-print-environment` | 1 | 2 | 1 | 2 | `MCP01-secret_disclosure` 의미 확장 |
| LAB-015 | `LAB-015-title-ignore-policy` | 0 | 1 | 0 | 1 | `ignore_previous_instructions` |
| LAB-028 | `LAB-028-nfkc-leet-ignore` | 1 | 3 | 0 | 2 | `ignore_previous_instructions`, `schema_instruction_poisoning` |
| LAB-029 | `LAB-029-token-gap-system-instruction` | 1 | 2 | 0 | 1 | `ignore_previous_instructions` |
| LAB-034 | `LAB-034-meta-poisoning` | 0 | 1 | 0 | 1 | `ignore_previous_instructions` |
| LAB-039 | `LAB-039-forced-tool-use` | 1 | 2 | 1 | 2 | `schema_instruction_poisoning` |
| LAB-051 | `LAB-051-bidi-control-instruction` | 2 | 4 | 1 | 3 | `ignore_previous_instructions`, `covert_behavior` |
| LAB-052 | `LAB-052-unicode-tag-instruction` | 2 | 4 | 1 | 3 | `ignore_previous_instructions`, `covert_behavior` |
| LAB-053 | `LAB-053-mathematical-alphanumeric-instruction` | 1 | 3 | 1 | 3 | `ignore_previous_instructions`, `schema_instruction_poisoning` |
| LAB-054 | `LAB-054-combining-mark-instruction` | 1 | 4 | 1 | 4 | ignore, covert, schema 3종 |
| LAB-056 | `LAB-056-fullwidth-latin-confusable` | 1 | 3 | 1 | 3 | `ignore_previous_instructions`, `schema_instruction_poisoning` |
| LAB-057 | `LAB-057-css-comment-instruction` | 2 | 3 | 1 | 2 | `ignore_previous_instructions` |
| LAB-058 | `LAB-058-script-tag-instruction` | 2 | 3 | 1 | 2 | `ignore_previous_instructions` |
| LAB-059 | `LAB-059-ie-conditional-comment-instruction` | 2 | 3 | 2 | 3 | `ignore_previous_instructions` |
| LAB-074 | `LAB-074-bidi-script-tag-chain` | 2 | 3 | 1 | 2 | `ignore_previous_instructions` |
| LAB-077 | `LAB-077-unicode-tag-meta-instruction` | 3 | 5 | 2 | 4 | `ignore_previous_instructions`, `covert_behavior` |
| LAB-078 | `LAB-078-nfkc-fullwidth-system-gap` | 2 | 4 | 1 | 3 | `ignore_previous_instructions`, `covert_behavior` |
| LAB-079 | `LAB-079-combining-mark-homoglyph-chain` | 2 | 4 | 1 | 3 | `ignore_previous_instructions`, `covert_behavior` |
| LAB-089 | `LAB-089-run-shell-tool` | 1 | 2 | 1 | 2 | `command_execution` |
| LAB-090 | `LAB-090-python-os-system` | 1 | 3 | 1 | 2 | `command_execution`, MCP03 schema 의미 매칭 |
| LAB-097 | `LAB-097-read-and-send-permissions` | 1 | 2 | 0 | 0 | MCP03 `covert_behavior` 의미 매칭 |

## Semantic Finding 구성

### Rule별

| Semantic rule | Findings |
|---|---:|
| `MCP03-ignore_previous_instructions` | 16 |
| `MCP03-covert_behavior` | 7 |
| `MCP03-schema_instruction_poisoning` | 6 |
| `MCP05-command_execution` | 2 |
| `MCP01-secret_disclosure` | 1 |

### 위치별

| Location root | Findings |
|---|---:|
| `description` | 22 |
| `title` | 4 |
| `meta` | 3 |
| `input_schema` | 3 |

### 점수 분포

| Score range | Findings |
|---|---:|
| 0.80 이상 | 15 |
| 0.80 미만 | 17 |
| 0.78 미만 | 10 |

최저 점수는 0.760, 최고 점수는 0.990입니다. 추가 Finding의 절반 이상이 0.80 미만이므로 공통 threshold를 일괄 상향하면 노이즈는 줄지만 LAB-015와 LAB-034 같은 신규 탐지도 함께 사라질 수 있습니다.

## Benign control 확인

| Case | Semantic off | Semantic on | Semantic 추가 여부 |
|---|---:|---:|---|
| LAB-030 base64 short benign control | 0 | 0 | 없음 |
| LAB-031 HTML comment benign control | 2 | 2 | 없음 |
| LAB-032 mixed-script benign control | 2 | 2 | 없음 |

현재 명시된 세 benign control에서는 semantic detector가 새로운 Finding을 만들지 않았습니다. 다만 LAB-031과 LAB-032의 기존 2개 Finding은 semantic과 무관한 탐지기 결과이므로 별도 오탐 검토가 필요합니다.

## 오탐 가능성이 높은 Semantic 결과

다음 결과는 fixture 문맥과 관계없이 실제 MCP metadata에서도 자주 나올 수 있는 짧거나 일반적인 표현입니다.

| Case | 탐지 텍스트 | Semantic 분류 | 문제점 |
|---|---|---|---|
| LAB-039 | `User request.` | MCP03 schema poisoning | 일반적인 schema 설명으로도 사용 가능 |
| LAB-090 | `user_input` | MCP03 schema poisoning | `required` 배열의 필드명일 뿐 공격 지시가 아님 |
| LAB-097 | `Secret Sync` | MCP03 covert behavior | 보안 제품이나 동기화 도구의 정상 제목일 수 있음 |

LAB-090의 MCP05 command execution Finding은 실제 위험과 정합하지만, 같은 사례의 `user_input` MCP03 Finding은 별개의 오탐 후보입니다. LAB-097의 semantic Finding도 fixture 카테고리 MCP06과 일치하지 않습니다.

## 해석

### 장점

- 정확한 키워드가 없는 LAB-034의 공격자 우선 지시를 새로 탐지했습니다.
- NFKC, fullwidth, bidi, Unicode tag, combining mark처럼 텍스트가 변형된 사례에서 MCP03 근거를 보강했습니다.
- MCP05 command execution 문장의 표현 변형도 의미적으로 보조 탐지했습니다.
- 명시된 benign control 3개에는 semantic Finding을 추가하지 않았습니다.

### 한계

- 전체 Finding은 33.7% 증가했지만 Finding 발생 사례는 2개만 증가해 중복 경고가 많이 늘었습니다.
- 21개 변경 사례 중 17개는 사례 단위 탐지 여부나 카테고리 정합 여부를 새롭게 개선하지 못했습니다.
- 짧은 필드명과 일반 제목에서도 의미 유사도가 threshold를 넘는 사례가 있습니다.
- 32개 semantic Finding 중 fixture OWASP 카테고리와 일치하는 것은 30개지만, fixture 카테고리는 개별 Finding의 정답 레이블이 아니므로 이를 precision 93.8%로 해석하면 안 됩니다.
- `_meta.expected_signal`에서 발생한 23개 정적 Finding은 두 보고서에 동일하게 포함되어 있어 semantic 효과와는 무관하지만, 전체 수치 자체를 부풀립니다.

## 결론 및 권장 방향

Semantic detector는 완전히 끄기보다 선택적 보조 탐지기로 유지하는 편이 좋습니다. LAB-034처럼 정적 룰이 놓치는 의미 변형을 찾는 가치가 확인됐기 때문입니다. 다만 현재 상태로 기본 경고를 모두 동일하게 노출하면 신규 사례 2개를 얻는 대신 Finding 32개가 증가해 분석 부담이 커집니다.

권장 개선 순서는 다음과 같습니다.

1. `input_schema.required[]`처럼 값이 필드명에 불과한 위치를 semantic 대상에서 제외합니다.
2. `User request.`, `Secret Sync`처럼 짧고 일반적인 텍스트는 최소 토큰 수와 위험 행동 단서 조건을 함께 적용합니다.
3. 공통 threshold 일괄 상향 대신 룰과 필드 위치별 threshold를 사용합니다.
4. 동일 텍스트에서 정적 Finding이 이미 발생하면 semantic Finding을 보조 근거로 묶어 중복 경고를 줄입니다.
5. fixture 카테고리가 아니라 Finding 단위 정답 레이블과 정상 MCP metadata 세트를 추가해 precision, recall, false-positive rate를 계산합니다.

현재 결과만 기준으로 하면 semantic은 탐지 범위를 조금 넓히는 데는 유효하지만, 운영 기본값으로 사용하기 전 일반 텍스트 필터와 중복 억제가 필요합니다.
