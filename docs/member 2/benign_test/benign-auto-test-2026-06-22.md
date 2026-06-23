# Member 2 Benign Lab Auto 모드 테스트 보고서

## 문서 목적

이 문서는 기본 detector 구성에서 유사도 모델의 `auto` 모드가 실제로 활성화되는지 확인하고, 전체 benign-lab 200개를 스캔한 결과를 정리합니다.

- 테스트 일자: 2026-06-22
- 브랜치: `feature/member2-tool-poisoning`
- 기준 커밋: `93ae2a9`
- Python: `3.14.5`

## Auto 모드 확인

기본 detector 레지스트리는 `SemanticSimilarityDetector()`를 별도 인자 없이 생성합니다. 생성자의 기본값이 `mode="auto"`이므로 현재 기본 스캔의 semantic mode는 `auto`입니다.

이번 테스트에서는 모델 경로 확인에 그치지 않고 실제 임베딩 생성까지 수행했습니다.

| 항목 | 확인 결과 |
| --- | --- |
| Semantic mode | `auto` |
| Provider | `SentenceTransformerEmbeddingProvider` |
| 모델 | `BAAI/bge-small-en-v1.5` |
| 로컬 경로 | `models/embedding/bge-small-en-v1.5` |
| 모델 경로 존재 | 예 |
| 모델 로딩 | 성공 |
| 임베딩 차원 | 384 |

따라서 이번 결과는 모델이 없어 semantic 검사를 건너뛴 결과가 아닙니다. `auto` 모드가 로컬 모델을 찾아 실제로 semantic similarity 검사를 수행한 상태의 결과입니다.

## 테스트 대상 및 방법

다음 두 세트의 모든 `tools.json`을 `load_tools_json()`으로 읽고, `create_default_detectors()`가 반환하는 기본 detector 10개로 스캔했습니다.

| 세트 | Fixture | Tool | 목적 |
| --- | ---: | ---: | --- |
| `mcp03-benign-100` | 100 | 100 | MCP03 및 난독화 detector의 경계 사례 검증 |
| `general-benign-100` | 100 | 100 | 일반적인 MCP 도구 설명의 오탐 검증 |
| 합계 | 200 | 200 | 전체 benign-lab 검증 |

기본 detector 구성:

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

별도의 detector 비활성화나 threshold 변경 없이 기본 설정을 사용했습니다.

## 결과 요약

| 세트 | Tool | Finding 발생 사례 | 전체 Finding | 사례 기준 오탐률 | Semantic Finding | Detector 오류 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `mcp03-benign-100` | 100 | 1 | 1 | 1.0% | 0 | 0 |
| `general-benign-100` | 100 | 0 | 0 | 0.0% | 0 | 0 |
| 합계 | 200 | 1 | 1 | 0.5% | 0 | 0 |

두 세트 모두 프로젝트 통합 테스트 기준인 세트별 오탐률 5% 이하를 만족했습니다.

### 통합 테스트

```text
pytest -q tests/integration/test_scan_vulnerable_lab.py -k 'benign_lab_false_positive_rate'
```

```text
2 passed, 325 deselected in 23.67s
```

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
- 디코딩 후 의심 문구: 없음

이 사례는 URL 인코딩 자체를 설명하는 정상 문서입니다. 디코딩된 내용에도 숨겨진 지시나 공격 문구가 없으므로 실제 MCP03이 아니라 `EncodedPayloadDetector`의 오탐으로 판단합니다.

## Semantic Detector 평가

Semantic detector는 `auto` 상태에서 모델을 정상 로드해 200개 도구를 검사했지만 Finding을 생성하지 않았습니다.

- Semantic Finding: 0건
- Semantic 오탐 사례: 0개
- Semantic 실행 오류: 0건

즉, 이번 benign-lab 범위에서는 semantic detector를 활성화해도 추가 오탐이 발생하지 않았습니다. 전체 오탐 1건은 semantic detector가 아니라 URL encoding 난독화 detector에서 발생했습니다.

## 판단 및 개선 후보

현재 결과는 전체 사례 기준 오탐률 0.5%로 프로젝트 기준을 충족합니다. Semantic detector의 `auto` 동작도 정상입니다.

다만 `EncodedPayloadDetector`는 URL 인코딩 문자열을 발견하면 디코딩 후 의심 문구가 없어도 medium Finding을 생성합니다. 다음 개선에서는 아래 조건을 검토할 수 있습니다.

- 디코딩 결과에 suspicious phrase가 없는 짧고 단순한 URL 인코딩 예시는 Finding에서 제외합니다.
- 또는 문서·예시 문맥에서는 severity와 confidence를 낮추거나 informational signal로 처리합니다.
- 난독화 존재와 악성 payload 판정을 구분해 MCP03 확정 Finding의 정밀도를 높입니다.

이번 보고서는 현재 구현을 변경하지 않고 기본 `auto` 설정의 실제 동작과 benign-lab 결과만 기록합니다.
