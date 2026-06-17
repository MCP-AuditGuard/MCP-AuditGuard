# 로컬 임베딩 유사도 모델 도입 개선 요약

이 문서는 `vulnerable-lab/expanded-52`의 52개 테스트 케이스를 기준으로, 기존 탐지 방식과 로컬 임베딩 유사도 모델 도입 이후의 탐지 결과를 비교한 것이다.

비교 기준 파일:

- 기존 결과: `docs/vulnerable-lab-finding-matrix.md`
- 로컬 임베딩 유사도 모델 적용 결과: `docs/vulnerable-lab-finding-matrix-semantic.md`

## 요약

| 항목 | 기존 | 도입 후 | 변화 |
|---|---:|---:|---:|
| 전체 테스트 케이스 | 52 | 52 | - |
| 탐지된 케이스 | 12 | 16 | +4 |
| 탐지되지 않은 케이스 | 40 | 36 | -4 |
| 총 Finding 수 | 16 | 20 | +4 |
| 케이스 기준 탐지율 | 23.1% | 30.8% | +7.7%p |
| 탐지 케이스 상대 개선율 | - | - | +33.3% |
| Finding 수 상대 증가율 | - | - | +25.0% |

## 계산 방식

케이스 기준 탐지율:

```text
기존 탐지율 = 12 / 52 = 23.1%
도입 후 탐지율 = 16 / 52 = 30.8%
```

절대 개선폭:

```text
30.8% - 23.1% = +7.7%p
```

탐지 케이스 기준 상대 개선율:

```text
(16 - 12) / 12 = 33.3%
```

Finding 수 기준 상대 증가율:

```text
(20 - 16) / 16 = 25.0%
```

## 추가로 탐지된 케이스

로컬 임베딩 유사도 모델 도입 이후 새로 탐지된 케이스는 총 4개다.

| Case | Scenario | Category | 추가 Finding | Severity | 유사도 점수 |
|---|---|---|---|---|---:|
| LAB-001 | `LAB-001-plain-env-secret` | MCP01 Secret Exposure | `MCP01-semantic_plain_secret_exposure` | critical | 0.795 |
| LAB-002 | `LAB-002-print-environment` | MCP01 Secret Exposure | `MCP01-semantic_environment_dump` | high | 0.937 |
| LAB-029 | `LAB-029-run-shell-tool` | MCP05 Command Injection | `MCP05-semantic_command_execution` | high | 0.872 |
| LAB-030 | `LAB-030-python-os-system` | MCP05 Command Injection | `MCP05-semantic_command_execution` | high | 0.887 |

## 카테고리별 개선

이번 개선으로 추가 탐지된 영역은 두 가지다.

```text
MCP01 Secret Exposure: +2개 케이스
MCP05 Command Injection: +2개 케이스
```

MCP01에서는 기존 키워드/정규식 탐지가 놓치던 평문 환경변수 노출과 환경변수 출력 지시를 의미 기반으로 보완했다.

MCP05에서는 명령 실행 위험을 직접적인 정규식 패턴이 아니라 의미 유사도 기반으로 탐지했다.

## 해석

로컬 임베딩 유사도 모델 도입으로 전체 vulnerable lab 기준 탐지율은 다음과 같이 개선되었다.

```text
23.1% -> 30.8%
```

이는 전체 52개 테스트 케이스 중 4개 케이스를 추가로 탐지한 결과이며, 탐지 케이스 수 기준으로는 약 33.3%의 상대 개선이다.

다만 이 수치는 프로젝트의 `vulnerable-lab/expanded-52` fixture 기준 개선율이다. 따라서 일반적인 모든 MCP 보안 시나리오에 대한 성능 향상으로 해석하기보다는, 현재 프로젝트가 보유한 테스트셋 기준의 개선으로 보는 것이 정확하다.

## 주의할 점

로컬 임베딩 유사도 모델은 기존 탐지 방식을 대체하지 않는다. 현재 구조에서는 기존 키워드, 정규식, obfuscation detector에 더해 의미 기반 보조 탐지 계층으로 동작한다.

또한 MCP01의 일부 추가 탐지는 모델 도입만으로 발생한 것이 아니라, `rules/semantic_signatures.yaml`의 semantic signature와 threshold 조정이 함께 작동한 결과다.

즉 이번 개선은 다음 조합의 효과로 보는 것이 정확하다.

```text
기존 정적 탐지기
+ 로컬 BAAI/bge-small-en-v1.5 임베딩 모델
+ semantic_signatures.yaml 기반 위험 예시 문장
+ 유사도 threshold 조정
```

## 결론

로컬 임베딩 유사도 모델 도입으로 기존 탐지 방식이 놓치던 의미 기반 위험 표현을 일부 보완할 수 있었다.

현재 기준 개선 효과:

```text
탐지 케이스: 12개 -> 16개
총 Finding: 16개 -> 20개
탐지율: 23.1% -> 30.8%
상대 개선율: +33.3%
```

특히 MCP01 Secret Exposure와 MCP05 Command Injection 영역에서 보완 효과가 확인되었다.
