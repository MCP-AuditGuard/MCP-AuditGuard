# 테스트 Markdown 비교 요약 - 2026-06-16

이 문서는 현재 `docs/` 폴더에 있는 테스트 관련 Markdown 파일들을 한 번에 요약하고 비교한 문서입니다.

## 비교 대상 문서

| 파일 | 목적 |
|---|---|
| `docs/vulnerable-lab-finding-matrix.md` | semantic 실험 이전의 기본 vulnerable-lab 스캔 결과 |
| `docs/vulnerable-lab-finding-matrix-semantic.md` | 넓은 범위의 로컬 임베딩 semantic signature 적용 결과 |
| `docs/vulnerable-lab-finding-matrix-keyword-semantic.md` | 기존 keyword 룰을 임베딩 seed로 확장한 결과 |
| `docs/vulnerable-lab-finding-matrix-2026-06-16.md` | allowlist, 룰별 threshold, action gate를 적용한 최신 보수적 semantic 결과 |
| `docs/semantic-improvement-summary.ko.md` | 기본 결과와 넓은 semantic signature 결과를 비교한 한국어 요약 |
| `docs/keyword-semantic-improvement-summary.ko.md` | 기본 결과와 keyword-semantic 확장 결과를 비교한 한국어 요약 |
| `docs/vulnerable-lab-planned-coverage.md` | 52개 vulnerable-lab 케이스가 현재 또는 향후 프로젝트 범위에 해당하는지 분류한 문서 |
| `docs/test-scenario-expansion-plan.md` | 52개 확장 vulnerable-lab 시나리오 설계 문서 |

## 전체 비교

| 결과 세트 | 스캔 케이스 | Finding 발생 케이스 | 탐지율 | 총 Finding | Critical | High | Medium | 비고 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 기본 Matrix | 52 | 12 | 23.1% | 16 | 6 | 8 | 2 | 기존 keyword, regex, obfuscation, rule 기반 detector 결과 |
| 넓은 Semantic Matrix | 52 | 16 | 30.8% | 20 | 7 | 11 | 2 | MCP01, MCP05까지 포함한 넓은 semantic signature 적용 |
| Keyword-Semantic Matrix | 52 | 14 | 26.9% | 20 | 6 | 12 | 2 | 기존 keyword 룰을 semantic similarity seed로 확장 |
| 최신 2026-06-16 Matrix | 52 | 12 | 23.1% | 16 | 6 | 8 | 2 | allowlist, threshold, action gate로 semantic 확장을 보수적으로 제한 |

## 해석

넓은 semantic 실험은 vulnerable-lab 기준으로 가장 높은 탐지 수를 보였습니다.

```text
12개 케이스 -> 16개 케이스
23.1% -> 30.8%
```

이 개선은 주로 현재 Member 2의 MCP03 담당 범위를 넘어서는 semantic signature에서 발생했습니다.

| 추가 탐지 케이스 | 카테고리 | 추가 Finding |
|---|---|---|
| LAB-001 | MCP01 Secret Exposure | `MCP01-semantic_plain_secret_exposure` |
| LAB-002 | MCP01 Secret Exposure | `MCP01-semantic_environment_dump` |
| LAB-029 | MCP05 Command Injection | `MCP05-semantic_command_execution` |
| LAB-030 | MCP05 Command Injection | `MCP05-semantic_command_execution` |

Keyword-semantic 실험은 더 적은 케이스를 추가로 탐지했습니다.

```text
12개 케이스 -> 14개 케이스
23.1% -> 26.9%
```

이 방식은 기존 keyword 룰을 기준으로 의미적으로 가까운 문장을 탐지했지만, 일반적인 schema 문구에서 오탐 가능성도 함께 드러났습니다.

## 케이스별 차이

| Case | 기본 | 넓은 Semantic | Keyword Semantic | 최신 2026-06-16 | 변경 내용 |
|---|---:|---:|---:|---:|---|
| LAB-001 | 0 | 1 | 0 | 0 | 넓은 semantic은 평문 secret 노출을 잡았지만, 최신 보수적 설정에서는 해당 broad signature 경로가 유효 탐지로 이어지지 않음 |
| LAB-002 | 0 | 1 | 0 | 0 | 넓은 semantic은 environment dump를 잡았지만, 최신 설정은 MCP01 broad semantic 확장을 제한함 |
| LAB-014 | 0 | 0 | 1 | 0 | keyword-semantic은 `_meta` poisoning을 잡았지만, 최신 action-gated allowlist에서는 보고하지 않음 |
| LAB-019 | 1 | 1 | 2 | 1 | keyword-semantic은 schema 관련 추가 Finding을 만들었지만, 최신 설정에서는 억제됨 |
| LAB-029 | 0 | 1 | 0 | 0 | 넓은 semantic은 command execution 위험을 잡았지만, 현재 Member 2의 MCP03 범위 밖임 |
| LAB-030 | 0 | 1 | 1 | 0 | broad/keyword semantic 변형은 command 또는 schema 신호를 잡았지만, 최신 보수적 설정에서는 억제됨 |
| LAB-037 | 1 | 1 | 2 | 1 | keyword-semantic은 `Secret Sync` title에서 covert-behavior를 추가 탐지했지만, 최신 설정은 이처럼 노이즈 가능성이 있는 확장을 억제함 |
| LAB-039 | 1 | 1 | 1 | 1 | `MCP03-privileged_resource_access`로 안정적으로 탐지됨 |

## 최신 보수적 Semantic 결과

최신 결과는 의도적으로 기본 결과와 같은 수준의 케이스 수로 돌아왔습니다.

```text
Finding 발생 케이스: 12
총 Finding: 16
```

이는 최신 semantic 작업이 recall 증가보다 precision, 즉 오탐 방지를 우선했기 때문입니다.

- semantic rule expansion을 allowlist로 제한
- Member 2 keyword 룰 중 `ignore_previous_instructions`, `tool_priority_manipulation`만 semantic 확장
- `schema_instruction_poisoning`, `covert_behavior`는 semantic 확장에서 제외
- 전체 공통 threshold 대신 룰별 threshold 사용
- semantic rule finding을 만들기 전에 action gate를 통과해야 함
- `user`, `input`, `request`, `tool` 같은 일반 표현에서 오탐이 발생하지 않도록 benign semantic fixture 추가

## 프로젝트 범위 비교

`docs/vulnerable-lab-planned-coverage.md`는 52개 케이스를 다음처럼 분류합니다.

```text
명시적으로 계획된 탐지 범위: 42개
넓은 향후 커버리지 케이스: 10개
```

카테고리별 계획 상태는 다음과 같습니다.

| Category | 케이스 수 | 계획 상태 |
|---|---:|---|
| MCP01 Secret Exposure | 6 | 계획된 확장 범위 |
| MCP02 Authentication and Authorization | 4 | 향후 확장 또는 넓은 커버리지 |
| MCP03 Tool Poisoning | 12 | MVP 범위 |
| MCP04 Supply Chain Risk | 6 | 계획된 확장 범위 |
| MCP05 Command Injection | 6 | 계획된 확장 범위 |
| MCP06 Excessive Tool Permissions | 3 | 향후 확장 또는 넓은 커버리지 |
| MCP07 Data Boundary Violation | 2 | 향후 확장 또는 넓은 커버리지 |
| MCP08 Audit and Telemetry | 6 | 계획된 확장 범위 |
| MCP09 Shadow MCP | 6 | 계획된 확장 범위 |
| MCP10 Denial of Service and Resource Abuse | 1 | 향후 확장 또는 넓은 커버리지 |

최신 결과는 현재 구현이 가장 강한 영역에서 가장 좋은 탐지 성과를 보입니다.

| Category | 최신 탐지 케이스 | 전체 케이스 |
|---|---:|---:|
| MCP01 Secret Exposure | 2 | 6 |
| MCP02 Authentication and Authorization | 0 | 4 |
| MCP03 Tool Poisoning | 8 | 12 |
| MCP04 Supply Chain Risk | 0 | 6 |
| MCP05 Command Injection | 0 | 6 |
| MCP06 Excessive Tool Permissions | 1 | 3 |
| MCP07 Data Boundary Violation | 1 | 2 |
| MCP08 Audit and Telemetry | 0 | 6 |
| MCP09 Shadow MCP | 0 | 6 |
| MCP10 Denial of Service and Resource Abuse | 0 | 1 |

## 핵심 정리

1. 넓은 semantic 실험은 recall을 가장 많이 올렸지만, 일부 개선은 현재 Member 2의 MCP03 담당 범위를 넘어서는 카테고리에서 발생했습니다.
2. Keyword-semantic 실험은 기존 룰의 paraphrase를 일부 잡을 수 있음을 보여줬지만, 넓은 룰 확장은 noisy finding을 만들 수 있었습니다.
3. 최신 2026-06-16 결과는 allowlist, threshold, action gate를 통해 precision을 우선하도록 조정되었습니다.
4. 최신 결과는 semantic coverage를 과장하지 않기 때문에 보수적인 MVP 발표에 더 적합합니다.
5. 현재 가장 강한 탐지 영역은 `Agent.md`의 MVP 목표와 일치하는 MCP03 Tool Poisoning입니다.

## 발표용 설명 추천

현재 프로젝트 발표에서는 semantic 작업을 완성된 넓은 범위의 detector라기보다, 통제된 실험으로 설명하는 것이 좋습니다.

```text
우리는 keyword와 regex 기반 탐지를 의미 기반으로 확장할 수 있는지 실험했습니다.
넓은 semantic 버전은 vulnerable-lab 탐지 케이스를 12개에서 16개로 늘렸지만,
오탐 위험을 줄이기 위해 allowlist, 룰별 threshold, action gate를 적용해 범위를 좁혔습니다.
최신 보수적 버전은 baseline 수준의 precision을 유지하면서,
향후 semantic 확장을 위한 구조를 준비한 상태입니다.
```

이 설명은 현재 결과를 과장하지 않으면서도, 프로젝트가 semantic detection으로 발전할 수 있는 방향을 보여줍니다.
