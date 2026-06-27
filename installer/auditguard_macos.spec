# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
import shutil
import stat

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
)


# ---------------------------------------------------------------------------
# 프로젝트 경로
# ---------------------------------------------------------------------------

SPEC_DIRECTORY = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIRECTORY.parent

LAUNCHER_PATH = (
    SPEC_DIRECTORY
    / "macos_launcher.py"
)

COMMAND_SOURCE_PATH = (
    SPEC_DIRECTORY
    / "AuditGuard.command"
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
# macOS 빌드 설정
# ---------------------------------------------------------------------------

# 값을 지정하지 않으면 현재 Mac과 Python의 아키텍처를 사용한다.
#
# Apple Silicon:
#   arm64
#
# Intel Mac:
#   x86_64
#
# 두 아키텍처 통합:
#   universal2
#
# 환경변수 예:
#   AUDITGUARD_MACOS_TARGET_ARCH=arm64
TARGET_ARCH = (
    os.environ.get(
        "AUDITGUARD_MACOS_TARGET_ARCH",
    )
    or None
)

VALID_TARGET_ARCHITECTURES = {
    None,
    "arm64",
    "x86_64",
    "universal2",
}

if TARGET_ARCH not in VALID_TARGET_ARCHITECTURES:
    raise ValueError(
        "AUDITGUARD_MACOS_TARGET_ARCH는 "
        "arm64, x86_64, universal2 중 하나여야 합니다. "
        f"현재 값: {TARGET_ARCH}"
    )


# 팀 내부 테스트 빌드에서는 보통 지정하지 않는다.
#
# 지정하지 않으면 PyInstaller가 ad-hoc signing을 적용한다.
#
# 외부 배포용 서명 예:
#   AUDITGUARD_MACOS_CODESIGN_IDENTITY="Developer ID Application: ..."
CODESIGN_IDENTITY = (
    os.environ.get(
        "AUDITGUARD_MACOS_CODESIGN_IDENTITY",
    )
    or None
)


# ---------------------------------------------------------------------------
# 빌드 전 필수 파일 검사
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    LAUNCHER_PATH,
    COMMAND_SOURCE_PATH,
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
            "macOS 빌드에 필요한 파일이 없습니다: "
            f"{required_file}"
        )


for required_directory in REQUIRED_DIRECTORIES:
    if not required_directory.is_dir():
        raise FileNotFoundError(
            "macOS 빌드에 필요한 디렉터리가 없습니다: "
            f"{required_directory}"
        )


# ---------------------------------------------------------------------------
# 프로젝트 데이터 파일 수집
# ---------------------------------------------------------------------------

def collect_directory_files(
    source_directory: Path,
    destination_directory: str,
    *,
    excluded_directory_names: frozenset[str] = frozenset(),
    excluded_file_names: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """
    디렉터리 안의 파일을 재귀적으로 수집하여
    PyInstaller datas 형식으로 변환한다.

    반환 예:
        [
            (
                "/project/web/templates/index.html",
                "web/templates",
            ),
        ]
    """

    collected_files: list[tuple[str, str]] = []

    for source_file in source_directory.rglob("*"):
        if not source_file.is_file():
            continue

        relative_path = source_file.relative_to(
            source_directory
        )

        directory_parts = relative_path.parts[:-1]

        if any(
            directory_name in excluded_directory_names
            for directory_name in directory_parts
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


datas: list[tuple[str, str]] = []


# HTML 템플릿
datas += collect_directory_files(
    WEB_TEMPLATES_DIRECTORY,
    "web/templates",
)


# CSS, JavaScript 등의 웹 정적 리소스
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


# bge-small-en-v1.5 로컬 Semantic 모델
#
# Hugging Face 다운로드 캐시는 실행에 필요하지 않으므로 제외한다.
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
# 패키지 데이터, 바이너리, hidden import 수집
# ---------------------------------------------------------------------------

binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []


def collect_package(
    package_name: str,
) -> None:
    """
    동적 import와 패키지 데이터가 많은 패키지를 수집한다.
    """

    (
        package_datas,
        package_binaries,
        package_hiddenimports,
    ) = collect_all(
        package_name,
        on_error="warn once",
    )

    datas.extend(
        package_datas
    )
    binaries.extend(
        package_binaries
    )
    hiddenimports.extend(
        package_hiddenimports
    )


# sentence-transformers는 모델 설정에 따라 클래스를 동적으로
# 불러올 수 있으므로 명시적으로 수집한다.
collect_package(
    "sentence_transformers"
)


# Transformers의 lazy import와 모델 구현 모듈
collect_package(
    "transformers"
)


# 바이너리 확장 또는 패키지 데이터 포함
collect_package(
    "tokenizers"
)

collect_package(
    "safetensors"
)


# Uvicorn은 설정 문자열에 따라 프로토콜과 lifespan 구현체를
# 동적으로 선택할 수 있다.
hiddenimports += collect_submodules(
    "uvicorn",
    on_error="warn once",
)


# MCP SDK의 transport/client 구현체를 포함한다.
hiddenimports += collect_submodules(
    "mcp",
    on_error="warn once",
)


# importlib.metadata를 사용하는 패키지를 위해 dist-info 포함
datas += copy_metadata(
    "sentence-transformers",
    recursive=True,
)


# ---------------------------------------------------------------------------
# 중복 제거
# ---------------------------------------------------------------------------

def deduplicate_tuples(
    values: list[tuple[str, str]],
) -> list[tuple[str, str]]:
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
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


datas = deduplicate_tuples(
    datas
)

binaries = deduplicate_tuples(
    binaries
)

hiddenimports = deduplicate_strings(
    hiddenimports
)


# ---------------------------------------------------------------------------
# PyInstaller Analysis
# ---------------------------------------------------------------------------

analysis = Analysis(
    [
        str(LAUNCHER_PATH),
    ],
    pathex=[
        str(PROJECT_ROOT),
        str(SPEC_DIRECTORY),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 테스트·개발 도구
        "pytest",
        "_pytest",
        "IPython",
        "jupyter",
        "notebook",

        # 현재 사용자 프로그램에서 사용하지 않는 GUI
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",

        # Windows 전용 패키지
        "win32api",
        "win32com",
        "pythoncom",
        "pywintypes",
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
# macOS 콘솔 실행파일
# ---------------------------------------------------------------------------

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,

    # macOS에서는 .exe 확장자가 붙지 않는다.
    name="AuditGuard",

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,

    # PyTorch, tokenizers, safetensors 등의 바이너리 안정성을 위해
    # UPX를 사용하지 않는다.
    upx=False,

    # Terminal 출력을 사용하는 콘솔 프로그램
    console=True,

    disable_windowed_traceback=False,

    # .app이 아닌 콘솔 실행파일이므로 argv emulation은 필요하지 않다.
    argv_emulation=False,

    target_arch=TARGET_ARCH,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=None,

    contents_directory="_internal",

    # .app용 icns 아이콘은 현재 사용하지 않는다.
    icon=None,
)


# ---------------------------------------------------------------------------
# onedir 결과 생성
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


# ---------------------------------------------------------------------------
# AuditGuard.command를 최종 배포 폴더 최상위에 복사
# ---------------------------------------------------------------------------

DIST_DIRECTORY = (
    Path(DISTPATH).resolve()
    / "AuditGuard"
)

COMMAND_DESTINATION_PATH = (
    DIST_DIRECTORY
    / "AuditGuard.command"
)


if not DIST_DIRECTORY.is_dir():
    raise RuntimeError(
        "PyInstaller onedir 결과 폴더를 찾을 수 없습니다: "
        f"{DIST_DIRECTORY}"
    )


shutil.copy2(
    COMMAND_SOURCE_PATH,
    COMMAND_DESTINATION_PATH,
)


# Finder에서 더블클릭할 수 있도록 실행 권한 추가
current_mode = (
    COMMAND_DESTINATION_PATH
    .stat()
    .st_mode
)

COMMAND_DESTINATION_PATH.chmod(
    current_mode
    | stat.S_IXUSR
    | stat.S_IXGRP
    | stat.S_IXOTH
)