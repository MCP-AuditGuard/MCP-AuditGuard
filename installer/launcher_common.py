from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from dataclasses import dataclass
from pathlib import Path
from typing import Final


def _configure_source_import_path() -> None:
    """
    PyInstaller 빌드 전 Python으로 Launcher를 직접 실행할 때
    프로젝트 루트의 소스 코드를 site-packages보다 우선해서 사용한다.

    예:
        Windows
        .venv-build\\Scripts\\python.exe installer\\windows_launcher.py

        macOS
        .venv-build/bin/python installer/macos_launcher.py

    PyInstaller로 빌드된 실행파일에서는 번들 내부 모듈을 사용하므로
    sys.path를 변경하지 않는다.
    """

    if getattr(sys, "frozen", False):
        return

    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)

    # 같은 경로가 뒤쪽에 들어 있다면 제거하고 가장 앞에 다시 추가한다.
    #
    # 이렇게 해야 일반 설치된 site-packages의 프로젝트 모듈보다
    # 현재 Git 작업 폴더의 소스 코드가 우선된다.
    try:
        sys.path.remove(project_root_text)
    except ValueError:
        pass

    sys.path.insert(0, project_root_text)


_configure_source_import_path()


# 프로젝트 루트 경로를 sys.path에 설정한 뒤 import해야 한다.
import uvicorn  # noqa: E402

from core.runtime_preflight import (  # noqa: E402
    RuntimePreflightResult,
    run_runtime_preflight,
)


DEFAULT_SERVER_HOST: Final[str] = "127.0.0.1"
DEFAULT_START_PORT: Final[int] = 8000
DEFAULT_END_PORT: Final[int] = 8099
DEFAULT_HEALTH_PATH: Final[str] = "/health"

DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_HEALTH_CHECK_INTERVAL_SECONDS: Final[float] = 0.2
DEFAULT_HEALTH_REQUEST_TIMEOUT_SECONDS: Final[float] = 1.0


@dataclass(frozen=True)
class LauncherConfig:
    """
    운영체제별 Launcher가 공통 실행 코드에 전달하는 설정.

    application_name:
        프로그램 이름.

    platform_name:
        콘솔에 표시할 운영체제 또는 Launcher 이름.

    host:
        Uvicorn이 바인딩할 주소.
        기본값은 이 PC에서만 접근할 수 있는 127.0.0.1이다.

    start_port, end_port:
        사용할 수 있는 포트를 순서대로 찾을 범위.

    health_path:
        FastAPI 서버 준비 여부를 확인할 API 경로.
    """

    application_name: str = "MCP-AuditGuard"
    platform_name: str = "Local Web Launcher"

    host: str = DEFAULT_SERVER_HOST
    start_port: int = DEFAULT_START_PORT
    end_port: int = DEFAULT_END_PORT

    health_path: str = DEFAULT_HEALTH_PATH

    health_check_timeout_seconds: float = (
        DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
    )
    health_check_interval_seconds: float = (
        DEFAULT_HEALTH_CHECK_INTERVAL_SECONDS
    )
    health_request_timeout_seconds: float = (
        DEFAULT_HEALTH_REQUEST_TIMEOUT_SECONDS
    )


@dataclass
class ServerStartupState:
    """
    서버 준비 확인 스레드가 메인 스레드에 전달하는 상태.

    browser_opened:
        기본 브라우저 실행 요청에 성공했는지 여부.

    error_message:
        제한 시간 안에 /health 응답을 받지 못한 경우의 오류.
    """

    browser_opened: bool = False
    error_message: str | None = None


def run_launcher(
    config: LauncherConfig,
) -> int:
    """
    Windows와 macOS가 공통으로 사용하는 AuditGuard 실행 흐름.

    실행 순서:
    1. Semantic Runtime Preflight
    2. 사용 가능한 로컬 포트 검색
    3. FastAPI 앱 import
    4. Uvicorn 서버 실행
    5. /health 응답 확인
    6. 기본 브라우저 실행
    7. Ctrl+C 또는 콘솔 종료 시 서버 종료
    """

    _print_startup_header(config)

    preflight_result = run_runtime_preflight()

    if not preflight_result.semantic_ready:
        _print_preflight_failure(preflight_result)
        _pause_before_exit()
        return 1

    _print_preflight_success(preflight_result)

    try:
        port = find_available_port(
            host=config.host,
            start_port=config.start_port,
            end_port=config.end_port,
        )
    except (ValueError, RuntimeError) as error:
        _print_fatal_error(
            title="사용 가능한 포트를 찾지 못했습니다.",
            detail=str(error),
        )
        _pause_before_exit()
        return 1

    server_url = f"http://{config.host}:{port}"
    health_url = f"{server_url}{config.health_path}"

    try:
        # Semantic 사전 검사가 끝난 뒤 기존 FastAPI 앱을 불러온다.
        # 웹 API나 Scanner 기능을 Launcher에서 새로 만들지 않는다.
        from web.app import app
    except Exception as error:
        _print_fatal_error(
            title="웹 애플리케이션을 불러오지 못했습니다.",
            detail=f"{type(error).__name__}: {error}",
        )
        _pause_before_exit()
        return 1

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )

    server = uvicorn.Server(
        config=uvicorn_config,
    )

    startup_state = ServerStartupState()

    browser_thread = threading.Thread(
        target=_wait_for_server_and_open_browser,
        kwargs={
            "server": server,
            "server_url": server_url,
            "health_url": health_url,
            "launcher_config": config,
            "startup_state": startup_state,
        },
        name="auditguard-browser-launcher",
        daemon=True,
    )

    _print_server_information(
        config=config,
        server_url=server_url,
        port=port,
    )

    browser_thread.start()

    try:
        # Uvicorn 서버는 메인 스레드에서 실행한다.
        #
        # 그래야 Windows와 macOS 모두에서 Ctrl+C 종료 신호를
        # Uvicorn이 정상적으로 처리할 수 있다.
        server.run()

    except KeyboardInterrupt:
        server.should_exit = True

    except SystemExit as error:
        exit_code = _normalize_exit_code(
            error.code,
        )

        if exit_code != 0:
            _print_fatal_error(
                title="웹 서버가 비정상 종료되었습니다.",
                detail=(
                    "Uvicorn이 종료 코드 "
                    f"{exit_code}을 반환했습니다."
                ),
            )
            _pause_before_exit()

        return exit_code

    except Exception as error:
        _print_fatal_error(
            title="웹 서버 실행 중 오류가 발생했습니다.",
            detail=f"{type(error).__name__}: {error}",
        )
        _pause_before_exit()
        return 1

    if startup_state.error_message is not None:
        _print_fatal_error(
            title="웹 서버 준비 확인에 실패했습니다.",
            detail=startup_state.error_message,
        )
        _pause_before_exit()
        return 1

    if not server.started:
        _print_fatal_error(
            title="웹 서버가 정상적으로 시작되지 않았습니다.",
            detail=(
                "Uvicorn 서버가 시작 상태에 도달하지 못했습니다. "
                "콘솔에 먼저 출력된 오류 내용을 확인하세요."
            ),
        )
        _pause_before_exit()
        return 1

    print()
    print(f"{config.application_name}가 종료되었습니다.")

    return 0


def find_available_port(
    *,
    host: str,
    start_port: int,
    end_port: int,
) -> int:
    """
    지정한 범위에서 사용할 수 있는 첫 번째 TCP 포트를 반환한다.

    기본 범위:
        127.0.0.1:8000
        ~
        127.0.0.1:8099
    """

    if start_port < 1:
        raise ValueError(
            "start_port는 1 이상이어야 합니다."
        )

    if end_port > 65535:
        raise ValueError(
            "end_port는 65535 이하여야 합니다."
        )

    if start_port > end_port:
        raise ValueError(
            "start_port는 end_port보다 클 수 없습니다."
        )

    for port in range(
        start_port,
        end_port + 1,
    ):
        if _is_port_available(
            host=host,
            port=port,
        ):
            return port

    raise RuntimeError(
        f"{host}:{start_port}~{end_port} 범위에 "
        "사용 가능한 포트가 없습니다."
    )


def _is_port_available(
    *,
    host: str,
    port: int,
) -> bool:
    """
    지정한 주소에 임시로 bind하여 포트 사용 가능 여부를 확인한다.

    확인 후 소켓을 즉시 닫고 Uvicorn이 같은 포트를 사용한다.
    검사와 실제 서버 시작 사이에는 매우 작은 경쟁 가능성이 있으므로,
    최종 bind 실패는 Uvicorn 오류 처리에서 다시 확인된다.
    """

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as probe_socket:
            probe_socket.bind(
                (host, port),
            )
            probe_socket.listen(1)

        return True

    except OSError:
        return False


def _wait_for_server_and_open_browser(
    *,
    server: uvicorn.Server,
    server_url: str,
    health_url: str,
    launcher_config: LauncherConfig,
    startup_state: ServerStartupState,
) -> None:
    """
    /health가 HTTP 200을 반환할 때까지 기다린 뒤 브라우저를 연다.

    제한 시간 안에 서버가 준비되지 않으면 Uvicorn에 종료를 요청하고
    오류 내용을 ServerStartupState에 기록한다.
    """

    deadline = (
        time.monotonic()
        + launcher_config.health_check_timeout_seconds
    )

    while time.monotonic() < deadline:
        if server.should_exit:
            return

        if _is_health_endpoint_ready(
            health_url=health_url,
            request_timeout_seconds=(
                launcher_config.health_request_timeout_seconds
            ),
        ):
            startup_state.browser_opened = _open_browser(
                server_url=server_url,
            )
            return

        time.sleep(
            launcher_config.health_check_interval_seconds
        )

    startup_state.error_message = (
        "제한 시간 안에 웹 서버의 상태 확인 응답을 받지 "
        "못했습니다.\n"
        f"제한 시간: "
        f"{launcher_config.health_check_timeout_seconds:.0f}초\n"
        f"확인 주소: {health_url}"
    )

    # 불완전하게 실행된 서버를 계속 유지하지 않는다.
    server.should_exit = True


def _is_health_endpoint_ready(
    *,
    health_url: str,
    request_timeout_seconds: float,
) -> bool:
    """
    FastAPI /health API가 HTTP 200을 반환하는지 확인한다.
    """

    request = urllib.request.Request(
        health_url,
        method="GET",
        headers={
            "User-Agent": (
                "MCP-AuditGuard-Local-Launcher"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=request_timeout_seconds,
        ) as response:
            return response.status == 200

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False


def _open_browser(
    *,
    server_url: str,
) -> bool:
    """
    운영체제의 기본 브라우저로 AuditGuard 웹 화면을 연다.

    브라우저 실행에 실패해도 서버는 계속 실행한다.
    사용자가 콘솔에 표시된 주소를 직접 입력할 수 있기 때문이다.
    """

    print()
    print("웹 서버 준비가 완료되었습니다.")
    print(f"브라우저를 엽니다: {server_url}")
    print()

    try:
        opened = webbrowser.open(
            server_url,
            new=2,
            autoraise=True,
        )
    except Exception as error:
        print(
            "[경고] 기본 브라우저를 자동으로 열지 "
            "못했습니다."
        )
        print(
            f"{type(error).__name__}: {error}"
        )
        print(
            "아래 주소를 브라우저에 직접 입력하세요."
        )
        print(server_url)
        return False

    if not opened:
        print(
            "[경고] 운영체제가 브라우저 실행 요청을 "
            "처리하지 못했습니다."
        )
        print(
            "아래 주소를 브라우저에 직접 입력하세요."
        )
        print(server_url)
        return False

    return True


def _print_startup_header(
    config: LauncherConfig,
) -> None:
    """
    Launcher 시작 메시지를 출력한다.
    """

    print("=" * 68)
    print(config.application_name)
    print(config.platform_name)
    print("=" * 68)
    print()
    print("프로그램 실행 환경을 확인하고 있습니다.")
    print(
        "Semantic 모델을 처음 로드할 때 "
        "잠시 시간이 걸릴 수 있습니다."
    )
    print()


def _print_preflight_success(
    result: RuntimePreflightResult,
) -> None:
    """
    Semantic 사전 검사 성공 결과를 출력한다.
    """

    print(
        "[정상] Semantic 실행 환경 검사가 완료되었습니다."
    )
    print(
        f"  Provider : {result.provider_name}"
    )

    if result.model_path is not None:
        print(
            f"  Model    : {result.model_path}"
        )

    if result.embedding_dimension is not None:
        print(
            "  Dimension: "
            f"{result.embedding_dimension}"
        )

    print()


def _print_preflight_failure(
    result: RuntimePreflightResult,
) -> None:
    """
    Semantic 사전 검사 실패 결과를 출력한다.
    """

    print()
    print("=" * 68)
    print(
        "[실행 실패] Semantic 환경을 준비하지 못했습니다."
    )
    print("=" * 68)

    print(
        "오류 코드: "
        f"{result.error_code or 'unknown_error'}"
    )

    print(
        f"Provider : {result.provider_name}"
    )

    if result.model_path is not None:
        print(
            f"모델 경로: {result.model_path}"
        )

    print(
        "오류 내용: "
        f"{result.error_message or '알 수 없는 오류'}"
    )

    print()
    print(
        "MCP-AuditGuard 사용자용 프로그램은 Semantic 검사가 "
        "정상적으로 준비되지 않으면 실행되지 않습니다."
    )


def _print_server_information(
    *,
    config: LauncherConfig,
    server_url: str,
    port: int,
) -> None:
    """
    서버 주소와 종료 방법을 출력한다.
    """

    print("=" * 68)
    print(
        f"{config.application_name} 로컬 웹 서버를 시작합니다."
    )
    print("=" * 68)
    print(f"주소      : {server_url}")
    print(f"포트      : {port}")
    print("접근 범위 : 이 기기에서만 접속 가능")
    print(
        "종료 방법 : 이 콘솔에서 Ctrl+C 또는 콘솔 창 닫기"
    )
    print()
    print(
        "주의: 브라우저 창만 닫아서는 "
        f"{config.application_name}가 종료되지 않습니다."
    )
    print()


def _print_fatal_error(
    *,
    title: str,
    detail: str,
) -> None:
    """
    프로그램을 계속 실행할 수 없는 오류를 출력한다.
    """

    print()
    print("=" * 68)
    print(f"[실행 실패] {title}")
    print("=" * 68)
    print(detail)
    print()


def _pause_before_exit() -> None:
    """
    더블클릭 실행 중 오류 메시지가 바로 사라지지 않도록 대기한다.

    표준 입력이 연결되지 않은 환경에서는 바로 종료될 수 있다.
    """

    try:
        input("종료하려면 Enter 키를 누르세요.")
    except (EOFError, KeyboardInterrupt):
        pass


def _normalize_exit_code(
    exit_code: object,
) -> int:
    """
    SystemExit.code를 정수 종료 코드로 정규화한다.
    """

    if exit_code is None:
        return 0

    if isinstance(exit_code, int):
        return exit_code

    return 1