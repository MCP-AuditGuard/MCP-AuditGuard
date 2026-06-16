# Member 5 코드 설명: CLI, Report, Baseline, Diff

이 문서는 MCP-AuditGuard 프로젝트에서 팀원 5가 담당한 코드의 목적과 흐름을 설명한다.

팀원 5는 AuditGuard의 탐지 결과를 실제 사용자가 실행하고 확인할 수 있는 형태로 만드는 역할을 담당했다. CLI는 `tools.json` 입력을 받아 scanner를 실행하고, 결과를 Markdown 또는 JSON 리포트로 변환한다. 또한 baseline 저장과 diff 기능을 통해 이전에 정상으로 판단한 MCP tool metadata가 이후 변경되었는지 확인할 수 있다. 이 구조는 Tool Poisoning의 rug-pull 시나리오를 탐지하는 데 유용하며, detector가 추가되어도 동일한 Finding 구조를 통해 리포트로 출력할 수 있다는 장점이 있다.

## 1. 팀원 5 담당 범위

팀원 5의 담당 범위는 사용자-facing workflow다.

- Typer 기반 CLI 구현
- `scan` 명령어 구현
- Markdown report 생성
- JSON report 생성
- metadata hash 생성
- baseline 저장
- 이전 baseline과 현재 metadata diff 비교
- tool 추가/삭제/변경 탐지
- rug-pull finding 생성
- help 명령어 및 AuditGuard 사용 가이드 출력
- 로컬 임베딩 유사도 기반 semantic detector를 CLI/report/help 흐름에 연결

탐지 detector 자체를 새로 만드는 역할은 아니며, detector와 baseline diff 결과를 사용자가 볼 수 있는 결과물로 연결하는 역할이다.

## 2. 각 파일의 역할

### `cli/scan.py`

AuditGuard CLI의 entrypoint다.

주요 역할:

- `python -m cli.scan scan --input tools.json` 형태의 scan 명령 제공
- `--input`, `--format`, `--output`, `--save-baseline`, `--baseline` 옵션 처리
- `--enable-semantic`, `--semantic-threshold`, `--embedding-model-path` 옵션 처리
- tools.json 수집 함수 호출
- scanner 실행
- baseline 저장 및 baseline diff 연결
- Markdown/JSON renderer 호출
- 터미널 출력 또는 파일 저장
- 사용자 친화적인 에러 메시지 출력
- 별도 `help` command 제공

보안적 의미:

CLI는 비전문 사용자도 MCP tool metadata 보안 점검을 실행할 수 있게 해준다. 사용자는 MCP 서버를 AI Agent에 연결하기 전, tool description, schema, annotations 등에 숨은 Tool Poisoning 위험을 사전에 확인할 수 있다.

semantic scan은 기본값으로 꺼져 있다. 로컬 임베딩 모델 로딩은 느릴 수 있고 팀원별 개발 환경에 모델이 없을 수 있기 때문이다. 사용자가 `--enable-semantic`을 명시했을 때만 semantic detector를 연결한다.

### `reports/markdown_report.py`

Finding 목록을 사람이 읽기 쉬운 Markdown 리포트로 변환한다.

주요 역할:

- 리포트 제목 출력
- severity count 요약
- finding별 OWASP, severity, tool, target, evidence, recommendation 출력
- semantic finding의 confidence, similarity score, matched reference, detector type 출력
- finding이 없을 때 `No findings detected.` 출력

보안적 의미:

Markdown 리포트는 발표, 수동 보안 리뷰, 팀원 간 공유에 적합하다. evidence와 recommendation을 함께 보여주기 때문에 사용자가 왜 위험한지와 어떤 조치를 해야 하는지 바로 이해할 수 있다.

### `reports/json_report.py`

Finding 목록을 자동화용 JSON 배열로 변환한다.

주요 역할:

- Finding을 dict로 변환
- 자동화에 필요한 핵심 필드만 출력
- semantic detector의 `similarity_score`, `matched_reference`, `detector_type`, `confidence` 보존
- embedding vector 계열 필드는 report에 저장하지 않음
- `ensure_ascii=False`로 한글 보존
- `indent=2`로 사람이 읽기 쉬운 JSON 출력

보안적 의미:

JSON 리포트는 GitHub Actions, dashboard, 후속 분석 도구, SARIF 변환 같은 자동화 흐름에 연결하기 쉽다. 사람이 읽는 Markdown과 달리 기계가 안정적으로 파싱할 수 있다.

semantic detector 결과는 자동화에서 threshold 조정이나 dashboard 시각화에 활용될 수 있다. 다만 embedding vector 자체는 용량과 민감정보 처리 이슈가 있으므로 JSON report에 포함하지 않는다.

### `core/baseline_store.py`

현재 MCP tool metadata 상태를 baseline JSON으로 저장하고 로드한다.

주요 역할:

- ToolMetadata 정규화
- SHA-256 metadata hash 생성
- baseline dict 생성
- baseline JSON 파일 저장
- baseline JSON 파일 로드

보안적 의미:

MCP Tool Poisoning은 처음에는 정상처럼 보이다가 나중에 description, schema, annotations에 악성 지시문을 추가하는 방식으로 발생할 수 있다. baseline은 이전 정상 상태를 저장해두고 이후 변경을 감지하기 위한 기준점이다.

baseline에는 embedding vector를 저장하지 않는다. baseline diff의 목적은 metadata 변경 감지이며, vector는 모델 버전에 따라 달라질 수 있고 용량도 크기 때문이다. semantic 위험도는 scan 시점의 Finding으로 보고, metadata 변경 여부는 hash로 추적한다.

### `core/diff_engine.py`

이전 baseline과 현재 tool metadata를 비교해 변경 finding을 만든다.

탐지 기준:

- `BASELINE-001`: 새 tool 추가
- `BASELINE-002`: 기존 tool 삭제
- `BASELINE-003`: 기존 tool metadata hash 변경

보안적 의미:

같은 tool 이름이라도 description이나 schema가 바뀌면 악성 instruction이 새로 삽입되었을 수 있다. 그래서 modified tool은 high severity로 보고, 사용자가 metadata rug-pull 가능성을 검토할 수 있게 Finding으로 반환한다.

## 3. CLI 실행 흐름

```text
사용자 명령
  ↓
cli/scan.py
  ↓
tools.json 입력 확인
  ↓
ToolMetadata 수집
  ↓
detector 실행
  ↓
Finding 리스트 생성
  ↓
baseline 옵션이 있으면 diff Finding 추가
  ↓
Markdown 또는 JSON 리포트 생성
  ↓
터미널 출력 또는 파일 저장
```

예시:

```bash
python -m cli.scan scan --input tools.json
python -m cli.scan scan --input tools.json --format json --output report.json
python -m cli.scan scan --input tools.json --save-baseline baseline.json
python -m cli.scan scan --input tools-new.json --baseline baseline.json
```

## 4. Report 생성 흐름

scanner와 baseline diff는 모두 Finding 목록을 만든다.

```text
Finding list
  ↓
report format 확인
  ↓
Markdown renderer 또는 JSON renderer
  ↓
문자열 report
  ↓
터미널 출력 또는 파일 저장
```

이 구조의 장점은 detector 결과와 baseline diff 결과를 같은 리포트로 출력할 수 있다는 점이다.

## 5. Baseline 저장 흐름

```text
ToolMetadata list
  ↓
normalize_tool()
  ↓
json.dumps(sort_keys=True, ensure_ascii=False)
  ↓
SHA-256 hash
  ↓
{server_name}:{tool_name} key로 baseline 구성
  ↓
baseline.json 저장
```

`sort_keys=True`를 사용하는 이유는 dict key 순서 때문에 hash가 달라지는 문제를 막기 위해서다. 같은 metadata는 항상 같은 hash를 가져야 한다.

## 6. Baseline Diff 흐름

```text
old baseline
current ToolMetadata list
  ↓
current baseline 생성
  ↓
tool key set 비교
  ↓
added / removed / modified 판단
  ↓
Finding 생성
  ↓
기존 scanner Finding에 추가
```

baseline diff는 detector처럼 악성 문자열을 직접 찾는 기능은 아니다. 대신 "이전에 승인한 metadata와 달라졌다"는 사실을 탐지한다. 이 방식은 metadata rug-pull 시나리오를 발견하는 데 중요하다.

semantic detector와 baseline diff는 같은 Finding 목록에 함께 담긴다. 따라서 description이 변경되었고 동시에 semantic 위험 finding이 발생하면, 리포트에서 "metadata가 바뀌었다"는 사실과 "변경된 내용이 의미적으로 위험하다"는 사실을 함께 볼 수 있다.

## 7. Semantic Detector 연동 흐름

member5는 임베딩 탐지 알고리즘을 직접 구현하지 않는다. 다른 팀원이 `detectors/semantic/embedding_similarity.py`에 `EmbeddingSimilarityDetector`를 구현하면, member5 코드는 CLI 옵션과 report 출력 경로를 제공한다.

```text
사용자 명령
  ↓
--enable-semantic 확인
  ↓
EmbeddingSimilarityDetector import 시도
  ↓
threshold/model_path로 detector 생성
  ↓
기본 detector 목록에 추가
  ↓
Finding list에 semantic finding 포함
  ↓
Markdown/JSON report 출력
```

사용 예시:

```bash
python -m cli.scan scan \
  --input ./tools.json \
  --enable-semantic \
  --semantic-threshold 0.82
```

```bash
python -m cli.scan scan \
  --input ./tools.json \
  --enable-semantic \
  --embedding-model-path ./models/all-MiniLM-L6-v2
```

semantic detector가 아직 구현되지 않은 상태에서 `--enable-semantic`을 켜면 사용자에게 다음과 같은 에러를 보여준다.

```text
Semantic similarity detector is not available. Please implement detectors/semantic/embedding_similarity.py first.
```

이 방식의 장점:

- 기본 scan은 기존처럼 빠르게 유지된다.
- semantic scan은 필요할 때만 켤 수 있다.
- metadata를 외부 API로 전송하지 않고 로컬 모델 사용을 전제로 한다.
- detector 구현 여부와 관계없이 CLI import 자체는 깨지지 않는다.

## 8. 이 구조의 장점

- CLI, scanner, report, baseline 역할이 분리되어 유지보수가 쉽다.
- detector가 추가되어도 CLI 사용법을 크게 바꾸지 않아도 된다.
- Finding 구조를 공통으로 사용해 detector 결과와 baseline diff 결과를 같은 방식으로 출력할 수 있다.
- Markdown은 사람이 읽기 좋고, JSON은 자동화에 적합하다.
- baseline 저장과 diff 기능으로 정상 상태 이후 metadata 변경을 추적할 수 있다.
- semantic detector를 옵션으로 연결해 키워드 탐지를 우회한 의미적 Tool Poisoning 문구도 표시할 수 있다.
- 발표와 시연에서 실제 보안 도구처럼 실행 흐름을 보여줄 수 있다.

## 9. 발표 시 설명 문장

팀원 5는 AuditGuard의 탐지 결과를 실제 사용자가 실행하고 확인할 수 있는 형태로 만드는 역할을 담당했습니다.

CLI는 `tools.json` 입력을 받아 scanner를 실행하고, 결과를 Markdown 또는 JSON 리포트로 변환합니다.

또한 baseline 저장과 diff 기능을 통해 이전에 정상으로 판단한 MCP tool metadata가 이후 변경되었는지 확인할 수 있습니다.

이 구조는 Tool Poisoning의 rug-pull 시나리오를 탐지하는 데 유용하며, detector가 추가되어도 동일한 Finding 구조를 통해 리포트로 출력할 수 있다는 장점이 있습니다.

Markdown report는 사람이 이해하기 쉬운 보안 보고서에 적합하고, JSON report는 CI나 dashboard 같은 자동화 환경에 연결하기 좋습니다.

새로 추가되는 로컬 임베딩 유사도 기반 탐지는 명확한 키워드가 없는 위험 문장도 의미적으로 탐지할 수 있도록 돕습니다. member5 영역에서는 이 detector를 직접 구현하지 않고, 사용자가 `--enable-semantic` 옵션으로 활성화하고 Markdown/JSON 리포트에서 결과를 확인할 수 있도록 CLI와 report 흐름에 연결했습니다.
