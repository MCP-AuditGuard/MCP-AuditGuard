from __future__ import annotations

import ctypes
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from pathlib import Path
from typing import Final


def _configure_source_import_path() -> None:
    """
    PyInstaller 빌드 전 Python으로 Launcher를 직접 실행할 때,
    프로젝트 루트의 소스 코드를 site-packages보다 우선해서 사용한다.

    예:
        .venv-build\\Scripts\\python.exe
            installer\\windows_launcher.py

    PyInstaller 실행파일에서는 번들 내부 모듈을 사용하므로
    이 처리를 수행하지 않는다.
    """

    if getattr(sys, "frozen", False):
        return

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )
    project_root_text = str(project_root)

    # 이미 sys.path에 있더라도 site-packages보다 뒤에 있다면
    # 우선순위가 낮으므로 제거 후 맨 앞에 다시 넣는다.
    try:
        sys.path.remove(project_root_text)
    except ValueError:
        pass

    sys.path.insert(
        0,
        project_root_text,
    )


_configure_source_import_path()


# 프로젝트 루트 import 경로를 먼저 설정한 뒤
# 외부 패키지와 프로젝트 모듈을 import한다.
import uvicorn

from core.runtime_preflight import (
    RuntimePreflightResult,
    run_runtime_preflight,
)


APPLICATION_NAME: Final[str] = "MCP-AuditGuard"

SERVER_HOST: Final[str] = "127.0.0.1"

START_PORT: Final[int] = 8000
END_PORT: Final[int] = 8099

HEALTH_PATH: Final[str] = "/health"

HEALTH_CHECK_TIMEOUT_SECONDS: Final[float] = 30.0
HEALTH_CHECK_INTERVAL_SECONDS: Final[float] = 0.2
HEALTH_REQUEST_TIMEOUT_SECONDS: Final[float] = 1.0


def main() -> int:
    """
    MCP-AuditGuard Windows 사용자용 실행 진입점.

    실행 순서:
    1. 콘솔 초기화
    2. Semantic Runtime Preflight 실행
    3. 사용 가능한 로컬 포트 선택
    4. FastAPI 앱 로드
    5. Uvicorn 서버 실행
    6. 서버 준비 후 브라우저 자동 실행
    7. Ctrl+C 또는 콘솔 종료 시 프로그램 종료
    """

    _set_console_title(APPLICATION_NAME)
    _print_startup_header()

    preflight_result = run_runtime_preflight()

    if not preflight_result.semantic_ready:
        _print_preflight_failure(preflight_result)
        _pause_before_exit()
        return 1

    _print_preflight_success(preflight_result)

    try:
        port = find_available_port(
            host=SERVER_HOST,
            start_port=START_PORT,
            end_port=END_PORT,
        )
    except RuntimeError as error:
        _print_fatal_error(
            title="사용 가능한 포트를 찾지 못했습니다.",
            detail=str(error),
        )
        _pause_before_exit()
        return 1

    server_url = f"http://{SERVER_HOST}:{port}"
    health_url = f"{server_url}{HEALTH_PATH}"

    try:
        # Semantic 사전 검사와 포트 선택이 끝난 뒤 웹 앱을 import합니다.
        #
        # 이렇게 하면 모델이나 실행환경이 잘못된 상태에서 FastAPI 서버를
        # 불필요하게 초기화하지 않습니다.
        from web.app import app
    except Exception as error:
        _print_fatal_error(
            title="웹 애플리케이션을 불러오지 못했습니다.",
            detail=f"{type(error).__name__}: {error}",
        )
        _pause_before_exit()
        return 1

    config = uvicorn.Config(
        app=app,
        host=SERVER_HOST,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )

    server = uvicorn.Server(config=config)

    browser_thread = threading.Thread(
        target=_wait_for_server_and_open_browser,
        kwargs={
            "server": server,
            "server_url": server_url,
            "health_url": health_url,
        },
        name="auditguard-browser-launcher",
        daemon=True,
    )

    _print_server_information(
        server_url=server_url,
        port=port,
    )

    browser_thread.start()

    try:
        # 서버를 메인 스레드에서 실행해야 Uvicorn이 Windows의
        # Ctrl+C 종료 신호를 정상적으로 처리할 수 있습니다.
        server.run()
    except KeyboardInterrupt:
        # Uvicorn이 대부분의 Ctrl+C를 직접 처리하지만,
        # 실행 환경에 따라 여기까지 전달될 수 있으므로 안전하게 처리합니다.
        server.should_exit = True
    except Exception as error:
        _print_fatal_error(
            title="웹 서버 실행 중 오류가 발생했습니다.",
            detail=f"{type(error).__name__}: {error}",
        )
        _pause_before_exit()
        return 1

    if not server.started:
        _print_fatal_error(
            title="웹 서버가 정상적으로 시작되지 않았습니다.",
            detail=(
                "Uvicorn 서버가 시작 상태에 도달하지 못했습니다. "
                "위에 출력된 오류 내용을 확인하세요."
            ),
        )
        _pause_before_exit()
        return 1

    print()
    print("MCP-AuditGuard가 종료되었습니다.")

    return 0


def find_available_port(
    *,
    host: str,
    start_port: int,
    end_port: int,
) -> int:
    """
    지정한 포트 범위에서 현재 사용할 수 있는 첫 번째 포트를 반환한다.

    기본 범위:
        127.0.0.1:8000 ~ 127.0.0.1:8099

    포트를 찾지 못하면 RuntimeError를 발생시킨다.
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

    for port in range(start_port, end_port + 1):
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
    지정한 TCP 주소에 임시로 bind하여 포트 사용 가능 여부를 확인한다.

    이 함수는 포트를 계속 점유하지 않는다.
    포트 확인 직후 Uvicorn을 시작하여 경쟁 가능성을 최소화한다.
    """

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as probe_socket:
            probe_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )

            probe_socket.bind(
                (host, port),
            )

        return True
    except OSError:
        return False


def _wait_for_server_and_open_browser(
    *,
    server: uvicorn.Server,
    server_url: str,
    health_url: str,
) -> None:
    """
    Uvicorn 서버의 /health 응답을 기다린 뒤 기본 브라우저를 연다.

    서버 시작과 동시에 브라우저를 열지 않고 실제 HTTP 200 응답을
    확인한 후 브라우저를 열기 때문에 연결 실패 화면이 먼저 나타나는
    문제를 줄인다.

    제한 시간 안에 서버가 준비되지 않으면 서버 종료를 요청한다.
    """

    deadline = (
        time.monotonic()
        + HEALTH_CHECK_TIMEOUT_SECONDS
    )

    while time.monotonic() < deadline:
        if server.should_exit:
            return

        if _is_health_endpoint_ready(health_url):
            _open_browser(
                server_url=server_url,
            )
            return

        time.sleep(
            HEALTH_CHECK_INTERVAL_SECONDS
        )

    print()
    print("[오류] 웹 서버 준비 확인에 실패했습니다.")
    print(
        f"제한 시간: "
        f"{HEALTH_CHECK_TIMEOUT_SECONDS:.0f}초"
    )
    print(f"확인 주소: {health_url}")
    print(
        "웹 서버가 실행 중이지만 /health 응답이 없거나, "
        "서버 시작 중 오류가 발생했습니다."
    )

    # 브라우저를 열 수 없는 불완전한 상태로 프로세스를 계속
    # 유지하지 않도록 Uvicorn 서버 종료를 요청합니다.
    server.should_exit = True


def _is_health_endpoint_ready(
    health_url: str,
) -> bool:
    """
    /health가 HTTP 200을 반환하는지 확인한다.
    """

    request = urllib.request.Request(
        health_url,
        method="GET",
        headers={
            "User-Agent": (
                "MCP-AuditGuard-Windows-Launcher"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=HEALTH_REQUEST_TIMEOUT_SECONDS,
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
) -> None:
    """
    Windows 기본 브라우저로 MCP-AuditGuard 웹 화면을 연다.
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
        return

    if not opened:
        print(
            "[경고] Windows가 브라우저 실행 요청을 "
            "처리하지 못했습니다."
        )
        print(
            "아래 주소를 브라우저에 직접 입력하세요."
        )
        print(server_url)


def _print_startup_header() -> None:
    """
    사용자용 Launcher 시작 메시지를 출력한다.
    """

    print("=" * 68)
    print("MCP-AuditGuard")
    print("Windows Local Web Launcher")
    print("=" * 68)
    print()
    print("프로그램 실행 환경을 확인하고 있습니다.")
    print("Semantic 모델을 처음 로드할 때 잠시 시간이 걸릴 수 있습니다.")
    print()


def _print_preflight_success(
    result: RuntimePreflightResult,
) -> None:
    """
    Semantic 사전 검사 성공 정보를 콘솔에 출력한다.
    """

    print("[정상] Semantic 실행 환경 검사가 완료되었습니다.")
    print(f"  Provider : {result.provider_name}")

    if result.model_path is not None:
        print(f"  Model    : {result.model_path}")

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
    Semantic 사전 검사 실패 정보를 콘솔에 출력한다.
    """

    print()
    print("=" * 68)
    print("[실행 실패] Semantic 환경을 준비하지 못했습니다.")
    print("=" * 68)

    print(
        f"오류 코드: "
        f"{result.error_code or 'unknown_error'}"
    )

    print(
        f"Provider : "
        f"{result.provider_name}"
    )

    if result.model_path is not None:
        print(
            f"모델 경로: "
            f"{result.model_path}"
        )

    print(
        f"오류 내용: "
        f"{result.error_message or '알 수 없는 오류'}"
    )

    print()
    print(
        "MCP-AuditGuard 사용자용 프로그램은 Semantic 검사가 "
        "정상적으로 준비되지 않으면 실행되지 않습니다."
    )


def _print_server_information(
    *,
    server_url: str,
    port: int,
) -> None:
    """
    사용자가 서버 실행 상태와 종료 방법을 확인할 수 있게 출력한다.
    """

    print("=" * 68)
    print("MCP-AuditGuard 로컬 웹 서버를 시작합니다.")
    print("=" * 68)
    print(f"주소      : {server_url}")
    print(f"포트      : {port}")
    print("접근 범위 : 이 PC에서만 접속 가능")
    print("종료 방법 : 이 콘솔에서 Ctrl+C 또는 콘솔 창 닫기")
    print()
    print(
        "주의: 브라우저 창만 닫아서는 "
        "MCP-AuditGuard가 종료되지 않습니다."
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

    터미널이나 자동화 환경에서 표준 입력이 없는 경우에는
    EOFError를 무시하고 바로 종료한다.
    """

    try:
        input("종료하려면 Enter 키를 누르세요.")
    except (EOFError, KeyboardInterrupt):
        pass


def _set_console_title(
    title: str,
) -> None:
    """
    Windows 콘솔 창 제목을 설정한다.

    Windows가 아니거나 API 호출이 실패하더라도 실행에는 영향을
    주지 않도록 오류를 무시한다.
    """

    try:
        ctypes.windll.kernel32.SetConsoleTitleW(
            title
        )
    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    raise SystemExit(main())