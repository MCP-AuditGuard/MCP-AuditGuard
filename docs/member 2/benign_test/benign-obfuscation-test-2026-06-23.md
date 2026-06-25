# Member 2 Benign Lab Obfuscation Detector 테스트 보고서

## 문서 목적

이 문서는 `develop`에서 병합된 obfuscation detector 변경사항이 benign-lab에서 오탐을 얼마나 발생시키는지 확인하기 위해 작성했습니다.

이번 테스트는 semantic detector의 on/off 비교가 목적이 아니므로, 기본 설정 그대로 `SemanticSimilarityDetector(mode="auto")` 상태에서 전체 benign-lab을 스캔했습니다. 보고서에서는 전체 finding과 obfuscation 계열 finding을 분리해 정리합니다.

- 테스트 일자: 2026-06-23
- 브랜치: `feature/member2-tool-poisoning`
- 기준 커밋: `3ad0243`
- Python: `3.14.5`

## 테스트 설정

기본 detector 구성은 `create_default_detectors()`가 반환하는 현재 기본 구성을 그대로 사용했습니다.

1. `HiddenInstructionDetector`
2. `SchemaPoisoningDetector`
3. `MetadataPoisoningDetector`
4. `CrossToolInstructionDetector`
5. `MarkdownHiddenLinkDetector`
6. `UnicodeObfuscationDetector`
7. `EncodedPayloadDetector`
8. `HtmlCommentDetector`
9. `HomoglyphDetector`
10. `SemanticSimilarityDetector`

Semantic detector는 별도 비활성화 없이 기본 `auto` 모드입니다.

| 항목 | 확인 결과 |
| --- | --- |
| Semantic mode | `auto` |
| Provider | `SentenceTransformerEmbeddingProvider` |
| 모델 경로 | `models/embedding/bge-small-en-v1.5` |
| Provider 사용 가능 | 예 |
| Semantic finding | 0건 |

## 테스트 대상 및 방법

다음 두 세트의 모든 `tools.json`을 `load_tools_json()`으로 읽고, `Scanner(create_default_detectors())`로 스캔했습니다.

| 세트 | Fixture | Tool | 목적 |
| --- | ---: | ---: | --- |
| `mcp03-benign-100` | 100 | 100 | MCP03 및 난독화 detector 경계 사례 검증 |
| `general-benign-100` | 100 | 100 | 일반적인 MCP 도구 설명의 오탐 검증 |
| 합계 | 200 | 200 | 전체 benign-lab 검증 |

## 결과 요약

| 세트 | Tool | Finding 발생 사례 | 전체 Finding | 전체 사례 기준 오탐률 | Obfuscation 발생 사례 | Obfuscation Finding | Obfuscation 사례 기준 오탐률 | Semantic Finding | Detector 오류 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mcp03-benign-100` | 100 | 1 | 1 | 1.0% | 1 | 1 | 1.0% | 0 | 0 |
| `general-benign-100` | 100 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 0 | 0 |
| 합계 | 200 | 1 | 1 | 0.5% | 1 | 1 | 0.5% | 0 | 0 |

전체 benign-lab 200개 기준으로 finding은 1건이었고, 이 1건은 obfuscation detector에서 발생했습니다.

## Obfuscation 카테고리별 결과

| 카테고리 | Finding 수 | 발생 사례 |
| --- | ---: | ---: |
| `obfuscation.url_encoding` | 1 | 1 |
| `obfuscation.base64` | 0 | 0 |
| `obfuscation.hex` | 0 | 0 |
| `obfuscation.zero_width_unicode` | 0 | 0 |
| `obfuscation.bidi_control` | 0 | 0 |
| `obfuscation.html_comment` | 0 | 0 |
| `obfuscation.homoglyph` | 0 | 0 |

## 탐지된 정상 사례

### BENIGN-032 URL Encoding Explainer

- 경로: `vulnerable-lab/benign-lab/mcp03-benign-100/benign-encoded-content/BENIGN-032-url-encoding-doc/tools.json`
- 도구: `benign_032_url_encoding_doc`
- 정상 설명: `Explain URL encoding examples such as hello%20world.`
- Finding ID: `mcp03-url_encoding-6a7b48328914`
- 분류: `obfuscation.url_encoding`
- OWASP: `MCP03`
- 심각도/신뢰도: `medium` / `medium`
- 위치: `description`
- 디코딩 결과: `hello world.`
- 디코딩 후 의심 문구: `false`

Evidence:

```json
{
  "decoded_excerpt": "hello world.",
  "encoding": "url_encoding",
  "original_excerpt": "hello%20world.",
  "suspicious_after_decoding": false
}
```

이 사례는 URL 인코딩 자체를 설명하는 정상 문서입니다. 디코딩된 문자열도 단순 예시 문구이며, 숨겨진 지시문이나 민감 행동 유도는 없습니다. 따라서 실제 MCP03 tool poisoning이 아니라 `EncodedPayloadDetector`의 정상 예시 문맥 오탐으로 보는 것이 타당합니다.

## 이전 benign auto 테스트와 비교

2026-06-22 보고서의 benign-lab 결과와 비교하면 전체 오탐 양상은 동일합니다.

| 항목 | 2026-06-22 auto 테스트 | 2026-06-23 obfuscation 테스트 |
| --- | ---: | ---: |
| 전체 Tool | 200 | 200 |
| 전체 Finding | 1 | 1 |
| 전체 사례 기준 오탐률 | 0.5% | 0.5% |
| Semantic Finding | 0 | 0 |
| Obfuscation Finding | 1 | 1 |
| 동일 오탐 사례 | `BENIGN-032` | `BENIGN-032` |

이번 `develop` 병합 후 obfuscation detector 변경사항으로 인해 benign-lab에서 새 오탐이 추가로 발생하지는 않았습니다.

## 판단

현재 benign-lab 기준으로 obfuscation detector의 오탐은 200개 중 1개입니다. 프로젝트의 기존 benign false-positive 기준인 세트별 5% 이하를 만족합니다.

다만 남아 있는 1건은 URL encoding 존재만으로 finding을 생성한 사례입니다. `suspicious_after_decoding=false`인 짧은 문서 예시까지 medium finding으로 올릴 필요가 있는지는 개선 여지가 있습니다.

개선 후보:

- URL encoding 디코딩 결과에 의심 문구가 없고, 문맥이 `explain`, `example`, `encoding` 같은 문서 설명이면 finding을 낮추거나 제외합니다.
- 난독화 존재 자체와 악성 payload 확인을 분리해 evidence에 더 명확히 표현합니다.
- `suspicious_after_decoding=false`인 경우 severity/confidence를 낮추는 정책을 검토합니다.

이번 보고서는 탐지 엔진을 변경하지 않고, 현재 기본 설정에서 benign-lab을 스캔한 결과만 기록합니다.
