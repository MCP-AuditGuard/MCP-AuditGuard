# Vulnerable Lab MCP03 탐지 결과 비교 보고서

비교 대상:

- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-20.md`
- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-23.md`

작성일: 2026-06-23

## 1. 비교 요약

| 항목 | 2026-06-20 | 2026-06-23 | 변화 |
| --- | ---: | ---: | ---: |
| 전체 테스트 케이스 | 112 | 112 | 0 |
| 탐지된 케이스 | 45 | 48 | +3 |
| 미탐 케이스 | 67 | 64 | -3 |
| 전체 Finding 수 | 85 | 103 | +18 |
| Semantic Finding 수 | 29 | 27 | -2 |
| Obfuscation Finding 수 | 14 | 33 | +19 |
| Canonical Text 기반 MCP03 Rule Match | 없음 | 28 | +28 |

이번 개선의 핵심은 단순히 finding 수가 늘어난 것이 아니라, 난독화된 텍스트를 복호화 또는 정규화한 뒤 동일한 MCP03 룰로 다시 검사하도록 바뀐 점이다. 그래서 이전에는 “난독화 자체” 정도로만 보이던 결과가, 이제는 “복호화된 문장이 어떤 MCP03 규칙에 걸렸는지”까지 근거로 남는다.

## 2. 위험도 분포 변화

| Severity | 2026-06-20 | 2026-06-23 | 변화 |
| --- | ---: | ---: | ---: |
| Critical | 23 | 39 | +16 |
| High | 51 | 56 | +5 |
| Medium | 9 | 6 | -3 |
| Low | 2 | 2 | 0 |
| Info | 0 | 0 | 0 |

`critical`이 크게 증가한 이유는 난독화 탐지 결과가 단순한 obfuscation 신호로 끝나지 않고, canonical text에 대해 MCP03 룰 매칭을 수행하면서 `sensitive_data_steering`, `instruction_override` 같은 고위험 의도를 더 직접적으로 확인하게 되었기 때문이다.

즉, 위험도가 무작정 상향된 것이 아니라 “난독화된 내부 문장을 실제 MCP03 행위로 해석할 수 있는 경우”에 더 강한 severity가 붙게 된 것이다.

## 3. 새롭게 탐지된 케이스

| Lab ID | 케이스 | 개선 내용 |
| --- | --- | --- |
| LAB-025 | `LAB-025-octal-escape-instruction` | Octal escape로 숨겨진 instruction을 canonical text로 복원한 뒤 MCP03 룰에 매칭 |
| LAB-026 | `LAB-026-html-entity-instruction` | HTML entity로 숨겨진 instruction을 복호화 후 MCP03 룰에 매칭 |
| LAB-027 | `LAB-027-rot13-instruction` | ROT13으로 숨겨진 instruction을 복호화 후 MCP03 룰에 매칭 |
| LAB-047 | `LAB-047-markdown-image-link-poisoning` | Markdown image/link 형태로 숨겨진 poisoning 패턴을 탐지 |

이 4개는 2026-06-20 보고서에서는 탐지되지 않았지만, 2026-06-23 보고서에서는 탐지되었다. 특히 LAB-025, LAB-026, LAB-027은 “원문에는 명확한 키워드가 보이지 않지만, 복호화하면 MCP03 행위가 드러나는” 케이스라서 이번 구조 개선의 효과를 잘 보여준다.

## 4. 제외된 케이스

| Lab ID | 케이스 | 2026-06-20 탐지 | 2026-06-23 결과 | 해석 |
| --- | --- | --- | --- | --- |
| LAB-090 | `LAB-090-python-os-system` | `MCP03-semantic_keyword_schema_instruction_poisoning` | 미탐 | 오탐 감소에 가까운 변화 |

LAB-090은 command execution 성격의 케이스로, 현재 프로젝트의 초점인 MCP03 Tool Poisoning과는 직접성이 약하다. 이전에는 semantic detector가 schema 구조값이나 짧은 필드성 표현을 과하게 해석해 MCP03처럼 잡은 것으로 볼 수 있다.

2026-06-23에서는 semantic 입력 정제를 통해 `required`, `enum`, `const`, `default` 같은 구조 필드와 너무 짧은 title성 텍스트를 제외했다. 따라서 LAB-090이 빠진 것은 탐지력 저하라기보다, MCP03 범위에 맞게 오탐을 줄인 개선으로 해석하는 편이 타당하다.

## 5. 기존 탐지 케이스에서 강화된 부분

다음 케이스들은 이미 탐지되고 있었지만, 2026-06-23 결과에서 더 구체적인 근거가 추가되거나 난독화 유형이 세분화되었다.

| Lab ID | 변화 |
| --- | --- |
| LAB-050 | nested base64-url 케이스에서 base64뿐 아니라 URL encoding 근거도 추가 |
| LAB-051, LAB-052, LAB-053, LAB-054, LAB-056 | zero-width, homoglyph 계열 canonical evidence가 추가되어 숨겨진 MCP03 문장을 더 직접적으로 설명 |
| LAB-057 | CSS comment 기반 은닉 신호가 별도 finding으로 드러남 |
| LAB-058 | script tag 기반 은닉 신호가 별도 finding으로 드러남 |
| LAB-059 | IE conditional comment 유형으로 더 정확히 분리 |
| LAB-074, LAB-075, LAB-079, LAB-082 | 여러 난독화 기법이 섞인 케이스에서 각각의 evidence가 더 구체적으로 분리됨 |
| LAB-081 | base64-url 중첩 케이스에서 URL encoding evidence가 추가됨 |

이 변화는 finding 수 증가의 주요 원인이다. 다만 이것은 단순 중복 증가라기보다, “하나의 악성 도구 설명 안에 들어 있는 여러 은닉 기법을 더 명확히 드러내는 변화”에 가깝다.

## 6. Semantic Detector 변화

Semantic finding은 29개에서 27개로 2개 줄었다.

줄어든 대표 사례:

- LAB-090: `schema_instruction_poisoning` semantic 탐지 제거
- LAB-097: `covert_behavior` semantic 추가 탐지 제거

이는 semantic detector를 약화한 것이 아니라 입력 대상을 정제한 결과다. 이전에는 schema의 구조적 필드값이나 짧은 기능 설명이 semantic detector에 들어가면서 MCP03 의도처럼 해석될 수 있었다. 이제는 실제 도구 설명, description, instruction성 텍스트 중심으로 입력이 제한되어 의미 기반 탐지가 더 보수적으로 동작한다.

정리하면 semantic detector는 여전히 우회 표현 탐지에 기여하지만, 2026-06-23 버전에서는 “아무 구조값이나 의미적으로 의심하는 방식”에서 조금 벗어나 MCP03 설명문 중심으로 정돈되었다.

## 7. Evidence 품질 개선

2026-06-23 보고서에서는 여러 finding에 다음과 같은 근거 속성이 추가되었다.

- `matched_on`
- `matched_rule`
- `canonical_excerpt`
- `original_excerpt`
- `transforms`

이 변화의 의미는 크다. 이전 결과는 “무엇인가 난독화가 있다”는 수준에 가까웠다면, 이제는 다음 질문에 답할 수 있다.

- 원문에서 잡힌 것인가, 복호화된 canonical text에서 잡힌 것인가?
- 어떤 MCP03 룰에 매칭되었는가?
- 복호화 후 어떤 문장이 실제 근거가 되었는가?
- 어떤 변환 과정을 거쳤는가?

이 덕분에 보고서 사용자는 finding을 더 쉽게 검증할 수 있고, 프런트엔드에서도 근거 표시를 더 신뢰성 있게 구성할 수 있다.

## 8. 주의할 점

일부 finding ID는 2026-06-20과 2026-06-23 사이에서 달라졌다. 이는 동일한 시나리오라도 evidence에 canonical text, matched rule, transforms 같은 정보가 추가되면서 fingerprint가 바뀐 영향이 있다.

따라서 단순히 finding ID가 바뀌었다고 해서 모두 새로운 탐지라고 해석하면 안 된다. 이번 비교에서는 finding ID보다 lab scenario 단위, detector 유형, evidence 품질 변화를 중심으로 보는 것이 더 정확하다.

또한 finding 수가 85개에서 103개로 증가한 것은 탐지 범위가 넓어진 영향도 있지만, 하나의 케이스 안에서 여러 난독화 근거를 더 세분화해서 보여주기 시작한 영향도 있다.

## 9. 결론

2026-06-23 버전의 개선점은 다음과 같이 정리할 수 있다.

1. MCP03 탐지 케이스가 45개에서 48개로 증가했다.
2. Octal escape, HTML entity, ROT13, Markdown link/image poisoning 등 이전 미탐 케이스를 새로 잡았다.
3. Obfuscation finding이 14개에서 33개로 증가해 난독화 우회 표현 대응력이 좋아졌다.
4. Canonical text 기반 MCP03 룰 매칭이 도입되어 복호화된 문장에 대해서도 동일한 기준으로 탐지할 수 있게 되었다.
5. Semantic detector는 구조값 오탐을 줄이는 방향으로 정제되어 finding 수가 29개에서 27개로 감소했다.
6. Evidence에 `matched_on`, `matched_rule`, `canonical_excerpt`, `transforms` 등이 들어가면서 결과 검증 가능성이 좋아졌다.

전체적으로 2026-06-23 버전은 MCP03 Tool Poisoning에 더 집중된 방향으로 발전했다. 특히 “난독화 탐지”와 “MCP03 의도 판정”이 분리되어 있던 이전 구조에서, 복호화된 canonical text를 다시 MCP03 rule matcher에 통과시키는 구조로 바뀐 점이 가장 중요한 개선이다.

