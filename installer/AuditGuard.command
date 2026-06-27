#!/bin/zsh

set -u


SCRIPT_DIRECTORY="$(
    cd -- "$(dirname -- "$0")"
    pwd
)"

AUDITGUARD_EXECUTABLE="$SCRIPT_DIRECTORY/AuditGuard"


clear

echo "===================================================================="
echo "MCP-AuditGuard"
echo "macOS Local Web Launcher"
echo "===================================================================="
echo


if [[ ! -f "$AUDITGUARD_EXECUTABLE" ]]; then
    echo "[실행 실패] AuditGuard 실행파일을 찾지 못했습니다."
    echo
    echo "예상 경로:"
    echo "$AUDITGUARD_EXECUTABLE"
    echo
    echo "AuditGuard.command와 AuditGuard 실행파일을"
    echo "같은 배포 폴더에 두어야 합니다."
    echo

    read -r "?종료하려면 Enter 키를 누르세요."
    exit 1
fi


if [[ ! -x "$AUDITGUARD_EXECUTABLE" ]]; then
    echo "[실행 실패] AuditGuard 파일에 실행 권한이 없습니다."
    echo
    echo "Terminal에서 다음 명령을 실행하세요:"
    echo
    printf 'chmod +x "%s"\n' "$AUDITGUARD_EXECUTABLE"
    echo

    read -r "?종료하려면 Enter 키를 누르세요."
    exit 1
fi


# 실행 위치가 Finder, 바탕화면, 다운로드 폴더 등 어디이든
# AuditGuard 배포 폴더를 현재 작업 디렉터리로 사용한다.
cd -- "$SCRIPT_DIRECTORY"


"$AUDITGUARD_EXECUTABLE"
EXIT_CODE=$?


echo
echo "===================================================================="

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "MCP-AuditGuard가 종료되었습니다."
else
    echo "MCP-AuditGuard가 오류와 함께 종료되었습니다."
    echo "종료 코드: $EXIT_CODE"
fi

echo "===================================================================="
echo


read -r "?Terminal 창을 닫으려면 Enter 키를 누르세요."

exit "$EXIT_CODE"