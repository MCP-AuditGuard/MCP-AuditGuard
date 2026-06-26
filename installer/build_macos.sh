#!/bin/bash

set -euo pipefail


APPLICATION_NAME="MCP-AuditGuard"
MODEL_REPOSITORY="BAAI/bge-small-en-v1.5"

SCRIPT_DIRECTORY="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
    pwd
)"

PROJECT_ROOT="$(
    cd -- "$SCRIPT_DIRECTORY/.."
    pwd
)"

VENV_DIRECTORY="$PROJECT_ROOT/.venv-build"
VENV_PYTHON="$VENV_DIRECTORY/bin/python"
HF_EXECUTABLE="$VENV_DIRECTORY/bin/hf"

MODEL_DIRECTORY="$PROJECT_ROOT/models/embedding/bge-small-en-v1.5"
MACOS_SPEC="$SCRIPT_DIRECTORY/auditguard_macos.spec"

BUILD_DIRECTORY="$PROJECT_ROOT/build"
DIST_DIRECTORY="$PROJECT_ROOT/dist"

AUDITGUARD_EXECUTABLE="$DIST_DIRECTORY/AuditGuard/AuditGuard"
AUDITGUARD_COMMAND="$DIST_DIRECTORY/AuditGuard/AuditGuard.command"
INTERNAL_DIRECTORY="$DIST_DIRECTORY/AuditGuard/_internal"


write_step() {
    printf '\n'
    printf '%s\n' \
        '===================================================================='
    printf '%s\n' "$1"
    printf '%s\n' \
        '===================================================================='
}


fail() {
    printf '\n'
    printf '%s\n' \
        '===================================================================='
    printf '%s\n' '[빌드 실패]'
    printf '%s\n' \
        '===================================================================='
    printf '%s\n' "$1"
    printf '\n'

    exit 1
}


model_is_ready() {
    local config_path
    local safetensor_path
    local pytorch_weight_path

    config_path="$MODEL_DIRECTORY/config.json"
    safetensor_path="$MODEL_DIRECTORY/model.safetensors"
    pytorch_weight_path="$MODEL_DIRECTORY/pytorch_model.bin"

    [[ -f "$config_path" ]] \
        && (
            [[ -f "$safetensor_path" ]] \
            || [[ -f "$pytorch_weight_path" ]]
        )
}


resolve_base_python() {
    local configured_python

    configured_python="${AUDITGUARD_PYTHON:-python3}"

    if ! command -v "$configured_python" >/dev/null 2>&1; then
        fail \
            "Python을 찾을 수 없습니다: $configured_python
Python 3.11 이상을 설치하거나 AUDITGUARD_PYTHON에
Python 실행파일 경로를 지정하세요."
    fi

    if ! "$configured_python" -c \
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
    then
        fail "Python 3.11 이상이 필요합니다."
    fi

    printf '%s\n' "$configured_python"
}


if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "build_macos.sh는 macOS에서만 실행할 수 있습니다."
fi


if [[ ! -f "$MACOS_SPEC" ]]; then
    fail "macOS spec 파일을 찾을 수 없습니다: $MACOS_SPEC"
fi


ORIGINAL_DIRECTORY="$(pwd)"

cleanup_location() {
    cd -- "$ORIGINAL_DIRECTORY"
}

trap cleanup_location EXIT

cd -- "$PROJECT_ROOT"


printf '%s\n' \
    '===================================================================='
printf '%s\n' "$APPLICATION_NAME"
printf '%s\n' 'macOS Build'
printf '%s\n' \
    '===================================================================='
printf '프로젝트: %s\n' "$PROJECT_ROOT"


write_step "1/8 Python과 빌드 가상환경을 준비합니다."

if [[ "${AUDITGUARD_RECREATE_VENV:-0}" == "1" ]] \
    && [[ -d "$VENV_DIRECTORY" ]]
then
    printf '기존 빌드 가상환경을 삭제합니다: %s\n' \
        "$VENV_DIRECTORY"

    rm -rf -- "$VENV_DIRECTORY"
fi


if [[ ! -x "$VENV_PYTHON" ]]; then
    BASE_PYTHON="$(resolve_base_python)"
    BASE_PYTHON_VERSION="$(
        "$BASE_PYTHON" -c \
            'import sys; print(sys.version.split()[0])'
    )"

    printf '사용할 Python: %s\n' "$BASE_PYTHON"
    printf 'Python 버전: %s\n' "$BASE_PYTHON_VERSION"
    printf '빌드 가상환경을 생성합니다: %s\n' \
        "$VENV_DIRECTORY"

    "$BASE_PYTHON" -m venv "$VENV_DIRECTORY"
else
    printf '기존 빌드 가상환경을 사용합니다: %s\n' \
        "$VENV_DIRECTORY"
fi


VENV_PYTHON_VERSION="$(
    "$VENV_PYTHON" -c \
        'import sys; print(sys.version.split()[0])'
)"

printf '빌드 Python 버전: %s\n' \
    "$VENV_PYTHON_VERSION"

printf '빌드 Python 아키텍처: %s\n' \
    "$(
        "$VENV_PYTHON" -c \
            'import platform; print(platform.machine())'
    )"


write_step "2/8 pip와 프로젝트 빌드 의존성을 설치합니다."

"$VENV_PYTHON" -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel

"$VENV_PYTHON" -m pip install \
    '.[dev,semantic,build]'


write_step "3/8 Semantic 모델을 준비합니다."

if [[ "${AUDITGUARD_FORCE_MODEL_DOWNLOAD:-0}" == "1" ]] \
    || ! model_is_ready
then
    if [[ ! -x "$HF_EXECUTABLE" ]]; then
        fail \
            "Hugging Face CLI를 찾을 수 없습니다: $HF_EXECUTABLE"
    fi

    mkdir -p -- "$MODEL_DIRECTORY"

    DOWNLOAD_ARGUMENTS=(
        download
        "$MODEL_REPOSITORY"
        --local-dir
        "$MODEL_DIRECTORY"
    )

    if [[ -n "${AUDITGUARD_MODEL_REVISION:-}" ]]; then
        DOWNLOAD_ARGUMENTS+=(
            --revision
            "$AUDITGUARD_MODEL_REVISION"
        )

        printf '고정 revision: %s\n' \
            "$AUDITGUARD_MODEL_REVISION"
    else
        printf '%s\n' \
            'AUDITGUARD_MODEL_REVISION이 없으므로 모델 저장소의 기본 revision을 사용합니다.'
    fi

    "$HF_EXECUTABLE" "${DOWNLOAD_ARGUMENTS[@]}"
else
    printf '기존 Semantic 모델을 사용합니다: %s\n' \
        "$MODEL_DIRECTORY"
fi


if ! model_is_ready; then
    fail \
        "Semantic 모델 다운로드 후 필수 파일을 찾지 못했습니다: $MODEL_DIRECTORY"
fi


write_step "4/8 Semantic Runtime Preflight를 실행합니다."

"$VENV_PYTHON" - <<'PY'
from core.runtime_preflight import run_runtime_preflight

result = run_runtime_preflight()

print(f"ready: {result.semantic_ready}")
print(f"provider: {result.provider_name}")
print(f"model: {result.model_path}")
print(f"dimension: {result.embedding_dimension}")
print(f"error: {result.error_code}")
print(f"message: {result.error_message}")

raise SystemExit(0 if result.semantic_ready else 1)
PY


write_step "5/8 빌드 관련 테스트를 실행합니다."

if [[ "${AUDITGUARD_SKIP_TESTS:-0}" == "1" ]]; then
    printf '%s\n' \
        '요청에 따라 테스트를 건너뜁니다.'
elif [[ "${AUDITGUARD_FULL_TESTS:-0}" == "1" ]]; then
    "$VENV_PYTHON" -m pytest -q
else
    "$VENV_PYTHON" -m pytest \
        -q \
        tests/unit/test_runtime_preflight.py
fi


write_step "6/8 이전 build와 dist를 정리합니다."

rm -rf -- \
    "$BUILD_DIRECTORY" \
    "$DIST_DIRECTORY"


write_step "7/8 PyInstaller macOS onedir 빌드를 실행합니다."

# Git에서 실행 권한이 보존되지 않은 경우에도
# spec이 최종 배포 폴더로 복사할 수 있도록 원본 권한을 보정한다.
chmod +x \
    "$SCRIPT_DIRECTORY/AuditGuard.command"

"$VENV_PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    "$MACOS_SPEC"


write_step "8/8 최종 macOS 빌드 결과를 확인합니다."

REQUIRED_BUILD_PATHS=(
    "$AUDITGUARD_EXECUTABLE"
    "$AUDITGUARD_COMMAND"
    "$INTERNAL_DIRECTORY/web/templates/index.html"
    "$INTERNAL_DIRECTORY/web/static/app.js"
    "$INTERNAL_DIRECTORY/rules"
    "$INTERNAL_DIRECTORY/models/embedding/bge-small-en-v1.5/config.json"
)

for required_path in "${REQUIRED_BUILD_PATHS[@]}"; do
    if [[ ! -e "$required_path" ]]; then
        fail \
            "최종 빌드에서 필수 파일을 찾지 못했습니다: $required_path"
    fi

    printf '[확인] %s\n' "$required_path"
done


if [[ ! -x "$AUDITGUARD_EXECUTABLE" ]]; then
    fail \
        "최종 AuditGuard 실행파일에 실행 권한이 없습니다: $AUDITGUARD_EXECUTABLE"
fi


if [[ ! -x "$AUDITGUARD_COMMAND" ]]; then
    fail \
        "최종 AuditGuard.command에 실행 권한이 없습니다: $AUDITGUARD_COMMAND"
fi


printf '\n'
file "$AUDITGUARD_EXECUTABLE"

printf '\n'
printf '%s\n' \
    '===================================================================='
printf '%s\n' 'macOS 빌드가 완료되었습니다.'
printf '%s\n' 'Finder 더블클릭 실행 파일:'
printf '%s\n' "$AUDITGUARD_COMMAND"
printf '%s\n' \
    '===================================================================='
