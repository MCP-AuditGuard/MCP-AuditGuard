# MCP-AuditGuard 사용자용 프로그램 빌드 가이드

## 1. 목적

이 문서는 MCP-AuditGuard를 개발용 Python 실행이 아니라, 사용자가 실행할 수 있는 로컬 웹 프로그램으로 빌드하는 방법을 설명한다.

최종 실행 방식은 다음과 같다.

### Windows

```text
AuditGuard.exe 더블클릭
→ 콘솔 창 실행
→ Semantic 모델 사전 검사
→ 로컬 FastAPI 서버 시작
→ /health 확인
→ 기본 브라우저 자동 실행
→ 콘솔에서 Ctrl+C 또는 콘솔 창 닫기로 종료
```

### macOS

```text
AuditGuard.command 더블클릭
→ Terminal 실행
→ macOS용 AuditGuard 실행
→ Semantic 모델 사전 검사
→ 로컬 FastAPI 서버 시작
→ /health 확인
→ 기본 브라우저 자동 실행
→ Terminal에서 Ctrl+C로 종료
```

현재 빌드 방식은 PyInstaller `onedir` 방식이다.

---

## 2. 운영체제별 빌드 원칙

PyInstaller는 일반적인 크로스 컴파일러가 아니다.

```text
Windows에서 빌드
→ Windows용 AuditGuard.exe 생성

macOS에서 빌드
→ macOS용 AuditGuard 실행파일 생성
```

따라서 Windows용 프로그램은 Windows에서, macOS용 프로그램은 macOS에서 각각 빌드해야 한다.

macOS의 경우 사용하는 Python과 Mac의 CPU 아키텍처에 따라 다음 결과가 만들어진다.

```text
Apple Silicon(M1, M2, M3, M4 등)
→ arm64

Intel Mac
→ x86_64
```

---

## 3. 관련 파일 구조

```text
installer/
├─ launcher_common.py
├─ windows_launcher.py
├─ macos_launcher.py
├─ auditguard_windows.spec
├─ auditguard_macos.spec
├─ build_windows.ps1
├─ build_macos.sh
└─ AuditGuard.command
```

각 파일의 역할은 다음과 같다.

### `launcher_common.py`

Windows와 macOS가 함께 사용하는 실행 로직이다.

```text
Semantic Runtime Preflight
사용 가능한 포트 검색
FastAPI 앱 로드
Uvicorn 서버 시작
/health 준비 확인
기본 브라우저 실행
Ctrl+C 종료 처리
오류 출력
```

### `windows_launcher.py`

Windows 전용 진입점이다.

```text
Windows 콘솔 제목 설정
launcher_common 실행
```

### `macos_launcher.py`

macOS 전용 진입점이다.

```text
Terminal 제목 설정
launcher_common 실행
```

### `auditguard_windows.spec`

Windows용 PyInstaller 빌드 설정이다.

```text
windows_launcher.py를 시작점으로 사용
AuditGuard.exe 생성
콘솔 표시
web/templates 포함
web/static 포함
rules 포함
Semantic 모델 포함
sentence-transformers 관련 패키지 포함
onedir 결과 생성
```

### `auditguard_macos.spec`

macOS용 PyInstaller 빌드 설정이다.

```text
macos_launcher.py를 시작점으로 사용
macOS용 AuditGuard 실행파일 생성
콘솔 표시
web/templates 포함
web/static 포함
rules 포함
Semantic 모델 포함
sentence-transformers 관련 패키지 포함
AuditGuard.command를 최종 폴더에 복사
onedir 결과 생성
```

### `build_windows.ps1`

Windows 빌드 전체 과정을 자동 실행한다.

### `build_macos.sh`

macOS 빌드 전체 과정을 자동 실행한다.

### `AuditGuard.command`

macOS Finder에서 더블클릭했을 때 Terminal을 열고, 같은 폴더의 AuditGuard 실행파일을 실행한다.

---

## 4. 사전 요구사항

### 공통

- Git
- Python 3.11 이상
- 인터넷 연결
  - 최초 의존성 설치
  - 최초 Semantic 모델 다운로드

프로젝트의 현재 개발 환경과 동일하게 Python 3.14를 사용할 수 있지만, 빌드 스크립트는 Python 3.11 이상을 허용한다.

### Windows

PowerShell에서 실행한다.

### macOS

Terminal에서 실행한다.

macOS에서는 필요한 경우 Xcode Command Line Tools가 먼저 설치되어 있어야 한다.

---

## 5. 자동 빌드 방법

자동 빌드는 다음 과정을 한 번에 수행한다.

```text
1. 운영체제 확인
2. Python 3.11 이상 확인
3. .venv-build가 없으면 생성
4. pip, setuptools, wheel 업데이트
5. .[dev,semantic,build] 설치
6. Semantic 모델이 없으면 다운로드
7. Semantic Runtime Preflight 실행
8. 관련 테스트 실행
9. 기존 build, dist 삭제
10. PyInstaller 빌드
11. 최종 실행파일과 리소스 확인
```

가상환경을 직접 활성화할 필요가 없다.

빌드 스크립트가 다음 Python을 직접 사용한다.

```text
Windows
.venv-build\Scripts\python.exe

macOS
.venv-build/bin/python
```

---

## 6. Windows 자동 빌드

프로젝트 루트에서 실행한다.

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1
```

최종 결과:

```text
dist/
└─ AuditGuard/
   ├─ AuditGuard.exe
   └─ _internal/
```

실행:

```powershell
.\dist\AuditGuard\AuditGuard.exe
```

### 빌드 가상환경을 처음부터 다시 만들기

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1 `
    -RecreateVenv
```

### 전체 테스트 실행

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1 `
    -FullTests
```

### 테스트 생략

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1 `
    -SkipTests
```

### 특정 Python 사용

기본 Python 검색이 실패하거나 특정 Python을 사용하려면 환경변수에 실행파일 경로를 지정한다.

```powershell
$env:AUDITGUARD_PYTHON = "C:\Path\To\python.exe"

powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1
```

---

## 7. macOS 자동 빌드

최초 한 번 실행 권한을 설정한다.

```bash
chmod +x installer/build_macos.sh
chmod +x installer/AuditGuard.command
```

빌드:

```bash
./installer/build_macos.sh
```

최종 결과:

```text
dist/
└─ AuditGuard/
   ├─ AuditGuard
   ├─ AuditGuard.command
   └─ _internal/
```

Finder에서는 다음 파일을 더블클릭한다.

```text
dist/AuditGuard/AuditGuard.command
```

Terminal에서 직접 실행할 수도 있다.

```bash
cd dist/AuditGuard
./AuditGuard.command
```

### 빌드 가상환경을 처음부터 다시 만들기

```bash
AUDITGUARD_RECREATE_VENV=1 \
./installer/build_macos.sh
```

### 전체 테스트 실행

```bash
AUDITGUARD_FULL_TESTS=1 \
./installer/build_macos.sh
```

### 테스트 생략

```bash
AUDITGUARD_SKIP_TESTS=1 \
./installer/build_macos.sh
```

### 특정 Python 사용

```bash
AUDITGUARD_PYTHON=/path/to/python3 \
./installer/build_macos.sh
```

---

## 8. Semantic 모델 준비

사용 모델:

```text
BAAI/bge-small-en-v1.5
```

저장 위치:

```text
models/
└─ embedding/
   └─ bge-small-en-v1.5/
```

빌드 스크립트는 다음 필수 파일을 확인한다.

```text
config.json

그리고 아래 둘 중 하나
model.safetensors
pytorch_model.bin
```

모델이 없으면 Hugging Face CLI를 통해 자동으로 다운로드한다.

### 모델을 강제로 다시 다운로드

Windows:

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1 `
    -ForceModelDownload
```

macOS:

```bash
AUDITGUARD_FORCE_MODEL_DOWNLOAD=1 \
./installer/build_macos.sh
```

### 모델 revision 고정

팀원 모두 동일한 모델 파일을 사용하려면 Hugging Face 모델 저장소의 commit SHA를 고정하는 것이 좋다.

Windows:

```powershell
$env:AUDITGUARD_MODEL_REVISION = "<MODEL_COMMIT_SHA>"

powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1
```

macOS:

```bash
AUDITGUARD_MODEL_REVISION="<MODEL_COMMIT_SHA>" \
./installer/build_macos.sh
```

revision을 지정하지 않으면 모델 저장소의 기본 revision을 사용한다.

---

## 9. 수동 Windows 빌드

자동 빌드 스크립트를 사용하지 않을 경우 다음 순서로 실행한다.

### 9.1 빌드 가상환경 생성

```powershell
py -3.14 -m venv .venv-build
```

### 9.2 pip 업데이트

```powershell
.\.venv-build\Scripts\python.exe -m pip install `
    --upgrade `
    pip `
    setuptools `
    wheel
```

### 9.3 의존성 설치

```powershell
.\.venv-build\Scripts\python.exe -m pip install `
    ".[dev,semantic,build]"
```

### 9.4 모델 다운로드

```powershell
.\.venv-build\Scripts\hf.exe download `
    BAAI/bge-small-en-v1.5 `
    --local-dir `
    .\models\embedding\bge-small-en-v1.5
```

### 9.5 Launcher 실행 확인

```powershell
.\.venv-build\Scripts\python.exe `
    .\installer\windows_launcher.py
```

확인 항목:

```text
Semantic 실행 환경 검사 성공
Dimension 384
로컬 모델 경로 출력
127.0.0.1:8000 또는 다음 사용 가능한 포트 사용
/health 200
브라우저 자동 실행
Ctrl+C 정상 종료
```

### 9.6 기존 결과 삭제

```powershell
Remove-Item .\build `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item .\dist `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue
```

### 9.7 PyInstaller 빌드

```powershell
.\.venv-build\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    .\installer\auditguard_windows.spec
```

### 9.8 최종 실행

```powershell
.\dist\AuditGuard\AuditGuard.exe
```

---

## 10. 수동 macOS 빌드

### 10.1 빌드 가상환경 생성

```bash
python3 -m venv .venv-build
```

### 10.2 pip 업데이트

```bash
.venv-build/bin/python -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel
```

### 10.3 의존성 설치

```bash
.venv-build/bin/python -m pip install \
    '.[dev,semantic,build]'
```

### 10.4 모델 다운로드

```bash
.venv-build/bin/hf download \
    BAAI/bge-small-en-v1.5 \
    --local-dir \
    models/embedding/bge-small-en-v1.5
```

### 10.5 Launcher 실행 확인

```bash
.venv-build/bin/python \
    installer/macos_launcher.py
```

### 10.6 기존 결과 삭제

```bash
rm -rf build dist
```

### 10.7 PyInstaller 빌드

```bash
.venv-build/bin/python -m PyInstaller \
    --noconfirm \
    --clean \
    installer/auditguard_macos.spec
```

### 10.8 실행 권한 확인

```bash
chmod +x dist/AuditGuard/AuditGuard
chmod +x dist/AuditGuard/AuditGuard.command
```

### 10.9 최종 실행

```bash
cd dist/AuditGuard
./AuditGuard.command
```

---

## 11. `build`와 `dist` 폴더 차이

PyInstaller를 실행하면 일반적으로 프로젝트 루트에 다음 두 폴더가 생성된다.

```text
build/
dist/
```

### `build/`

PyInstaller가 빌드 중 사용하는 중간 작업 폴더다.

예:

```text
build/
└─ AuditGuard/
   ├─ Analysis-00.toc
   ├─ PYZ-00.pyz
   ├─ PKG-00.toc
   ├─ EXE-00.toc
   ├─ warn-AuditGuard.txt
   └─ xref-AuditGuard.html
```

용도:

```text
모듈 분석 결과
수집한 바이너리 정보
중간 Python 아카이브
빌드 경고
임시 산출물
```

사용자에게 전달하지 않는다.

빌드 완료 후 삭제해도 된다.

### `dist/`

실제 실행하고 검증하는 최종 결과 폴더다.

Windows:

```text
dist/
└─ AuditGuard/
   ├─ AuditGuard.exe
   └─ _internal/
```

macOS:

```text
dist/
└─ AuditGuard/
   ├─ AuditGuard
   ├─ AuditGuard.command
   └─ _internal/
```

`onedir` 방식이므로 실행파일만 따로 이동하면 안 된다.

다음 폴더 전체가 함께 있어야 한다.

```text
dist/AuditGuard/
```

---

## 12. `.gitattributes`

Windows와 macOS가 함께 작업하므로 줄바꿈 형식을 고정하는 것이 좋다.

저장소 루트의 `.gitattributes`:

```gitattributes
* text=auto

*.py text eol=lf
*.toml text eol=lf
*.spec text eol=lf
*.md text eol=lf
*.yaml text eol=lf
*.yml text eol=lf

*.sh text eol=lf
*.command text eol=lf

*.ps1 text eol=crlf
*.bat text eol=crlf
*.cmd text eol=crlf
```

`.command`와 `.sh`가 Windows CRLF로 저장되면 macOS에서 `bad interpreter` 오류가 발생할 수 있다.

---

## 13. macOS 실행 권한을 Git에 기록

macOS 파일은 실행 권한이 필요하다.

```bash
chmod +x installer/build_macos.sh
chmod +x installer/AuditGuard.command
```

Git index에도 실행 권한을 기록한다.

```bash
git update-index \
    --chmod=+x \
    installer/build_macos.sh

git update-index \
    --chmod=+x \
    installer/AuditGuard.command
```

확인:

```bash
git ls-files --stage \
    installer/build_macos.sh \
    installer/AuditGuard.command
```

정상적인 실행파일 모드는 다음과 같다.

```text
100755
```

`100644`이면 실행 권한이 기록되지 않은 것이다.

Windows PowerShell에서도 다음 명령으로 Git 실행 권한을 기록할 수 있다.

```powershell
git update-index `
    --chmod=+x `
    installer/build_macos.sh

git update-index `
    --chmod=+x `
    installer/AuditGuard.command
```

---

## 14. 최종 빌드 검증

### 공통 확인

```text
Semantic Runtime Preflight 성공
Provider: SentenceTransformerEmbeddingProvider
Dimension: 384
모델 경로가 dist/AuditGuard/_internal 아래를 가리킴
/health 200
브라우저 자동 실행
웹 CSS와 JavaScript 정상 로드
MCP 서버 목록 API 정상
실제 검사 실행 정상
Ctrl+C 정상 종료
```

### Windows 필수 파일

```powershell
Test-Path .\dist\AuditGuard\AuditGuard.exe

Test-Path `
    .\dist\AuditGuard\_internal\web\templates\index.html

Test-Path `
    .\dist\AuditGuard\_internal\web\static\app.js

Test-Path `
    .\dist\AuditGuard\_internal\rules

Test-Path `
    .\dist\AuditGuard\_internal\models\embedding\bge-small-en-v1.5\config.json
```

모두 `True`여야 한다.

### macOS 필수 파일

```bash
test -x dist/AuditGuard/AuditGuard
echo $?

test -x dist/AuditGuard/AuditGuard.command
echo $?
```

모두 `0`이어야 한다.

아키텍처 확인:

```bash
file dist/AuditGuard/AuditGuard
```

Apple Silicon:

```text
Mach-O 64-bit executable arm64
```

Intel Mac:

```text
Mach-O 64-bit executable x86_64
```

---


##  팀원 재현 절차

다른 팀원이 빌드를 재현할 때는 기존 개발 PC의 파일을 복사하지 말고 다음 조건에서 확인한다.

```text
새 Git clone
.venv-build 없음
models/embedding 모델 없음
build 없음
dist 없음
```

Windows 팀원:

```powershell
powershell -ExecutionPolicy Bypass `
    -File .\installer\build_windows.ps1
```

macOS 팀원:

```bash
chmod +x installer/build_macos.sh
chmod +x installer/AuditGuard.command

./installer/build_macos.sh
```

팀원의 새 clone에서 빌드가 성공해야 팀 공용 빌드 구조가 완성된 것이다.


