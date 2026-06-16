from __future__ import annotations

from fastapi import APIRouter

from web.sample_catalog import discover_samples
from web.schemas import SampleResponse


router = APIRouter(
    prefix="/api/samples",
    tags=["samples"],
)


@router.get(
    "",
    response_model=list[SampleResponse],
)
def list_samples() -> list[SampleResponse]:
    """
    vulnerable-lab 폴더를 탐색해서
    현재 사용 가능한 샘플 목록을 반환한다.
    """
    return [
        SampleResponse.from_definition(sample)
        for sample in discover_samples()
    ]