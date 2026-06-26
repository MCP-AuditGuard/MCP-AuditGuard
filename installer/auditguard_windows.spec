# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
)


# ---------------------------------------------------------------------------
# 프로젝트 경로
# ---------------------------------------------------------------------------

# SPECPATH:
#   현재 auditguard.spec 파일이 들어 있는 installer 디렉터리
#
# 예:
#   C:\Dinho\Work\MCP_GitHub\installer
SPEC_DIRECTORY = Path(SPECPATH).resolve()

# 프로젝트 루트:
#   C:\Dinho\Work\MCP_GitHub
PROJECT_ROOT = SPEC_DIRECTORY.parent

LAUNCHER_PATH = (
    PROJECT_ROOT
    / "installer"
    / "windows_launcher.py"
)

WEB_TEMPLATES_DIRECTORY = (
    PROJECT_ROOT
    / "web"
    / "templates"
)

WEB_STATIC_DIRECTORY = (
    PROJECT_ROOT
    / "web"
    / "static"
)

RULES_DIRECTORY = (
    PROJECT_ROOT
    / "rules"
)

SEMANTIC_MODEL_DIRECTORY = (
    PROJECT_ROOT
    / "models"
    / "embedding"
    / "bge-small-en-v1.5"
)


# ---------------------------------------------------------------------------
# 빌드 전 필수 경로 검증
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    LAUNCHER_PATH,
)

REQUIRED_DIRECTORIES = (
    WEB_TEMPLATES_DIRECTORY,
    WEB_STATIC_DIRECTORY,
    RULES_DIRECTORY,
    SEMANTIC_MODEL_DIRECTORY,
)


for required_file in REQUIRED_FILES:
    if not required_file.is_file():
        raise FileNotFoundError(
            "PyInstaller 빌드에 필요한 파일이 없습니다: "
            f"{required_file}"
        )


for required_directory in REQUIRED_DIRECTORIES:
    if not required_directory.is_dir():
        raise FileNotFoundError(
            "PyInstaller 빌드에 필요한 디렉터리가 없습니다: "
            f"{required_directory}"
        )


# ---------------------------------------------------------------------------
# 디렉터리 파일 수집
# ---------------------------------------------------------------------------

def collect_directory_files(
    source_directory: Path,
    destination_directory: str,
    *,
    excluded_directory_names: frozenset[str] = frozenset(),
    excluded_file_names: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """
    source_directory 아래의 파일을 재귀적으로 수집하면서
    PyInstaller datas 형식으로 변환한다.

    반환 형식:
        [
            (
                "실제 원본 파일 경로",
                "배포 폴더 안의 목적 디렉터리",
            ),
        ]

    Semantic 모델 안의 Hugging Face 다운로드 캐시처럼
    사용자 프로그램 실행에 불필요한 디렉터리는 제외할 수 있다.
    """

    collected_files: list[tuple[str, str]] = []

    for source_file in source_directory.rglob("*"):
        if not source_file.is_file():
            continue

        relative_path = source_file.relative_to(
            source_directory
        )

        if any(
            directory_name
            in excluded_directory_names
            for directory_name in relative_path.parts[:-1]
        ):
            continue

        if source_file.name in excluded_file_names:
            continue

        destination_path = (
            Path(destination_directory)
            / relative_path.parent
        )

        collected_files.append(
            (
                str(source_file),
                str(destination_path),
            )
        )

    return collected_files


# ---------------------------------------------------------------------------
# 애플리케이션 데이터 파일
# ---------------------------------------------------------------------------

datas: list[tuple[str, str]] = []


# Jinja2 HTML 템플릿
datas += collect_directory_files(
    WEB_TEMPLATES_DIRECTORY,
    "web/templates",
)


# CSS, JavaScript 등 정적 파일
datas += collect_directory_files(
    WEB_STATIC_DIRECTORY,
    "web/static",
)


# Tool Poisoning 및 Semantic YAML 규칙
datas += collect_directory_files(
    RULES_DIRECTORY,
    "rules",
    excluded_directory_names=frozenset(
        {
            "__pycache__",
        }
    ),
)


# bge-small-en-v1.5 Semantic 모델
#
# .cache는 Hugging Face가 다운로드하면서 생성한 메타데이터이므로
# 실제 오프라인 모델 실행에는 필요하지 않아 배포에서 제외한다.
datas += collect_directory_files(
    SEMANTIC_MODEL_DIRECTORY,
    "models/embedding/bge-small-en-v1.5",
    excluded_directory_names=frozenset(
        {
            ".cache",
            "__pycache__",
        }
    ),
)


# ---------------------------------------------------------------------------
# Python 패키지 데이터, 바이너리, 숨은 import
# ---------------------------------------------------------------------------

binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []


def collect_package(
    package_name: str,
) -> None:
    """
    동적 import와 패키지 데이터가 많은 패키지를 PyInstaller에
    명시적으로 포함한다.

    collect_all() 반환:
        package_datas
        package_binaries
        package_hiddenimports
    """

    package_datas, package_binaries, package_hiddenimports = (
        collect_all(
            package_name,
            on_error="warn once",
        )
    )

    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)


# Sentence Transformers는 모델 구성 파일의 문자열을 기준으로
# 내부 모델 클래스를 동적으로 불러올 수 있으므로 명시적으로 수집한다.
collect_package("sentence_transformers")


# Transformers도 lazy import와 동적 모듈 로딩이 많으므로
# 첫 사용자용 빌드에서는 안전성을 우선하여 포함한다.
collect_package("transformers")


# Rust/C 확장 바이너리와 패키지 데이터가 포함될 수 있다.
collect_package("tokenizers")
collect_package("safetensors")


# Uvicorn은 HTTP, WebSocket, lifespan 구현체를 문자열 기반으로
# 선택할 수 있으므로 하위 모듈을 포함한다.
hiddenimports += collect_submodules(
    "uvicorn",
    on_error="warn once",
)


# MCP Python SDK 내부에서 transport나 client 모듈을 동적으로
# 가져오는 경우를 대비한다.
hiddenimports += collect_submodules(
    "mcp",
    on_error="warn once",
)


# sentence-transformers와 의존 패키지 일부는 importlib.metadata로
# 설치 패키지 정보를 조회할 수 있으므로 dist-info를 포함한다.
#
# recursive=True:
#   sentence-transformers의 의존성 metadata도 함께 수집
datas += copy_metadata(
    "sentence-transformers",
    recursive=True,
)


# ---------------------------------------------------------------------------
# 중복 항목 정리
# ---------------------------------------------------------------------------

def deduplicate_tuples(
    values: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    datas와 binaries의 동일한 항목을 제거하면서 기존 순서를 유지한다.
    """

    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def deduplicate_strings(
    values: list[str],
) -> list[str]:
    """
    hiddenimports의 중복을 제거하면서 기존 순서를 유지한다.
    """

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


datas = deduplicate_tuples(datas)
binaries = deduplicate_tuples(binaries)
hiddenimports = deduplicate_strings(hiddenimports)


# ---------------------------------------------------------------------------
# PyInstaller Analysis
# ---------------------------------------------------------------------------

analysis = Analysis(
    [
        str(LAUNCHER_PATH),
    ],
    pathex=[
        str(PROJECT_ROOT),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 사용자용 실행파일에는 테스트 도구가 필요하지 않다.
        "pytest",
        "_pytest",

        # 개발 도구
        "IPython",
        "jupyter",
        "notebook",

        # 현재 프로그램에서는 사용하지 않는 GUI 프레임워크
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    noarchive=False,
    optimize=0,
)


# ---------------------------------------------------------------------------
# Python 모듈 아카이브
# ---------------------------------------------------------------------------

python_archive = PYZ(
    analysis.pure,
)


# ---------------------------------------------------------------------------
# Windows 실행파일
# ---------------------------------------------------------------------------

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AuditGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,

    # PyTorch, tokenizers 등의 DLL은 UPX 압축으로 문제가 발생할 수 있어
    # 첫 안정화 빌드에서는 압축하지 않는다.
    upx=False,

    # 콘솔 포함:
    # 로그 확인, Ctrl+C 종료, 오류 메시지 확인
    console=True,

    disable_windowed_traceback=False,

    # macOS 전용 기능이므로 Windows에서는 False
    argv_emulation=False,

    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,

    # PyInstaller 6 onedir 내부 파일 디렉터리
    contents_directory="_internal",

    # 프로그램 아이콘은 이후 별도로 추가
    icon=None,
)


# ---------------------------------------------------------------------------
# onedir 결과 폴더 생성
# ---------------------------------------------------------------------------

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AuditGuard",
)