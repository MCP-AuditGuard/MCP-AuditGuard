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
