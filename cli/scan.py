from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import typer
from rich.console import Console

from core.baseline_store import load_baseline, save_baseline
from core.diff_engine import diff_baseline
from reports.json_report import render_json
from reports.markdown_report import render_markdown


app = typer.Typer(help="MCP-AuditGuard CLI")
console = Console()

SUPPORTED_FORMATS = {"markdown", "json"}


@app.callback()
def main() -> None:
    """MCP-AuditGuard command line interface."""


@app.command("scan")
def scan_command(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to tools.json.",
    ),
    report_format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Report format: markdown or json.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Optional path to write the report.",
    ),
    save_baseline_path: Path | None = typer.Option(
        None,
        "--save-baseline",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Optional path to save the current metadata baseline.",
    ),
    baseline_path: Path | None = typer.Option(
        None,
        "--baseline",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Optional previous baseline JSON path to compare against.",
    ),
) -> None:
    """Scan MCP tools metadata and render a report."""
    try:
        report = run_scan(
            input_path=input_path,
            report_format=report_format,
            output_path=output_path,
            save_baseline_path=save_baseline_path,
            baseline_path=baseline_path,
        )
    except UserFacingError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error

    if output_path is None:
        console.print(report)


def run_scan(
    *,
    input_path: Path,
    report_format: str,
    output_path: Path | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> str:
    normalized_format = report_format.lower()
    if normalized_format not in SUPPORTED_FORMATS:
        raise UserFacingError("Unsupported format. Use 'markdown' or 'json'.")

    tools = _collect_tools(input_path)
    findings = _scan_tools(tools)

    if baseline_path is not None:
        old_baseline = _load_baseline(baseline_path)
        findings.extend(diff_baseline(old_baseline, tools))

    if save_baseline_path is not None:
        _save_baseline(tools, save_baseline_path)

    report = _render_report(findings, normalized_format)

    if output_path is not None:
        _write_report(report, output_path)

    return report


def collect_from_tools_json(input_path: Path) -> list[Any]:
    """Collect ToolMetadata objects from tools.json.

    This wrapper keeps the CLI usable while the real collector module is still
    being implemented.
    """
    try:
        from core.tool_collector import collect_from_tools_json as real_collect
    except ModuleNotFoundError:
        return _fallback_collect_from_tools_json(input_path)

    return real_collect(input_path)


def scan_tools(tools: list[Any], detectors: list[Any]) -> list[Any]:
    """Run the scanner with an injectable detector list."""
    try:
        from core.scanner import scan_tools as real_scan_tools
    except ModuleNotFoundError:
        # TODO: Replace this fallback when detector registration is implemented.
        return []

    return real_scan_tools(tools, detectors)


def _collect_tools(input_path: Path) -> list[Any]:
    try:
        return collect_from_tools_json(input_path)
    except FileNotFoundError as error:
        raise UserFacingError(f"Input file not found: {input_path}") from error
    except json.JSONDecodeError as error:
        raise UserFacingError(f"Could not parse tools JSON: {error.msg}") from error
    except OSError as error:
        raise UserFacingError(f"Could not read input file: {error}") from error
    except ValueError as error:
        raise UserFacingError(str(error)) from error
    except Exception as error:
        if error.__class__.__name__ == "ToolCollectionError":
            message = str(error)
            if message.startswith("invalid JSON file"):
                raise UserFacingError(f"Could not parse tools JSON: {message}") from error
            raise UserFacingError(message) from error
        raise


def _scan_tools(tools: list[Any]) -> list[Any]:
    detectors = _default_detectors()
    try:
        return scan_tools(tools, detectors)
    except Exception as error:
        raise UserFacingError(f"Scanner failed: {error}") from error


def _default_detectors() -> list[Any]:
    from detectors.obfuscation.encoded_payload import EncodedPayloadDetector
    from detectors.obfuscation.homoglyph import HomoglyphDetector
    from detectors.obfuscation.html_comment import HtmlCommentDetector
    from detectors.obfuscation.unicode_obfuscation import UnicodeObfuscationDetector
    from detectors.tool_poisoning.cross_tool_instruction import CrossToolInstructionDetector
    from detectors.tool_poisoning.hidden_instruction import HiddenInstructionDetector
    from detectors.tool_poisoning.markdown_hidden_link import MarkdownHiddenLinkDetector
    from detectors.tool_poisoning.metadata_poisoning import MetadataPoisoningDetector
    from detectors.tool_poisoning.schema_poisoning import SchemaPoisoningDetector

    return [
        HiddenInstructionDetector(),
        SchemaPoisoningDetector(),
        MetadataPoisoningDetector(),
        CrossToolInstructionDetector(),
        MarkdownHiddenLinkDetector(),
        UnicodeObfuscationDetector(),
        EncodedPayloadDetector(),
        HtmlCommentDetector(),
        HomoglyphDetector(),
    ]


def _load_baseline(baseline_path: Path) -> dict[str, Any]:
    try:
        return load_baseline(str(baseline_path))
    except FileNotFoundError as error:
        raise UserFacingError(f"Baseline file not found: {baseline_path}") from error
    except json.JSONDecodeError as error:
        raise UserFacingError(f"Could not parse baseline JSON: {error.msg}") from error
    except OSError as error:
        raise UserFacingError(f"Could not read baseline file: {error}") from error


def _save_baseline(tools: list[Any], baseline_path: Path) -> None:
    try:
        save_baseline(tools, str(baseline_path))
    except OSError as error:
        raise UserFacingError(f"Could not save baseline: {error}") from error


def _render_report(findings: list[Any], report_format: str) -> str:
    if report_format == "markdown":
        return render_markdown(findings)
    if report_format == "json":
        return render_json(findings)
    raise UserFacingError("Unsupported format. Use 'markdown' or 'json'.")


def _write_report(report: str, output_path: Path) -> None:
    try:
        output_path.write_text(report, encoding="utf-8")
    except OSError as error:
        raise UserFacingError(f"Could not write report: {error}") from error


def _fallback_collect_from_tools_json(input_path: Path) -> list[Any]:
    raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(raw_data, dict):
        raw_tools = raw_data.get("tools", [])
    elif isinstance(raw_data, list):
        raw_tools = raw_data
    else:
        raise ValueError("tools.json must contain a list or an object with a tools list.")

    if not isinstance(raw_tools, list):
        raise ValueError("tools.json field 'tools' must be a list.")

    return [_tool_from_dict(item) for item in raw_tools]


def _tool_from_dict(item: Any) -> SimpleNamespace:
    if not isinstance(item, dict):
        raise ValueError("Each tool entry must be a JSON object.")

    return SimpleNamespace(
        server_name=str(item.get("server_name", "")),
        tool_name=str(item.get("tool_name") or item.get("name", "")),
        description=item.get("description"),
        input_schema=item.get("input_schema") or item.get("inputSchema"),
        output_schema=item.get("output_schema") or item.get("outputSchema"),
        annotations=item.get("annotations"),
    )


class UserFacingError(Exception):
    """Error type for messages that can be shown directly to CLI users."""


if __name__ == "__main__":
    app()
