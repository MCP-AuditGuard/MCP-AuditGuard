from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 내부 리소스의 상대 경로
# ---------------------------------------------------------------------------

WEB_TEMPLATES_RELATIVE_PATH = Path("web") / "templates"
WEB_STATIC_RELATIVE_PATH = Path("web") / "static"
RULES_RELATIVE_PATH = Path("rules")

EMBEDDING_MODEL_RELATIVE_PATH = (
    Path("models")
    / "embedding"
    / "bge-small-en-v1.5"
)


def is_frozen() -> bool:
    """
    현재 프로그램이 PyInstaller 실행파일로 실행되고 있는지 반환한다.

    일반 Python 실행:
        False

    PyInstaller로 빌드된 AuditGuard.exe 실행:
        True
    """

    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """
    프로그램에 포함된 읽기 전용 리소스의 기준 디렉터리를 반환한다.

    개발 환경에서는 프로젝트 루트를 반환한다.

        C:\\Dinho\\Work\\MCP_GitHub

    PyInstaller onedir 환경에서는 PyInstaller가 데이터 파일을 배치한
    내부 리소스 디렉터리를 반환한다.

        dist\\AuditGuard\\_internal

    이 함수가 반환하는 위치 아래에 다음 디렉터리가 존재해야 한다.

        web\\templates
        web\\static
        rules
        models\\embedding\\bge-small-en-v1.5
    """

    if is_frozen():
        pyinstaller_bundle_root = getattr(
            sys,
            "_MEIPASS",
            None,
        )

        if pyinstaller_bundle_root:
            return Path(pyinstaller_bundle_root).resolve()

        # 일반적으로 PyInstaller 실행에서는 _MEIPASS가 존재한다.
        # 예상하지 못한 실행 환경에서도 최소한 실행파일 위치를
        # 기준으로 동작할 수 있도록 fallback을 제공한다.
        return Path(sys.executable).resolve().parent

    # 이 파일의 실제 위치:
    #
    #   프로젝트루트/core/runtime_paths.py
    #
    # parents[0] = core
    # parents[1] = 프로젝트 루트
    return Path(__file__).resolve().parents[1]


def executable_directory() -> Path:
    """
    현재 실행 프로그램이 위치한 디렉터리를 반환한다.

    개발 환경:
        프로젝트 루트

    PyInstaller onedir 환경:
        AuditGuard.exe가 있는 디렉터리

        예:
        dist\\AuditGuard

    resource_root()와 다르게, 이 함수는 실행파일 자체가 위치한
    외부 디렉터리를 반환한다.
    """

    if is_frozen():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def resource_path(
    *parts: str | Path,
) -> Path:
    """
    프로그램 리소스 루트를 기준으로 하위 경로를 생성한다.

    예:
        resource_path("web", "templates")
        resource_path("rules")
        resource_path("models", "embedding", "bge-small-en-v1.5")
    """

    path = resource_root()

    for part in parts:
        path = path / Path(part)

    return path


def web_templates_directory() -> Path:
    """
    Jinja2 HTML 템플릿 디렉터리를 반환한다.
    """

    return resource_path(WEB_TEMPLATES_RELATIVE_PATH)


def web_static_directory() -> Path:
    """
    CSS, JavaScript 등의 웹 정적 파일 디렉터리를 반환한다.
    """

    return resource_path(WEB_STATIC_RELATIVE_PATH)


def rules_directory() -> Path:
    """
    Tool Poisoning 및 Semantic 규칙 YAML 디렉터리를 반환한다.
    """

    return resource_path(RULES_RELATIVE_PATH)


def embedding_model_directory() -> Path:
    """
    프로그램에 포함된 sentence-transformers 모델 디렉터리를 반환한다.

    모델:
        bge-small-en-v1.5
    """

    return resource_path(EMBEDDING_MODEL_RELATIVE_PATH)