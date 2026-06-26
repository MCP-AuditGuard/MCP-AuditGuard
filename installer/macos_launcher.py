from __future__ import annotations

import sys

from launcher_common import (
    LauncherConfig,
    run_launcher,
)


APPLICATION_NAME = "MCP-AuditGuard"


def main() -> int:
    """
    macOS 사용자용 AuditGuard 실행 진입점.

    macOS Terminal 제목을 설정한 뒤
    공통 Launcher 실행 흐름을 호출한다.

    이 Launcher는 콘솔 실행을 기준으로 한다.

    권장 사용자 실행 방식:
        AuditGuard.command 더블클릭
        또는 Terminal에서 AuditGuard 실행
    """

    _set_macos_terminal_title(
        APPLICATION_NAME
    )

    return run_launcher(
        LauncherConfig(
            application_name=APPLICATION_NAME,
            platform_name=(
                "macOS Local Web Launcher"
            ),
        )
    )


def _set_macos_terminal_title(
    title: str,
) -> None:
    """
    ANSI escape sequence를 사용해 macOS Terminal 제목을 설정한다.

    표준 출력이 Terminal에 연결되어 있지 않거나
    제목 설정을 지원하지 않는 환경에서는 아무 작업도 하지 않는다.
    """

    try:
        if not sys.stdout.isatty():
            return

        sys.stdout.write(
            f"\033]0;{title}\007"
        )
        sys.stdout.flush()

    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    raise SystemExit(main())