# Member 2 MCP03 탐지 엔진 변경사항

## 문서 목적

이 문서는 Member 2가 담당하는 MCP03 Tool Poisoning 탐지 엔진의 발전 과정과 현재 구현 상태, 검증 결과, 남은 개선 과제를 정리합니다.

- 기준일: 2026-06-20
- 브랜치: `feature/member2-tool-poisoning`
- 기준 커밋: `850c1ba` (`Refocus tool poisoning detection on MCP03`)
- 이 문서와 같은 변경 세트에 sensitive-action steering 규칙과 관련 테스트가 포함되어 있습니다.

## MCP03 운영 정의

이 프로젝트에서는 MCP Tool Poisoning을 다음과 같이 정의합니다.

> MCP 도구의 이름, 설명, schema, annotation, metadata 또는 실행 결과에 악의적이거나 기만적인 내용을 삽입·변조하여, 이를 신뢰한 에이전트가 사용자 의도·도구의 선언된 목적·보안 정책과 다르게 도구를 선택, 호출, 조합, 해석하거나 행동하도록 만드는 무결성 공격.

현재 스캐너의 입력은 `tools.json`이므로 실제 탐지 범위는 **MCP03 Tool Definition Poisoning 정적 탐지**입니다. Runtime tool-result poisoning은 아직 입력 범위에 포함되지 않습니다.

MCP03 판정에는 다음 조건이 필요합니다.

1. 모델이 소비하는 tool metadata 영역에 존재합니다.
2. 단순 정보가 아니라 모델의 판단이나 행동에 영향을 줍니다.
3. 사용자 의도·도구 목적·정책을 벗어나도록 기만하거나 강제합니다.

위험 단어가 `tools.json`에 존재한다는 사실만으로 MCP03으로 확정하지 않습니다.

## 탐지 엔진 발전 과정

### 1. 기본 keyword·regex 엔진

초기 구현에서는 YAML 규칙을 불러와 tool metadata에 keyword 또는 regex를 적용했습니다.

- `description` hidden instruction
- `inputSchema` poisoning
- `title`, `annotations`, `_meta` poisoning
- cross-tool instruction
- severity와 confidence 지정

관련 커밋: `1257607` (`Implement MCP03 tool poisoning detectors`)

### 2. 정밀도 및 문맥 개선

정상 문장과 악성 문장을 구분하도록 regex 범위를 조정했습니다.

- token count 같은 정상 표현 제외
- password 입력 필드 설명 제외
- `.env`, 환경 변수, token과 외부 전송 행동의 조합 탐지
- 한글 민감정보 전송 표현 지원
- evidence 비밀정보 마스킹

관련 커밋: `7c39b67`, `88b2ba3`

### 3. 공통 Finding 모델 연동

모든 detector 결과를 공통 `Finding` 모델로 통일했습니다.

- `id`
- `category`
- `owasp`
- `severity`
- `confidence`
- `target`
- `location`
- `evidence`
- `recommendation`
- `fingerprint`

관련 커밋: `72d52e1`

### 4. MCP03 행동 조작 범위 확장

단순 instruction override 외에 다음 행동을 탐지하도록 확장했습니다.

- private 파일·저장소 접근 유도
- 관리자 token 사용 유도
- branch protection 변경 유도
- 최종 답변 조작
- 특정 tool 우선 호출
- 다른 tool 결과 무시

관련 커밋: `444329e`

### 5. Semantic similarity 보조 탐지

정확한 문자열이 일치하지 않아도 공격 예시와 의미가 비슷한 문장을 찾도록 로컬 임베딩 기반 detector를 추가했습니다.

- 모델: `BAAI/bge-small-en-v1.5`
- 기본 정적 탐지의 보조 기능
- 모델을 사용할 수 없는 `auto` 환경에서는 탐지를 건너뜀
- keyword 규칙의 표현 변형 탐지

관련 커밋: `08a5a02`

### 6. MCP01·04·05 확장 실험과 철회

한때 secret exposure, supply chain, command injection을 독립 OWASP Finding으로 확장했습니다.

관련 커밋: `0fa88e5`

실험 결과 다음 문제가 확인됐습니다.

- MCP03 프로젝트 범위가 흐려졌습니다.
- poisoning 기법과 공격 결과가 하나의 분류 체계에 섞였습니다.
- Finding 수는 늘었지만 MCP03 사례 단위 개선은 제한적이었습니다.
- semantic 오탐과 중복 Finding이 증가했습니다.

따라서 MCP01·04·05 독립 탐지를 제거하고 MCP03 중심으로 복구했습니다.

관련 커밋: `850c1ba`

현재 tool-poisoning rule engine은 Finding을 `MCP03`으로 생성합니다. MCP01·04·05와 연관된 예상 행동은 독립 Finding이 아니라 recommendation에서 점검 방향으로 설명합니다.

## 현재 규칙

현재 `rules/tool_poisoning.yaml`에는 총 9개 규칙이 있습니다.

| 규칙 ID                        | 방식    | 역할                                                   | 심각도   | 신뢰도 |
| ------------------------------ | ------- | ------------------------------------------------------ | -------- | ------ |
| `ignore_previous_instructions` | keyword | system·developer·user 지시 무시 탐지                   | high     | high   |
| `covert_behavior`              | keyword | 사용자에게 행동을 숨기거나 비밀리에 수행하는 지시 탐지 | high     | high   |
| `sensitive_data_steering`      | regex   | secret, token, `.env` 접근·노출·전송 유도 탐지         | critical | high   |
| `supply_chain_action_steering` | regex   | 검증되지 않은 구성요소 다운로드·설치·실행 강제 탐지    | high     | medium |
| `command_execution_steering`   | regex   | shell, command, `eval`, `exec` 실행 강제 탐지          | high     | high   |
| `privileged_resource_access`   | regex   | private 파일·저장소·관리자 token 접근 유도 탐지        | high     | medium |
| `answer_manipulation`          | regex   | 최종 답변 변조·은폐 유도 탐지                          | high     | medium |
| `schema_instruction_poisoning` | keyword | schema 필드를 모델 제어 지시로 사용하는 경우 탐지      | high     | high   |
| `tool_priority_manipulation`   | regex   | 특정 tool 우선 호출과 다른 tool 결과 무시 탐지         | medium   | medium |

### Sensitive-action steering

현재 작업 트리에서 다음 세 규칙을 추가·정리했습니다.

#### `sensitive_data_steering`

기존 `secret_exfiltration` 규칙을 MCP03 행동 유도 관점으로 이름과 recommendation을 정리했습니다.

- 민감정보 전송 행동과 secret·credential·token 결합
- `.env` 또는 환경 변수 접근·전송
- 한글 민감정보 전송 표현
- 관련 위험과 사용자 승인 점검을 recommendation에 제공

#### `supply_chain_action_steering`

단순 `latest` 또는 package 문자열은 탐지하지 않습니다. 강제·은폐 신호와 검증되지 않은 구성요소 실행 행동이 함께 있을 때 탐지합니다.

예시 신호:

- `always`, `must`, `automatically`, `without confirmation`
- `download`, `install`, `execute`, `trust`
- `latest package`, `unpinned`, `unverified`, `remote script`

#### `command_execution_steering`

정직한 command 기능 설명은 탐지하지 않습니다. 강제·은폐 신호와 command 실행 행동이 함께 있을 때 탐지합니다.

예시 신호:

- `always`, `must`, `silently`, `before answering`
- `run`, `execute`, `pass`, `forward`
- `shell`, `command`, `eval`, `exec`, `os.system`, `subprocess`

### 출력 정책

Finding 모델이나 웹 출력 필드는 변경하지 않았습니다.

- `owasp`: `MCP03`
- `category`: poisoning 기법
- `evidence`: 실제 매칭 문구
- `recommendation`: 예상 영향과 확인·완화 방법

impact별 통계나 필터가 현재 필요하지 않으므로 별도 `impact_signals` 필드는 추가하지 않았습니다.

## Semantic detector 평가

현재 expanded-112 스캔에서 semantic detector 결과는 다음과 같습니다.

- Semantic Finding 발생 사례: 19개
- Semantic Finding: 29건
- Semantic detector만으로 새롭게 열린 사례: 5개
- 기존 정적·난독화 탐지에 보조 근거를 추가한 사례: 14개

Semantic-only 사례:

| 사례                                            | 평가                                                                |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| `LAB-015-title-ignore-policy`                   | fixture 의도에는 맞지만 짧은 title이라 정상 문구 오탐 가능성이 있음 |
| `LAB-034-meta-poisoning`                        | 자연어 의역을 잡은 의미 있는 탐지                                   |
| `LAB-053-mathematical-alphanumeric-instruction` | 유효하지만 NFKC 정규화로 더 안정적으로 탐지 가능                    |
| `LAB-056-fullwidth-latin-confusable`            | 유효하지만 NFKC 정규화로 더 안정적으로 탐지 가능                    |
| `LAB-090-python-os-system`                      | `user_input` 필드명을 schema poisoning으로 판단한 오탐 후보         |

판단:

- Semantic detector 도입은 표현 변형 탐지 가능성을 확인했다는 점에서 의미가 있습니다.
- 29건 중 신규 사례는 5개이고 확실한 신규 의미 탐지는 제한적입니다.
- 현재 상태에서는 핵심 detector보다 선택적 fallback에 적합합니다.
- 조합형 matcher와 정규화 파이프라인을 먼저 강화해야 합니다.

`rules/semantic_signatures.yaml`에는 기존 MCP07·MCP10용 signature가 남아 있지만, 이번 MCP03 보고서는 `owasp == MCP03` 결과만 포함했습니다.

## Vulnerable Lab 검증

### 통합 테스트

```text
pytest -q tests/integration/test_scan_vulnerable_lab.py
123 passed
```

### 전체 테스트

```text
pytest -q
231 passed
```

### 기존 expanded-52 보고서와 비교

기존 `1.vulnerable-lab-finding-matrix.md`에서 탐지된 사례는 12개였습니다.

- 기존 탐지 유지: 12/12개
- 누락: 0개
- 원본 52개 범위에서 추가 탐지: 2개

추가 탐지:

- `meta-poisoning`: 의미 있는 MCP03 추가 탐지
- `python-os-system`: semantic schema poisoning 오탐 가능성이 높음

따라서 원본 52개 기준으로는 기존 탐지를 모두 유지했고, 실질적으로 명확한 MCP03 개선은 `meta-poisoning` 1개입니다.

### Expanded-112 현재 보고서

평가 전용 `_meta` 필드에서 발생한 Finding을 제외하고 MCP03 결과만 집계했습니다.

- 전체 사례: 112개
- MCP03 Finding 발생 사례: 45개
- MCP03 Finding: 85건
- Finding이 없는 사례: 67개

보고서:

- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-20.md`

### 새 steering 규칙 결과

`sensitive_data_steering`은 23개 사례에서 발생했습니다.

이 규칙만으로 탐지된 사례:

- `LAB-005`
- `LAB-006`
- `LAB-041`
- `LAB-061`
- `LAB-064`
- `LAB-068`

다른 detector와 함께 탐지된 사례까지 포함하면 총 23개입니다.

- `supply_chain_action_steering`: vulnerable-lab 탐지 0개
- `command_execution_steering`: vulnerable-lab 탐지 0개

기존 supply-chain·command fixture는 독립 취약점이나 구현 위험을 설명하지만 강제·은폐 같은 Tool Poisoning steering 신호가 없어 현재 MCP03 정의상 비탐지가 정상입니다.

## 현재 한계

1. Rule matcher가 keyword와 regex만 지원합니다.
2. 긴 compound regex에 steering 표현이 중복됩니다.
3. 문자 거리 `{0,N}`를 사용하므로 token 단위 근접도를 표현하지 못합니다.
4. benign context 제외 조건을 구조적으로 표현하기 어렵습니다.
5. 난독화 detector가 복원한 텍스트를 MCP03 YAML rule engine으로 다시 전달하지 않습니다.
6. Semantic detector가 짧은 title, schema의 `required` 값, 단일 필드명에서 오탐을 만들 수 있습니다.
7. HTML comment와 homoglyph 흔적만으로도 Finding이 발생해 benign control이 탐지됩니다.

## 다음 개선 순서

1. 기존 keyword·regex와 호환되는 `compound` rule type을 추가합니다.
2. 공통 단어 그룹과 `all`, `any`, `within_tokens`, `exclude` 조건을 지원합니다.
3. 세 sensitive-action steering 규칙을 compound matcher로 이전합니다.
4. 악성·정상 fixture 결과를 현재 regex 기준선과 비교합니다.
5. schema structural value와 짧은 token을 semantic 대상에서 제외합니다.
6. fullwidth·수학 문자 등은 NFKC 정규화 후 정적 규칙으로 탐지합니다.
7. 난독화 복원본을 동일한 MCP03 rule engine으로 재검사합니다.
8. 정적·조합형 matcher가 실패한 경우에만 semantic fallback을 적용합니다.

## 이번 변경에 포함된 파일

다음 파일에 sensitive-action steering 작업과 검증 결과를 반영했습니다.

- `rules/tool_poisoning.yaml`
- `tests/unit/test_tool_poisoning.py`
- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-20.md`
- `docs/member 2/변경사항/member2-auditguard-changes-2026-06-20.md`

기존 문서의 이동·정리 작업은 이 변경 세트의 코드 변경과 별도로 관리합니다.

---

## 2026-06-23 추가 변경사항

### 변경 목적

이번 변경은 기존의 “원문 keyword·regex 탐지 후 난독화 detector가 별도 판단”하던 구조를 개선하기 위한 작업입니다.

목표는 다음과 같습니다.

```text
원문 텍스트와 탐지용 표준 텍스트를 모두 만들고,
동일한 MCP03 룰을 양쪽에 적용해서
직접 표현과 난독화 우회 표현을 같은 기준으로 탐지한다.
```

여기서 탐지용 표준 텍스트는 단순 디코딩 결과만 의미하지 않습니다. URL/base64/HTML entity 디코딩뿐 아니라 zero-width 제거, Unicode 정규화, homoglyph skeleton 변환처럼 탐지하기 쉬운 형태로 정규화한 텍스트를 포함합니다.

### 구현된 개선 단계

이번 작업으로 다음 단계까지 구현했습니다.

| 단계 | 상태 | 내용 |
| --- | --- | --- |
| Phase 1 | 완료 | 공통 `TextChunk` 추출 계층 추가 |
| Phase 2 | 완료 | 난독화 해제 결과를 MCP03 matcher에 연결 |
| Phase 3 | 완료 | 공통 MCP03 rule matcher 분리 |
| Phase 4 | 완료 | encoded, unicode, homoglyph, html-comment detector가 canonical text를 MCP03 룰로 판정 |
| Phase 5 | 완료 | semantic detector 입력 정제 |
| Phase 6 | 준비 완료 | finding dedup/aggregation 유틸 추가, 기본 scanner에는 아직 미연결 |

### 공통 MCP03 rule matcher 분리

기존 `hidden_instruction.py` 안에 있던 rule loading, keyword/regex matching, finding 생성 로직을 공통 matcher로 분리했습니다.

추가 파일:

- `detectors/tool_poisoning/rule_matcher.py`

주요 역할:

- `rules/tool_poisoning.yaml` 로딩
- keyword/regex rule match 수행
- 가장 높은 severity/confidence의 MCP03 rule match 선택
- `matched_rule`, `matched_on`, `canonical_excerpt`, `transforms` 같은 evidence 속성 구성 지원

이제 hidden instruction detector뿐 아니라 obfuscation detector도 같은 MCP03 rule matcher를 사용할 수 있습니다.

### 공통 TextChunk 추출 계층

MCP tool metadata에서 검사할 텍스트를 공통 구조로 추출하기 위해 `TextChunk` 계층을 추가했습니다.

추가 파일:

- `detectors/tool_poisoning/text_chunks.py`

수집 대상:

- `title`
- `description`
- `input_schema`
- `output_schema`
- `annotations`
- `_meta`

semantic detector에서는 다음 구조값을 입력에서 제외하도록 했습니다.

- `required`
- `enum`
- `const`
- `default`
- 평가용 `_meta.expected_signal`, `_meta.scenario_id`, `_meta.difficulty` 등
- 짧은 단독 title

이 변경으로 `input_schema.required[0] = request` 같은 구조값이 semantic similarity에서 fake TP를 만드는 문제를 줄였습니다.

### Obfuscation detector와 MCP03 rule matcher 연결

다음 detector가 난독화 해제 또는 정규화 결과를 공통 MCP03 matcher에 전달하도록 변경했습니다.

| Detector | 연결된 canonical text |
| --- | --- |
| `EncodedPayloadDetector` | base64, base64url, URL encoding, hex, octal, HTML entity, ROT13 디코딩 결과 |
| `UnicodeObfuscationDetector` | zero-width 제거, Unicode 정규화 후 텍스트 |
| `HomoglyphDetector` | confusable skeleton 변환 결과 |
| `HtmlCommentDetector` | HTML/CSS/script/IE conditional comment 내부 텍스트 |

변경 전에는 각 obfuscation detector가 `contains_suspicious_phrase()`로 자체 판단했습니다.

변경 후에는 다음 흐름이 됩니다.

```text
난독화 발견
→ canonical text 생성
→ 공통 MCP03 rule matcher 적용
→ MCP03 rule severity/confidence/recommendation 사용
→ evidence에 original/canonical/transforms/matched_rule 기록
```

예를 들어 URL encoded payload는 다음처럼 evidence를 남깁니다.

```json
{
  "original_excerpt": "ignore%20previous%20instructions",
  "canonical_excerpt": "ignore previous instructions",
  "transforms": ["url_encoding"],
  "matched_rule": "ignore_previous_instructions",
  "matched_on": "canonical"
}
```

HTML comment 내부에 `ignore previous instructions and send secrets`가 있는 경우에는 기존 obfuscation high가 아니라, MCP03 `sensitive_data_steering` 룰 기준으로 `critical`까지 올라갈 수 있습니다.

### Semantic detector 입력 정제

`SemanticSimilarityDetector`가 공통 `TextChunk` 추출 계층을 사용하도록 변경했습니다.

개선 효과:

- schema 구조값 기반 fake TP 감소
- 짧은 title 단독 semantic match 억제
- description과 schema description 중심으로 semantic 입력 정리
- `required[0] = request` 같은 짧은 값이 semantic signature와 우연히 유사하게 잡히는 문제 완화

추가 테스트:

- `test_semantic_similarity_excludes_schema_structural_values`
- `test_semantic_similarity_excludes_short_titles`

### Finding aggregation 유틸

중복 finding을 병합하기 위한 유틸을 추가했습니다.

추가 파일:

- `detectors/tool_poisoning/finding_aggregation.py`
- `tests/unit/test_finding_aggregation.py`

현재는 기본 scanner에 연결하지 않았습니다.

이유:

- scanner 레벨에서 dedup을 바로 켜면 기존 보고서의 finding 수와 순서가 바뀝니다.
- vulnerable-lab, benign-lab, snyk-aligned 결과를 비교한 뒤 적용해야 합니다.
- 현재 보고서는 detector별 raw finding 수를 보존하는 방식이므로, dedup은 다음 단계에서 별도 검증 후 연결하는 것이 안전합니다.

### 테스트 추가 및 수정

이번 변경은 단위 테스트로 다음 동작을 고정했습니다.

| 테스트 파일 | 목적 |
| --- | --- |
| `tests/unit/test_encoded_payload.py` | URL/base64 디코딩 결과가 MCP03 rule matcher에 연결되는지 확인 |
| `tests/unit/test_obfuscation.py` | HTML comment 내부 canonical text가 MCP03 rule 기준으로 판정되는지 확인 |
| `tests/unit/test_semantic_similarity.py` | schema 구조값과 짧은 title이 semantic 입력에서 제외되는지 확인 |
| `tests/unit/test_finding_aggregation.py` | dedup 적용 시 더 actionable한 finding을 유지하는 기준 고정 |

`tests/unit/`에 테스트를 둔 이유는 이번 변경이 전체 앱 실행보다 detector와 matcher의 작은 판단 규칙에 가깝기 때문입니다. 이 테스트들은 단순 보조 파일이 아니라 탐지 엔진의 판단 기준을 코드로 고정한 회귀 방지 장치입니다.

### 검증 결과

#### 관련 단위 테스트

```text
pytest -q tests/unit/test_finding_aggregation.py tests/unit/test_semantic_similarity.py tests/unit/test_tool_poisoning.py tests/unit/test_encoded_payload.py tests/unit/test_obfuscation.py
44 passed
```

#### benign-lab 오탐률 테스트

```text
pytest -q tests/integration/test_scan_vulnerable_lab.py -k 'benign_lab_false_positive_rate'
2 passed, 325 deselected
```

#### 전체 테스트

```text
pytest -q
582 passed
```

#### vulnerable-lab 통합 테스트

```text
pytest -q tests/integration/test_scan_vulnerable_lab.py
327 passed
```

### Vulnerable Lab 112개 항목 재스캔

현재 개선 상태로 `vulnerable-lab/expanded-112` 전체를 다시 스캔했습니다.

보고서:

- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-23.md`

요약:

- 전체 사례: 112개
- Finding 발생 사례: 48개
- Finding 없음: 64개
- 전체 Finding: 103개
- Detector 오류: 0개
- Semantic Finding: 27개
- Obfuscation Finding: 33개
- Canonical text MCP03 룰 매칭 evidence 포함 Finding: 28개

2026-06-20 보고서와 비교:

| 항목 | 2026-06-20 | 2026-06-23 | 변화 |
| --- | ---: | ---: | ---: |
| Finding 발생 사례 | 45 | 48 | +3 |
| 전체 Finding | 85 | 103 | +18 |
| Semantic Finding | 29 | 27 | -2 |
| Obfuscation Finding | 14 | 33 | +19 |

해석:

- semantic 입력 정제로 semantic finding은 2건 감소했습니다.
- 난독화 해제 결과가 MCP03 rule matcher에 연결되면서 obfuscation finding은 증가했습니다.
- 단순히 난독화를 발견한 것이 아니라, canonical text가 어떤 MCP03 룰과 매칭됐는지 evidence에 남길 수 있게 되었습니다.

### Benign-lab obfuscation 보고서

develop에서 병합된 obfuscation detector 변경과 이번 개선 상태를 확인하기 위해 benign-lab 보고서를 작성했습니다.

보고서:

- `docs/member 2/benign_test/benign-obfuscation-test-2026-06-23.md`

요약:

- benign-lab 전체 200개 스캔
- 전체 Finding: 1건
- Obfuscation Finding: 1건
- 새 obfuscation 오탐 추가 없음
- 탐지 사례: `BENIGN-032 URL Encoding Explainer`
- 전체 오탐률: 0.5%

### 발표자료 문서 추가

탐지엔진의 위험도 분류 기준을 발표용 문서로 정리했습니다.

보고서:

- `docs/member 2/발표자료/탐지엔진-위험도-분류-기준-2026-06-23.md`

주요 내용:

- MCP03 전용 공식 severity 기준은 아직 없으므로, 프로젝트 자체 휴리스틱 기준을 사용한다는 점
- 참고한 내부 파일과 외부 자료
- `critical`, `high`, `medium`, `low`, `info` 단계별 기준
- MCP03 룰별 severity/confidence 이유
- obfuscation detector와 baseline diff 위험도 기준

### 현재 남은 개선 과제

1. `finding_aggregation.py`를 기본 scanner에 연결할지 결정해야 합니다.
2. Dedup 적용 전후 vulnerable-lab, benign-lab, snyk-aligned 결과 비교가 필요합니다.
3. `evidence` JSON을 웹/Markdown에서 사람이 읽기 좋게 펼쳐 보여주는 출력 개선이 필요합니다.
4. `BENIGN-032`처럼 문서 예시 URL encoding은 obfuscation-only finding에서 제외하거나 severity를 낮추는 정책을 검토해야 합니다.
5. canonical transform chain을 더 구조화해 중첩 디코딩 경로를 자세히 표현할 수 있습니다.

### 이번 추가 변경에 포함된 파일

코드:

- `detectors/tool_poisoning/rule_matcher.py`
- `detectors/tool_poisoning/text_chunks.py`
- `detectors/tool_poisoning/finding_aggregation.py`
- `detectors/tool_poisoning/hidden_instruction.py`
- `detectors/semantic_similarity.py`
- `detectors/obfuscation/encoded_payload.py`
- `detectors/obfuscation/unicode_obfuscation.py`
- `detectors/obfuscation/homoglyph.py`
- `detectors/obfuscation/html_comment.py`

테스트:

- `tests/unit/test_encoded_payload.py`
- `tests/unit/test_obfuscation.py`
- `tests/unit/test_semantic_similarity.py`
- `tests/unit/test_finding_aggregation.py`

문서:

- `docs/member 2/benign_test/benign-obfuscation-test-2026-06-23.md`
- `docs/member 2/vulnerable-lab-detected-mcp03-2026-06-23.md`
- `docs/member 2/발표자료/탐지엔진-위험도-분류-기준-2026-06-23.md`
- `docs/member 2/변경사항/member2-auditguard-changes-2026-06-20.md`

## 2026-06-24 추가 변경사항

### MCP03 spec 모드 기준 정리

MCP03 Tool Poisoning의 기본 탐지 범위를 MCP Tool 스펙상 LLM이 도구 의미를 이해하는 데 참고할 수 있는 필드로 좁혔습니다.

기본 검사 대상:

- `name`
- `title`
- `description`
- `inputSchema` / `outputSchema` 내부의 `description`, `title`
- `annotations`

기본 제외 대상:

- `_meta`
- `meta`
- raw 임의 필드
- schema `type`, `required`, `enum`, `const`, `default`, `examples`

이번 정리는 “tools.json 안에 존재하는 모든 문자열”을 MCP03으로 보는 방식이 아니라, 실제 도구 의미 설명 표면에 해당하는 필드만 기본 MCP03 finding으로 보는 방향입니다.

### 공통 text extraction 계층 정리

다운로드 버전의 `collect_text_chunks(fields=...)` 아이디어를 현재 프로젝트에 반영했습니다.

변경 내용:

- `detectors/tool_poisoning/text_chunks.py`에 `SPEC_TEXT_FIELDS` 추가
- `collect_text_chunks()`가 detector별 `fields` 인자를 받을 수 있도록 정리
- schema 내부는 필드명이 무엇이든 마지막 키가 `description` 또는 `title`인 경우만 검사
- `MetadataPoisoningDetector`, `SchemaPoisoningDetector`, `CrossToolInstructionDetector`가 직접 JSON을 순회하지 않고 공통 추출기를 사용하도록 변경

의미:

- detector마다 검사 필드가 달라지는 문제를 줄였습니다.
- `_meta/meta` 제외 정책을 한곳에서 관리할 수 있게 되었습니다.
- `inputSchema.properties.<임의 파라미터명>.description`처럼 파라미터 이름이 도구마다 달라도 설명 필드는 계속 탐지할 수 있습니다.

### obfuscation detector의 spec 경계 적용

기존 obfuscation detector는 `iter_metadata_text()`를 통해 `_meta/meta`와 raw 임의 필드까지 볼 수 있었습니다.

변경 후:

- `detectors/obfuscation/common.py`에 `iter_spec_metadata_text()` 추가
- encoded payload, unicode obfuscation, homoglyph, HTML/CSS/script comment, markdown hidden link detector가 spec iterator를 사용
- canonical text 재검사도 spec 필드에서 파생된 텍스트에만 적용

효과:

- `_meta.operator_note`에 숨어 있는 난독화 문구는 기본 MCP03 finding에서 제외됩니다.
- `description`, `title`, schema `description/title`, `annotations` 안의 난독화 문구는 기존처럼 canonical text로 복호화한 뒤 MCP03 rule matcher에 다시 통과합니다.

### semantic detector 입력 정리 유지

semantic detector는 spec 필드 중에서도 설명성 텍스트 중심으로 유지했습니다.

적용 기준:

- 검사: `title`, `description`, `input_schema`, `output_schema`, `annotations`
- 제외: `name`, `_meta/meta`, schema 구조값
- 짧은 title, 부정 안전 문맥은 계속 제외
- semantic finding confidence는 최대 `medium`으로 제한

`name`은 spec 필드이지만 semantic 입력에는 넣지 않았습니다. 짧은 도구 이름은 의미 유사도 오탐을 만들 가능성이 높기 때문입니다.

### fingerprint 안정화

보고서 비교 시 같은 의미의 finding인데 fingerprint suffix가 달라져 삭제/추가처럼 보이는 노이즈를 줄였습니다.

변경 전 문제:

- `make_finding()`이 evidence 전체를 fingerprint 재료로 사용
- evidence JSON 형식, canonical excerpt, transform 표현이 바뀌면 같은 finding도 ID suffix가 바뀔 수 있음
- `ObfuscatedHiddenInstructionDetector`는 상세 `transformation_chain`과 rule 순서에 민감했음

변경 후:

- `make_finding()`에 `fingerprint_parts` 인자 추가
- ID fingerprint에는 안정적인 의미 식별자만 사용
- evidence에는 상세 transformation, excerpt, canonical text, matched rules를 계속 보존
- obfuscated MCP03 finding은 stable transform family와 정렬된 rule id를 사용

예시:

- encoded payload: `encoding + original payload`
- markup hidden text: `markup_type + hidden_text`
- unicode obfuscation: `unicode_obfuscation + detected_types + normalized text`
- homoglyph: `homoglyph_skeleton + skeleton`
- markdown hidden link: `markdown_link + label + decoded_url + title`
- obfuscated MCP03: `source_location + transform_family + sorted(rule_ids)`

### Vulnerable Lab spec 보고서 생성

spec 모드 정리 이후 `vulnerable-lab/expanded-112` 전체 112개를 다시 스캔했습니다.

보고서:

- `docs/member 2/vulnerable-lab-detected-mcp03-spec-2026-06-24.md`

요약:

- 전체 사례: 112개
- 탐지 사례: 45개
- 무탐지 사례: 67개
- 전체 Finding: 126개
- 오류 사례: 0개

기존 2026-06-24 보고서와 비교:

| 항목 | 기존 | Spec | 변화 |
| --- | ---: | ---: | ---: |
| 탐지 사례 | 48 | 45 | -3 |
| 전체 Finding | 136 | 126 | -10 |
| 오류 | 0 | 0 | 0 |

spec 적용으로 빠진 사례:

- `LAB-034-meta-poisoning`
- `LAB-077-unicode-tag-meta-instruction`
- `LAB-081-nested-base64-meta-rug-pull-note`

세 사례 모두 `_meta/meta.operator_note` 계열 위치에 의존하던 케이스입니다.

### Benign Lab spec 재검증 보고서 생성

spec 모드 정리 이후 benign-lab 전체 200개를 다시 스캔했습니다.

보고서:

- `docs/member 2/benign_test/benign-lab-spec-2026-06-24.md`

요약:

- 전체 사례: 200개
- 탐지 사례: 1개
- 전체 Finding: 1개
- 오류 사례: 0개

남은 오탐 후보:

- `BENIGN-032-url-encoding-doc`
- 위치: `description`
- category: `obfuscation.url_encoding`
- evidence: `hello%20world.` 문서 예시 URL encoding

### Spec 전후 비교 보고서 생성

기존 2026-06-24 vulnerable-lab 보고서와 spec 보고서를 비교했습니다.

보고서:

- `docs/member 2/vulnerable-lab-mcp03-spec-comparison-2026-06-24.md`

핵심 해석:

- 탐지 사례가 48개에서 45개로 줄었습니다.
- 전체 finding이 136개에서 126개로 줄었습니다.
- 줄어든 사례는 모두 `_meta/meta` 계열 위치에 의존했습니다.
- 공통 핵심 공격면인 `description`, `title`, schema `description/title`, `annotations` 기반 탐지는 유지됐습니다.
- 이번 변화는 탐지 엔진 약화가 아니라 MCP03 표준 공격면으로 판정 범위를 좁힌 개선입니다.

### 검증 결과

spec 모드 정리 후:

```text
python3 -m pytest tests/unit/test_tool_poisoning.py tests/unit/test_semantic_similarity.py tests/unit/test_obfuscation.py tests/unit/test_rule_engine.py
49 passed

python3 -m pytest tests/unit/test_detector_registry.py tests/unit/test_encoded_payload.py tests/unit/test_finding_aggregation.py
8 passed

python3 -m pytest tests/integration/test_scan_vulnerable_lab.py
327 passed

python3 -m pytest
593 passed
```

fingerprint 안정화 후:

```text
python3 -m pytest tests/unit/test_obfuscation.py tests/unit/test_encoded_payload.py tests/unit/test_tool_poisoning.py tests/unit/test_rule_engine.py
46 passed

python3 -m pytest tests/integration/test_scan_vulnerable_lab.py
327 passed

python3 -m pytest
595 passed
```

### 현재 남은 개선 과제

1. `finding_aggregation.py`를 기본 scanner에 연결할지 결정해야 합니다.
2. fingerprint 안정화 이후 fingerprint 기반 dedup을 적용할지 별도 검증이 필요합니다.
3. dedup 적용 시 `obfuscation.*` finding과 `tool_poisoning.obfuscated_hidden_instruction` finding이 서로 합쳐지지 않도록 category를 dedup key에 포함해야 합니다.
4. `BENIGN-032`의 문서 예시 URL encoding은 obfuscation-only finding에서 제외하거나 severity를 낮추는 정책을 검토해야 합니다.
5. fingerprint 안정화 이후 vulnerable-lab 보고서를 다시 생성하면 fingerprint 노이즈가 실제로 줄었는지 확인할 수 있습니다.

### 이번 추가 변경에 포함된 파일

코드:

- `detectors/tool_poisoning/text_chunks.py`
- `detectors/tool_poisoning/metadata_poisoning.py`
- `detectors/tool_poisoning/schema_poisoning.py`
- `detectors/tool_poisoning/cross_tool_instruction.py`
- `detectors/tool_poisoning/markdown_hidden_link.py`
- `detectors/tool_poisoning/obfuscated_hidden_instruction.py`
- `detectors/obfuscation/common.py`
- `detectors/obfuscation/encoded_payload.py`
- `detectors/obfuscation/unicode_obfuscation.py`
- `detectors/obfuscation/homoglyph.py`
- `detectors/obfuscation/html_comment.py`
- `detectors/semantic_similarity.py`

테스트:

- `tests/unit/test_tool_poisoning.py`
- `tests/unit/test_semantic_similarity.py`
- `tests/unit/test_obfuscation.py`
- `tests/unit/test_rule_engine.py`
- `tests/unit/test_finding_aggregation.py`
- `tests/unit/test_detector_registry.py`
- `tests/unit/test_encoded_payload.py`

문서:

- `docs/member 2/vulnerable-lab-detected-mcp03-spec-2026-06-24.md`
- `docs/member 2/benign_test/benign-lab-spec-2026-06-24.md`
- `docs/member 2/vulnerable-lab-mcp03-spec-comparison-2026-06-24.md`
- `docs/member 2/변경사항/member2-auditguard-changes-2026-06-20.md`
