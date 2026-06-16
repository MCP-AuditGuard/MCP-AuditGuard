from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from core.baseline_store import load_baseline, save_baseline
from core.diff_engine import diff_baseline
from core.exceptions import ScanServiceError
from core.scanner import scan_tools
from core.tool_collector import collect_from_tools_json
from detectors.registry import create_default_detectors
from reports.json_report import render_json
from reports.markdown_report import render_markdown
from core.models import Finding, ToolMetadata
from core.scan_result import ScanResult

SUPPORTED_FORMATS = {"markdown", "json"}

def execute_scan(
    *,
    input_path: Path,
    source_label: str | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> ScanResult:
    started_at = datetime.now(timezone.utc)

    tools = _collect_tools(input_path)
    findings = _scan_tools(tools)

    baseline_compared = baseline_path is not None

    if baseline_path is not None:
        old_baseline = _load_baseline(baseline_path)
        findings.extend(diff_baseline(old_baseline, tools))

    if save_baseline_path is not None:
        _save_baseline(tools, save_baseline_path)

    completed_at = datetime.now(timezone.utc)

    return ScanResult(
        scan_type="static",
        source_type="tools_json",
        source=source_label or str(input_path),
        started_at=started_at,
        completed_at=completed_at,
        tools=tools,
        findings=findings,
        baseline_compared=baseline_compared,
    )


def run_scan(
    *,
    input_path: Path,
    report_format: str,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> str:
    normalized_format = report_format.lower()

    if normalized_format not in SUPPORTED_FORMATS:
        raise ScanServiceError(
            "Unsupported format. Use 'markdown' or 'json'."
        )

    result = execute_scan(
        input_path=input_path,
        save_baseline_path=save_baseline_path,
        baseline_path=baseline_path,
    )

    return _render_report(result.findings,normalized_format,)


def _collect_tools(input_path: Path) -> list[ToolMetadata]:
    try:
        return collect_from_tools_json(input_path)
    except FileNotFoundError as error:
        raise ScanServiceError(f"Input file not found: {input_path}") from error
    except json.JSONDecodeError as error:
        raise ScanServiceError(f"Could not parse tools JSON: {error.msg}") from error
    except OSError as error:
        raise ScanServiceError(f"Could not read input file: {error}") from error
    except ValueError as error:
        raise ScanServiceError(str(error)) from error
    except Exception as error:
        if error.__class__.__name__ == "ToolCollectionError":
            message = str(error)
            if message.startswith("invalid JSON file"):
                raise ScanServiceError(f"Could not parse tools JSON: {message}") from error
            raise ScanServiceError(message) from error
        raise


def _scan_tools(tools: list[ToolMetadata]) -> list[Finding]:
    detectors = create_default_detectors()
    try:
        return scan_tools(tools, detectors)
    except Exception as error:
        raise ScanServiceError(f"Scanner failed: {error}") from error


def _load_baseline(baseline_path: Path) -> dict[str, Any]:
    try:
        return load_baseline(str(baseline_path))
    except FileNotFoundError as error:
        raise ScanServiceError(f"Baseline file not found: {baseline_path}") from error
    except json.JSONDecodeError as error:
        raise ScanServiceError(f"Could not parse baseline JSON: {error.msg}") from error
    except OSError as error:
        raise ScanServiceError(f"Could not read baseline file: {error}") from error


def _save_baseline(tools: list[ToolMetadata], baseline_path: Path) -> None:
    try:
        save_baseline(tools, str(baseline_path))
    except OSError as error:
        raise ScanServiceError(f"Could not save baseline: {error}") from error


def _render_report(findings: list[Finding], report_format: str) -> str:
    if report_format == "markdown":
        return render_markdown(findings)
    if report_format == "json":
        return render_json(findings)
    raise ScanServiceError("Unsupported format. Use 'markdown' or 'json'.")
