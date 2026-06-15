from __future__ import annotations

import shutil

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, HTTPException, UploadFile, status, Query

from core.scan_service import execute_scan
from web.schemas import ScanResponse
from web.sample_catalog import (
    SampleJsonAmbiguousError,
    SampleJsonNotFoundError,
    get_sample_definition,
    resolve_sample_json,
)
from reports.artifact_store import save_report_artifacts
from core.scan_result import ScanResult

router = APIRouter(
    prefix="/api/scans",
    tags=["scans"],
)


@router.post(
    "/upload",
    response_model=ScanResponse,
    status_code=status.HTTP_200_OK,
)
def scan_uploaded_tools_json(
    file: UploadFile = File(...),
) -> ScanResponse:
    """
    업로드된 tools.json을 정적으로 검사한다.

    처리 흐름:
    1. 업로드 파일 기본 검증
    2. 임시 JSON 파일 저장
    3. execute_scan() 호출
    4. ScanResult를 ScanResponse로 변환
    5. 임시 파일 삭제
    """
    original_filename = file.filename or "uploaded-tools.json"

    if not original_filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JSON files can be scanned.",
        )

    temp_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            suffix=".json",
            delete=False,
        ) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = Path(temp_file.name)

        result = execute_scan(
            input_path=temp_path,
            source_label=original_filename,
        )

        return _finalize_scan_response(result)

    finally:
        file.file.close()

        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.post(
    "/sample/{sample_id:path}",
    response_model=ScanResponse,
    status_code=status.HTTP_200_OK,
)
def scan_registered_sample(
    sample_id: str,
    json_file: str | None = Query(
        default=None,
        alias="file",
        description=(
            "폴더 안에 JSON 파일이 여러 개일 때 "
            "검사할 파일 이름"
        ),
    ),
) -> ScanResponse:
    """
    vulnerable-lab에서 자동 발견된 샘플을 검사한다.

    일반적인 폴더:
    POST /api/scans/sample/01-hidden-description

    중첩된 폴더:
    POST /api/scans/sample/expanded-52/LAB-001-plain-env-secret

    JSON 파일이 여러 개인 폴더:
    POST /api/scans/sample/05-metadata-rug-pull
         ?file=tools-before.json
    """
    sample = get_sample_definition(sample_id)

    if sample is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown sample: {sample_id}",
        )

    try:
        sample_path = resolve_sample_json(
            sample,
            requested_file=json_file,
        )

    except SampleJsonNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except SampleJsonAmbiguousError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "This sample contains multiple JSON files. "
                    "Specify the file query parameter."
                ),
                "sample_id": error.sample_id,
                "available_files": list(error.file_names),
            },
        ) from error

    result = execute_scan(
        input_path=sample_path,
        source_label=f"sample:{sample.id}/{sample_path.name}",
    )

    return _finalize_scan_response(result)         

def _finalize_scan_response(
    result: ScanResult,
) -> ScanResponse:
    save_report_artifacts(result)
    return ScanResponse.from_result(result)
