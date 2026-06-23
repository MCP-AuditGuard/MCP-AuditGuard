# MCP-AuditGuard CLI 명령어 가이드

## 1. 문서 목적

이 문서는 MCP-AuditGuard에서 현재 사용할 수 있는 CLI 명령을 한곳에 정리합니다.

CLI는 다음 두 가지 방식으로 실행할 수 있습니다.

1. Python 모듈 직접 실행

```powershell
python -m cli.main ...
```

2. 설치된 콘솔 명령 실행

```powershell
auditguard ...
```

두 방식은 진입점만 다르고, 뒤에 붙는 명령 구조와 옵션은 같습니다.

---

## 2. 권장 문서 위치

여러 멤버가 `docs` 폴더를 함께 사용한다면, 멤버 이름 기준보다 기능 기준으로 분리하는 것이 좋습니다.

권장 구조:

```text
docs/
├─ cli/
│  └─ cli-commands.md
├─ architecture/
├─ development/
├─ security/
└─ testing/
```

이 파일의 권장 저장 위치:

```text
docs/cli/cli-commands.md
```

멤버별 작업 기록이 별도로 필요할 때만 다음처럼 분리합니다.

```text
docs/
├─ cli/
│  └─ cli-commands.md
└─ contributions/
   └─ member1/
      └─ work-log.md
```

실제 기능 설명과 사용법은 `docs/cli/`에 두고, 개인 작업 기록만 `docs/contributions/member1/`에 두는 방식이 좋습니다.

---

## 3. 전체 CLI 구조

```text
auditguard
├─ help
├─ scan
├─ web
└─ mcp
   ├─ list
   └─ scan
```

Python 모듈 실행 방식으로 보면 다음과 같습니다.

```text
python -m cli.main
├─ help
├─ scan
├─ web
└─ mcp
   ├─ list
   └─ scan
```

---

# 4. 최상위 명령

## 4.1 Python 모듈 직접 실행

### 인자 없이 실행

```powershell
python -m cli.main
```

`no_args_is_help=True` 설정으로 최상위 도움말을 표시합니다.

### Typer 기본 도움말

```powershell
python -m cli.main --help
```

### 프로젝트에서 작성한 사용 가이드

```powershell
python -m cli.main help
```

---

## 4.2 `auditguard` 콘솔 명령 실행

### 인자 없이 실행

```powershell
auditguard
```

### Typer 기본 도움말

```powershell
auditguard --help
```

### 프로젝트에서 작성한 사용 가이드

```powershell
auditguard help
```

---

# 5. `scan` 명령

`scan`은 `tools.json` 같은 MCP 도구 메타데이터 파일을 입력받아 정적 검사를 수행합니다.

## 5.1 명령 도움말

### Python 모듈 실행

```powershell
python -m cli.main scan --help
```

### `auditguard` 실행

```powershell
auditguard scan --help
```

---

## 5.2 기본 검사

### Python 모듈 실행

```powershell
python -m cli.main scan --input tools.json
```

축약 옵션:

```powershell
python -m cli.main scan -i tools.json
```

### `auditguard` 실행

```powershell
auditguard scan --input tools.json
```

축약 옵션:

```powershell
auditguard scan -i tools.json
```

---

## 5.3 Markdown 형식 출력

### Python 모듈 실행

```powershell
python -m cli.main scan --input tools.json --format markdown
```

```powershell
python -m cli.main scan -i tools.json -f markdown
```

### `auditguard` 실행

```powershell
auditguard scan --input tools.json --format markdown
```

```powershell
auditguard scan -i tools.json -f markdown
```

---

## 5.4 JSON 형식 출력

### Python 모듈 실행

```powershell
python -m cli.main scan --input tools.json --format json
```

```powershell
python -m cli.main scan -i tools.json -f json
```

### `auditguard` 실행

```powershell
auditguard scan --input tools.json --format json
```

```powershell
auditguard scan -i tools.json -f json
```

---

## 5.5 결과 파일 저장

### Markdown 보고서 저장

Python 모듈 실행:

```powershell
python -m cli.main scan --input tools.json --format markdown --output report.md
```

축약형:

```powershell
python -m cli.main scan -i tools.json -f markdown -o report.md
```

`auditguard` 실행:

```powershell
auditguard scan --input tools.json --format markdown --output report.md
```

축약형:

```powershell
auditguard scan -i tools.json -f markdown -o report.md
```

### JSON 보고서 저장

Python 모듈 실행:

```powershell
python -m cli.main scan --input tools.json --format json --output report.json
```

`auditguard` 실행:

```powershell
auditguard scan --input tools.json --format json --output report.json
```

---

## 5.6 현재 메타데이터를 baseline으로 저장

### Python 모듈 실행

```powershell
python -m cli.main scan --input tools.json --save-baseline baseline.json
```

### `auditguard` 실행

```powershell
auditguard scan --input tools.json --save-baseline baseline.json
```

---

## 5.7 이전 baseline과 비교

### Python 모듈 실행

```powershell
python -m cli.main scan --input tools-new.json --baseline baseline.json
```

### `auditguard` 실행

```powershell
auditguard scan --input tools-new.json --baseline baseline.json
```

---

## 5.8 `scan` 옵션 정리

| 옵션 | 축약형 | 설명 |
|---|---:|---|
| `--input` | `-i` | 검사할 `tools.json` 경로 |
| `--format` | `-f` | 출력 형식. `markdown` 또는 `json` |
| `--output` | `-o` | 결과 보고서를 저장할 파일 경로 |
| `--save-baseline` | 없음 | 현재 메타데이터 baseline을 저장할 경로 |
| `--baseline` | 없음 | 비교할 이전 baseline JSON 경로 |
| `--help` | 없음 | `scan` 명령 도움말 표시 |

---

# 6. `web` 명령

`web`은 MCP-AuditGuard 로컬 웹 인터페이스를 실행합니다.

## 6.1 명령 도움말

### Python 모듈 실행

```powershell
python -m cli.main web --help
```

### `auditguard` 실행

```powershell
auditguard web --help
```

---

## 6.2 기본 실행

### Python 모듈 실행

```powershell
python -m cli.main web
```

### `auditguard` 실행

```powershell
auditguard web
```

기본값:

```text
host: 127.0.0.1
port: 8000
```

기본 접속 주소:

```text
http://127.0.0.1:8000
```

---

## 6.3 개발용 자동 재시작

### Python 모듈 실행

```powershell
python -m cli.main web --reload
```

### `auditguard` 실행

```powershell
auditguard web --reload
```

---

## 6.4 포트 변경

### Python 모듈 실행

```powershell
python -m cli.main web --port 8080
```

### `auditguard` 실행

```powershell
auditguard web --port 8080
```

---

## 6.5 호스트 변경

### Python 모듈 실행

```powershell
python -m cli.main web --host 127.0.0.1
```

### `auditguard` 실행

```powershell
auditguard web --host 127.0.0.1
```

---

## 6.6 호스트, 포트, reload 함께 사용

### Python 모듈 실행

```powershell
python -m cli.main web --host 127.0.0.1 --port 8080 --reload
```

### `auditguard` 실행

```powershell
auditguard web --host 127.0.0.1 --port 8080 --reload
```

---

## 6.7 `web` 옵션 정리

| 옵션 | 설명 |
|---|---|
| `--host` | 웹 서버가 바인딩할 호스트. 기본값 `127.0.0.1` |
| `--port` | 웹 서버 포트. 기본값 `8000` |
| `--reload` | 소스 변경 시 서버 자동 재시작 |
| `--help` | `web` 명령 도움말 표시 |

---

# 7. `mcp` 명령 그룹

`mcp`는 등록된 MCP 서버를 발견하고, 선택한 서버의 도구 메타데이터를 동적으로 수집하여 검사하는 명령 그룹입니다.

현재 하위 명령:

```text
mcp
├─ list
└─ scan
```

---

## 7.1 `mcp` 그룹 도움말

### Python 모듈 실행

```powershell
python -m cli.main mcp
```

```powershell
python -m cli.main mcp --help
```

### `auditguard` 실행

```powershell
auditguard mcp
```

```powershell
auditguard mcp --help
```

---

# 8. `mcp list` 명령

등록된 MCP 서버를 발견하여 목록으로 출력합니다.

출력되는 주요 정보:

```text
selection_id
product
scope
name
transport
enabled_state
support_state
support_reason_code
command_basename
http_origin
argument_count
```

## 8.1 명령 도움말

### Python 모듈 실행

```powershell
python -m cli.main mcp list --help
```

### `auditguard` 실행

```powershell
auditguard mcp list --help
```

---

## 8.2 기본 서버 목록 조회

### Python 모듈 실행

```powershell
python -m cli.main mcp list
```

### `auditguard` 실행

```powershell
auditguard mcp list
```

---

## 8.3 프로젝트 범위 MCP 설정 포함

프로젝트 설정을 신뢰하여 함께 읽을 때 사용합니다.

### Python 모듈 실행

```powershell
python -m cli.main mcp list --trust-project-config
```

### `auditguard` 실행

```powershell
auditguard mcp list --trust-project-config
```

---

## 8.4 프로젝트 루트 지정

현재 폴더를 프로젝트 루트로 지정:

### Python 모듈 실행

```powershell
python -m cli.main mcp list --project-root .
```

### `auditguard` 실행

```powershell
auditguard mcp list --project-root .
```

절대 경로 지정:

### Python 모듈 실행

```powershell
python -m cli.main mcp list --project-root C:\Dinho\Work\MCP_GitHub
```

### `auditguard` 실행

```powershell
auditguard mcp list --project-root C:\Dinho\Work\MCP_GitHub
```

---

## 8.5 프로젝트 설정 신뢰와 프로젝트 루트 동시 지정

### Python 모듈 실행

```powershell
python -m cli.main mcp list --trust-project-config --project-root C:\Dinho\Work\MCP_GitHub
```

### `auditguard` 실행

```powershell
auditguard mcp list --trust-project-config --project-root C:\Dinho\Work\MCP_GitHub
```

---

## 8.6 `mcp list` 옵션 정리

| 옵션 | 설명 |
|---|---|
| `--trust-project-config` | 신뢰한 프로젝트 범위 MCP 설정을 검색에 포함 |
| `--project-root` | MCP 설정 검색에 사용할 프로젝트 루트 디렉터리 |
| `--help` | `mcp list` 도움말 표시 |

`--project-root`에는 읽을 수 있는 디렉터리 경로를 지정해야 합니다.

---

# 9. `mcp scan` 명령

`mcp list`로 발견한 서버 중 하나를 `selection_id`로 선택하여 동적 메타데이터 검사를 수행합니다.

## 9.1 실행 순서

먼저 서버 목록을 확인합니다.

### Python 모듈 실행

```powershell
python -m cli.main mcp list
```

### `auditguard` 실행

```powershell
auditguard mcp list
```

목록에서 `selection_id`를 확인한 후 검사합니다.

---

## 9.2 명령 도움말

### Python 모듈 실행

```powershell
python -m cli.main mcp scan --help
```

### `auditguard` 실행

```powershell
auditguard mcp scan --help
```

---

## 9.3 기본 MCP 서버 검사

### Python 모듈 실행

```powershell
python -m cli.main mcp scan --server-id "선택ID"
```

### `auditguard` 실행

```powershell
auditguard mcp scan --server-id "선택ID"
```

`--server-id`는 필수 옵션입니다.

`selection_id`에 특수문자나 공백이 포함될 수 있으므로 따옴표로 감싸는 것이 안전합니다.

---

## 9.4 프로젝트 범위 설정을 포함하여 검사

목록 조회에서 `--trust-project-config`를 사용했다면 검사할 때도 같은 옵션을 사용해야 합니다.

### Python 모듈 실행

```powershell
python -m cli.main mcp scan --server-id "선택ID" --trust-project-config
```

### `auditguard` 실행

```powershell
auditguard mcp scan --server-id "선택ID" --trust-project-config
```

---

## 9.5 프로젝트 루트를 지정하여 검사

### Python 모듈 실행

```powershell
python -m cli.main mcp scan --server-id "선택ID" --project-root C:\Dinho\Work\MCP_GitHub
```

### `auditguard` 실행

```powershell
auditguard mcp scan --server-id "선택ID" --project-root C:\Dinho\Work\MCP_GitHub
```

---

## 9.6 모든 옵션 함께 사용

### Python 모듈 실행

```powershell
python -m cli.main mcp scan --server-id "선택ID" --trust-project-config --project-root C:\Dinho\Work\MCP_GitHub
```

### `auditguard` 실행

```powershell
auditguard mcp scan --server-id "선택ID" --trust-project-config --project-root C:\Dinho\Work\MCP_GitHub
```

---

## 9.7 `mcp scan` 옵션 정리

| 옵션 | 필수 여부 | 설명 |
|---|---:|---|
| `--server-id` | 필수 | `mcp list`에서 확인한 MCP 서버의 선택 ID |
| `--trust-project-config` | 선택 | 신뢰한 프로젝트 범위 MCP 설정을 검색에 포함 |
| `--project-root` | 선택 | MCP 설정 검색에 사용할 프로젝트 루트 |
| `--help` | 선택 | `mcp scan` 도움말 표시 |

---

# 10. 자주 사용하는 명령 요약

## 10.1 Python 모듈 실행 방식

```powershell
# 전체 도움말
python -m cli.main --help

# tools.json 정적 검사
python -m cli.main scan --input tools.json

# 로컬 웹 실행
python -m cli.main web

# 등록된 MCP 서버 목록
python -m cli.main mcp list

# 특정 MCP 서버 동적 검사
python -m cli.main mcp scan --server-id "선택ID"
```

## 10.2 `auditguard` 실행 방식

```powershell
# 전체 도움말
auditguard --help

# tools.json 정적 검사
auditguard scan --input tools.json

# 로컬 웹 실행
auditguard web

# 등록된 MCP 서버 목록
auditguard mcp list

# 특정 MCP 서버 동적 검사
auditguard mcp scan --server-id "선택ID"
```

---

# 11. 두 실행 방식 대응표

| 목적 | Python 모듈 실행 | 설치된 명령 실행 |
|---|---|---|
| 전체 도움말 | `python -m cli.main --help` | `auditguard --help` |
| 사용 가이드 | `python -m cli.main help` | `auditguard help` |
| 정적 검사 | `python -m cli.main scan ...` | `auditguard scan ...` |
| 웹 실행 | `python -m cli.main web ...` | `auditguard web ...` |
| MCP 목록 | `python -m cli.main mcp list ...` | `auditguard mcp list ...` |
| MCP 검사 | `python -m cli.main mcp scan ...` | `auditguard mcp scan ...` |

---

# 12. 실행 방식 선택 기준

## Python 모듈 직접 실행

```powershell
python -m cli.main ...
```

다음 상황에 적합합니다.

- 프로젝트 소스에서 직접 실행할 때
- 콘솔 명령 등록 여부와 무관하게 실행할 때
- 개발 중 진입점을 명확하게 확인할 때

## `auditguard` 명령 실행

```powershell
auditguard ...
```

다음 상황에 적합합니다.

- 프로젝트가 패키지로 설치되어 있을 때
- 사용자에게 간단한 실행 방법을 제공할 때
- 배포 및 실무 사용 형태로 실행할 때

`auditguard` 명령을 찾을 수 없다는 오류가 발생하면 프로젝트 가상환경이 활성화되어 있는지와 패키지 설치 상태를 확인해야 합니다.

일반적으로 개발 환경에서는 다음과 같은 editable 설치를 사용합니다.

```powershell
pip install -e .
```

개발 의존성 그룹까지 설치하는 프로젝트라면 프로젝트 설정에 맞게 다음 형식을 사용할 수 있습니다.

```powershell
pip install -e ".[dev]"
```

---

# 13. 현재 명령 구조의 역할 구분

```text
scan
```

파일로 전달받은 MCP 도구 메타데이터를 정적으로 검사합니다.

```text
web
```

MCP-AuditGuard 로컬 웹 인터페이스를 실행합니다.

```text
mcp list
```

Codex, Claude 등에서 설정된 MCP 서버를 발견하고 안전하게 요약합니다.

```text
mcp scan
```

발견된 MCP 서버 하나를 선택하여 연결하고, 도구 목록과 메타데이터를 수집한 뒤 검사합니다.

---

# 14. 문서 유지보수 규칙

CLI 명령이 추가되거나 옵션이 변경되면 다음 파일과 이 문서를 함께 갱신하는 것이 좋습니다.

```text
cli/main.py
cli/scan.py
cli/web.py
cli/mcp.py
docs/cli/cli-commands.md
```

권장 원칙:

1. 실제 코드에 등록된 명령을 기준으로 문서를 작성합니다.
2. `python -m cli.main`과 `auditguard` 두 실행 방식을 함께 기록합니다.
3. 옵션의 필수 여부와 기본값을 표시합니다.
4. 명령이 추가되면 전체 명령 트리도 갱신합니다.
5. 멤버 개인 작업 기록과 사용자용 명령 문서를 분리합니다.
