from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from core.models import Detector, Finding, ToolMetadata


FindingTransformer = Callable[[Finding], Finding]


@dataclass(frozen=True)
class ScanError:
    """
    Detector 실행 중 발생한 에러 정보를 담는 모델.

    왜 필요한가?
    - Detector 하나가 실패했다고 전체 스캔이 바로 죽으면 불편하다.
    - 어떤 detector가 어떤 tool을 검사하다 실패했는지 기록해야 디버깅하기 쉽다.
    - CLI나 report에서 "일부 detector 실행 실패"를 보여줄 수 있다.

    예:
        detector_id = "MCP03-HIDDEN-INSTRUCTION"
        target = "demo-server.search_file"
        message = "unexpected error..."
    """

    detector_id: str
    detector_category: str
    target: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    """
    Scanner 실행 결과 전체를 담는 모델.

    findings:
        Detector들이 발견한 보안 이슈 목록.

    errors:
        Detector 실행 중 발생한 에러 목록.

    왜 list[Finding]만 반환하지 않고 ScanResult도 만들었나?
    - 기본적으로 scanner.scan()은 list[Finding]을 반환하게 만들 것이다.
    - 하지만 CLI나 테스트에서는 에러 정보도 필요할 수 있다.
    - 그래서 scan_with_result()를 호출하면 findings + errors를 같이 받을 수 있게 한다.
    """

    findings: list[Finding] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """
        detector 실행 중 에러가 하나라도 있었는지 확인한다.
        """
        return len(self.errors) > 0

    @property
    def finding_count(self) -> int:
        """
        발견된 finding 개수.
        CLI summary나 테스트에서 쓰기 좋다.
        """
        return len(self.findings)

    @property
    def error_count(self) -> int:
        """
        detector 실행 실패 개수.
        CLI summary나 테스트에서 쓰기 좋다.
        """
        return len(self.errors)


class DetectorRegistry:
    """
    Detector들을 등록하고 관리하는 작은 저장소.

    Scanner에 detector list를 바로 넘겨도 되지만,
    Registry를 두면 다음 장점이 있다.

    1. detector 등록 코드를 한 곳에 모을 수 있다.
    2. detector id 중복을 막을 수 있다.
    3. 나중에 category별 필터링을 추가하기 쉽다.

    예:
        registry = DetectorRegistry()
        registry.register(HiddenInstructionDetector())
        registry.register(SchemaPoisoningDetector())

        scanner = Scanner(registry)
    """

    def __init__(self, detectors: Iterable[Detector] | None = None) -> None:
        self._detectors: list[Detector] = []

        if detectors is not None:
            self.register_many(detectors)

    def register(self, detector: Detector) -> None:
        """
        detector 1개를 등록한다.

        같은 id의 detector가 이미 등록되어 있으면 에러를 발생시킨다.
        이유:
        - 같은 id가 여러 개 있으면 report나 테스트에서 구분하기 어렵다.
        """
        detector_id = _get_detector_id(detector)

        if self.contains(detector_id):
            raise ValueError(f"detector already registered: {detector_id}")

        self._detectors.append(detector)

    def register_many(self, detectors: Iterable[Detector]) -> None:
        """
        detector 여러 개를 한 번에 등록한다.
        """
        for detector in detectors:
            self.register(detector)

    def contains(self, detector_id: str) -> bool:
        """
        특정 detector id가 이미 등록되어 있는지 확인한다.
        """
        return any(_get_detector_id(detector) == detector_id for detector in self._detectors)

    def get_all(self) -> list[Detector]:
        """
        등록된 detector 목록을 복사해서 반환한다.

        내부 list를 그대로 반환하지 않는 이유:
        - 외부에서 self._detectors를 직접 수정하지 못하게 하기 위해서.
        """
        return list(self._detectors)

    def __iter__(self) -> Iterator[Detector]:
        """
        for detector in registry 형태로 순회할 수 있게 한다.
        """
        return iter(self._detectors)

    def __len__(self) -> int:
        """
        len(registry)로 등록된 detector 개수를 확인할 수 있게 한다.
        """
        return len(self._detectors)


class Scanner:
    """
    ToolMetadata 목록에 Detector들을 실행하는 공통 스캐너.

    Scanner가 하는 일:
    - ToolMetadata 목록을 받는다.
    - 등록된 Detector들을 순서대로 실행한다.
    - Detector가 반환한 Finding들을 모은다.
    - Detector 실행 중 에러가 나면 ScanError로 기록한다.
    - 필요하면 finding_transformer를 통해 Finding 후처리를 한다.

    Scanner가 하지 않는 일:
    - tools.json 파일 읽기
    - MCP 서버 연결
    - hidden instruction 판단
    - base64 decoding
    - report 출력
    - baseline 저장

    즉, Scanner는 "실행 흐름 관리자"다.
    실제 탐지 판단은 각 Detector가 한다.
    """

    def __init__(
        self,
        detectors: Iterable[Detector] | DetectorRegistry | None = None,
        *,
        continue_on_error: bool = True,
        finding_transformer: FindingTransformer | None = None,
    ) -> None:
        """
        detectors:
            실행할 detector 목록 또는 DetectorRegistry.

        continue_on_error:
            True이면 detector 하나가 실패해도 다음 detector를 계속 실행한다.
            False이면 detector 실행 중 에러가 발생하는 순간 예외를 다시 던진다.

        finding_transformer:
            Finding 후처리 함수.
            지금은 없어도 된다.
            나중에 core/redaction.py가 생기면 여기 연결할 수 있다.

            예:
                scanner = Scanner(
                    detectors=[...],
                    finding_transformer=redact_finding,
                )
        """
        if isinstance(detectors, DetectorRegistry):
            self.registry = detectors
        else:
            self.registry = DetectorRegistry(detectors)

        self.continue_on_error = continue_on_error
        self.finding_transformer = finding_transformer

    def register(self, detector: Detector) -> None:
        """
        Scanner에 detector를 추가 등록한다.

        예:
            scanner = Scanner()
            scanner.register(HiddenInstructionDetector())
        """
        self.registry.register(detector)

    def scan(self, tools: Iterable[ToolMetadata]) -> list[Finding]:
        """
        가장 기본적인 스캔 함수.

        반환:
            list[Finding]

        왜 list[Finding]을 반환하게 했나?
        - 계획서의 완료 기준이 "Scanner returns a list of Finding objects"이다.
        - 2번, 3번, 5번 멤버가 가장 쉽게 사용할 수 있다.

        에러 정보까지 필요하면 scan_with_result()를 사용한다.
        """
        result = self.scan_with_result(tools)
        return result.findings

    def scan_with_result(self, tools: Iterable[ToolMetadata]) -> ScanResult:
        """
        Finding과 ScanError를 함께 반환하는 스캔 함수.

        CLI나 integration test에서는 이 함수를 쓰는 것이 좋다.
        예를 들어 detector 일부가 실패했는지 확인할 수 있다.
        """
        findings: list[Finding] = []
        errors: list[ScanError] = []

        for tool in tools:
            for detector in self.registry:
                try:
                    detector_findings = self._run_detector(detector, tool)
                except Exception as exc:
                    scan_error = self._build_scan_error(
                        detector=detector,
                        tool=tool,
                        exc=exc,
                    )

                    errors.append(scan_error)

                    if not self.continue_on_error:
                        raise

                    continue

                findings.extend(detector_findings)

        return ScanResult(
            findings=findings,
            errors=errors,
        )

    def _run_detector(
        self,
        detector: Detector,
        tool: ToolMetadata,
    ) -> list[Finding]:
        """
        detector 1개를 tool 1개에 대해 실행한다.

        여기서 Finding 후처리도 같이 한다.
        예:
            - secret redaction
            - evidence trimming
            - duplicated whitespace normalization

        지금은 finding_transformer가 없으면 그대로 반환한다.
        """
        detector_findings = detector.detect(tool)

        if detector_findings is None:
            raise TypeError(
                f"detector returned None. detector={_get_detector_id(detector)}"
            )

        transformed_findings: list[Finding] = []

        for finding in detector_findings:
            if not isinstance(finding, Finding):
                raise TypeError(
                    "detector must return list[Finding]. "
                    f"detector={_get_detector_id(detector)}, "
                    f"actual={type(finding).__name__}"
                )

            transformed_finding = self._transform_finding(finding)
            transformed_findings.append(transformed_finding)

        return transformed_findings

    def _transform_finding(self, finding: Finding) -> Finding:
        """
        Finding 후처리 지점.

        지금은 finding_transformer가 있으면 적용하고,
        없으면 finding을 그대로 반환한다.

        나중에 redaction.py를 만들면 이런 식으로 연결 가능하다.

        예:
            scanner = Scanner(
                detectors=[...],
                finding_transformer=redact_finding,
            )
        """
        if self.finding_transformer is None:
            return finding

        transformed = self.finding_transformer(finding)

        if not isinstance(transformed, Finding):
            raise TypeError(
                "finding_transformer must return Finding. "
                f"actual={type(transformed).__name__}"
            )

        return transformed

    def _build_scan_error(
        self,
        *,
        detector: Detector,
        tool: ToolMetadata,
        exc: Exception,
    ) -> ScanError:
        """
        detector 실행 중 발생한 예외를 ScanError로 변환한다.

        예외 객체를 그대로 밖으로 노출하지 않고,
        필요한 정보만 정리해서 담는다.
        """
        return ScanError(
            detector_id=_get_detector_id(detector),
            detector_category=_get_detector_category(detector),
            target=tool.target,
            message=str(exc),
        )


def _get_detector_id(detector: Detector) -> str:
    """
    detector id를 안전하게 가져온다.

    정상 detector라면 detector.id가 있어야 한다.
    그래도 혹시 누락되면 클래스명을 fallback으로 사용한다.
    """
    detector_id = getattr(detector, "id", None)

    if detector_id:
        return str(detector_id)

    return detector.__class__.__name__


def _get_detector_category(detector: Detector) -> str:
    """
    detector category를 안전하게 가져온다.

    정상 detector라면 detector.category가 있어야 한다.
    누락되면 unknown으로 처리한다.
    """
    detector_category = getattr(detector, "category", None)

    if detector_category:
        return str(detector_category)

    return "unknown"