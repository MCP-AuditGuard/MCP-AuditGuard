from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path


# web/sample_catalog.py
# parents[0] = web
# parents[1] = 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[1]
VULNERABLE_LAB_ROOT = PROJECT_ROOT / "vulnerable-lab"


class SampleCatalogError(Exception):
    """샘플 카탈로그 처리 중 발생하는 기본 예외."""


class SampleJsonNotFoundError(SampleCatalogError):
    """샘플 폴더에 사용할 수 있는 JSON 파일이 없을 때 발생."""


class SampleJsonAmbiguousError(SampleCatalogError):
    """
    샘플 폴더 안에 JSON 파일이 여러 개라서
    자동으로 하나를 선택할 수 없을 때 발생.
    """

    def __init__(
        self,
        sample_id: str,
        file_names: tuple[str, ...],
    ) -> None:
        self.sample_id = sample_id
        self.file_names = file_names

        joined_names = ", ".join(file_names)

        super().__init__(
            f"Sample '{sample_id}' contains multiple JSON files: "
            f"{joined_names}"
        )


@dataclass(frozen=True, slots=True)
class SampleDefinition:
    """
    vulnerable-lab의 폴더 하나를 나타내는 내부 모델.

    지금은 id와 title만 API에 공개하지만,
    나중에 description, category, tags 등을 추가할 수 있다.
    """

    id: str
    title: str
    directory: Path
    json_files: tuple[Path, ...]


def discover_samples(
    root: Path | None = None,
) -> list[SampleDefinition]:
    """
    vulnerable-lab 아래의 샘플 폴더들을 자동으로 탐색한다.

    탐색 조건:
    - vulnerable-lab 아래 모든 하위 디렉터리 검사
    - 숨김 폴더는 제외
    - tools*.json 파일이 하나 이상 있는 폴더만 샘플로 등록

    예:
    - vulnerable-lab/01-hidden-description/tools.json
    - vulnerable-lab/expanded-52/LAB-001-plain-env-secret/tools.json
    """
    lab_root = (root or VULNERABLE_LAB_ROOT).resolve()

    if not lab_root.is_dir():
        return []

    samples: list[SampleDefinition] = []

    directories = _discover_sample_directories(lab_root)

    for directory in directories:
        json_files = _find_tools_json_files(directory)

        # JSON 입력 파일이 없는 폴더는 샘플 목록에서 제외한다.
        if not json_files:
            continue

        samples.append(
            SampleDefinition(
                id=_build_sample_id(
                    lab_root,
                    directory,
                ),
                title=_build_title(directory.name),
                directory=directory.resolve(),
                json_files=json_files,
            )
        )

    return samples


def get_sample_definition(
    sample_id: str,
) -> SampleDefinition | None:
    """
    현재 파일 시스템을 다시 탐색한 뒤,
    sample_id와 같은 상대 경로 id를 가진 샘플을 반환한다.
    """
    return next(
        (
            sample
            for sample in discover_samples()
            if sample.id == sample_id
        ),
        None,
    )


def resolve_sample_json(
    sample: SampleDefinition,
    *,
    requested_file: str | None = None,
) -> Path:
    """
    샘플 폴더에서 실제 검사할 JSON 파일을 결정한다.

    결정 규칙:
    1. requested_file이 있으면 정확히 해당 파일 사용
    2. tools.json이 있으면 tools.json 사용
    3. JSON 파일이 하나뿐이면 그 파일 사용
    4. 여러 개면 자동 선택하지 않고 오류
    """
    files_by_name = {
        path.name: path
        for path in sample.json_files
    }

    if requested_file is not None:
        selected_path = files_by_name.get(requested_file)

        if selected_path is None:
            raise SampleJsonNotFoundError(
                f"JSON file '{requested_file}' was not found "
                f"in sample '{sample.id}'."
            )

        return selected_path

    default_path = files_by_name.get("tools.json")

    if default_path is not None:
        return default_path

    if len(sample.json_files) == 1:
        return sample.json_files[0]

    if not sample.json_files:
        raise SampleJsonNotFoundError(
            f"No JSON file was found in sample '{sample.id}'."
        )

    raise SampleJsonAmbiguousError(
        sample_id=sample.id,
        file_names=tuple(
            path.name
            for path in sample.json_files
        ),
    )


def _discover_sample_directories(
    lab_root: Path,
) -> list[Path]:
    directories = {
        path.parent.resolve()
        for path in lab_root.rglob("tools*.json")
        if path.is_file()
        and not _has_hidden_part(path.relative_to(lab_root))
    }

    return sorted(
        directories,
        key=lambda path: _build_sample_id(
            lab_root,
            path,
        ).casefold(),
    )


def _find_tools_json_files(
    directory: Path,
) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path.resolve()
                for path in directory.glob("tools*.json")
                if path.is_file()
            ),
            key=lambda path: path.name.casefold(),
        )
    )


def _build_sample_id(
    lab_root: Path,
    directory: Path,
) -> str:
    return directory.relative_to(lab_root).as_posix()


def _has_hidden_part(
    path: Path,
) -> bool:
    return any(
        part.startswith(".")
        for part in path.parts
    )


def _build_title(folder_name: str) -> str:
    """
    폴더 이름에서 화면용 title을 만든다.

    예:
    01-hidden-description
        → Hidden Description

    05-metadata-rug-pull
        → Metadata Rug Pull

    07_새로운_샘플
        → 새로운 샘플
    """
    without_lab_prefix = re.sub(
        r"^lab[\s._-]*\d+[\s._-]*",
        "",
        folder_name,
        flags=re.IGNORECASE,
    )

    without_number_prefix = re.sub(
        r"^\d+[\s._-]*",
        "",
        without_lab_prefix,
    )

    normalized = re.sub(
        r"[-_]+",
        " ",
        without_number_prefix,
    ).strip()

    if not normalized:
        return folder_name

    return normalized.title()
