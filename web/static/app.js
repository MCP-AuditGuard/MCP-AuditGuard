"use strict";


const elements = {
    toolsFile: document.getElementById("tools-file"),
    sampleSelect: document.getElementById("sample-select"),
    scanButton: document.getElementById("scan-button"),

    statusIndicator: document.getElementById("status-indicator"),
    statusMessage: document.getElementById("status-message"),

    toolCount: document.getElementById("tool-count"),
    findingCount: document.getElementById("finding-count"),
    affectedTargetCount: document.getElementById(
        "affected-target-count"
    ),

    criticalCount: document.getElementById("critical-count"),
    highCount: document.getElementById("high-count"),
    mediumCount: document.getElementById("medium-count"),
    lowCount: document.getElementById("low-count"),
    infoCount: document.getElementById("info-count"),

    findingsEmpty: document.getElementById("findings-empty"),
    findingsTableContainer: document.getElementById(
        "findings-table-container"
    ),
    findingsTableBody: document.getElementById(
        "findings-table-body"
    ),

    findingDetailEmpty: document.getElementById(
        "finding-detail-empty"
    ),
    findingDetail: document.getElementById("finding-detail"),

    markdownDownload: document.getElementById(
        "markdown-download"
    ),
    jsonDownload: document.getElementById(
        "json-download"
    ),
};


document.addEventListener(
    "DOMContentLoaded",
    initializePage
);


async function initializePage() {
    bindEvents();
    resetResultView();
    await loadSamples();
}


function bindEvents() {
    elements.toolsFile.addEventListener(
        "change",
        handleFileSelection
    );

    elements.sampleSelect.addEventListener(
        "change",
        handleSampleSelection
    );

    elements.scanButton.addEventListener(
        "click",
        handleScan
    );
}


function handleFileSelection() {
    const selectedFile = elements.toolsFile.files[0];

    if (selectedFile) {
        // 파일을 선택하면 샘플 선택을 해제한다.
        elements.sampleSelect.value = "";

        setStatus(
            "idle",
            `선택된 파일: ${selectedFile.name}`
        );
    }
}


function handleSampleSelection() {
    const sampleId = elements.sampleSelect.value;

    if (sampleId) {
        // 샘플을 선택하면 업로드 파일 선택을 해제한다.
        elements.toolsFile.value = "";

        const selectedOption =
            elements.sampleSelect.selectedOptions[0];

        setStatus(
            "idle",
            `선택된 샘플: ${selectedOption.textContent}`
        );
    }
}


async function loadSamples() {
    setStatus(
        "loading",
        "실습 샘플 목록을 불러오는 중입니다."
    );

    try {
        const response = await fetch("/api/samples");

        const samples = await readApiResponse(response);

        renderSampleOptions(samples);

        setStatus(
            "idle",
            "검사할 파일이나 샘플을 선택하세요."
        );
    } catch (error) {
        setStatus(
            "error",
            `샘플 목록을 불러오지 못했습니다: ${error.message}`
        );
    }
}


function renderSampleOptions(samples) {
    // 기존 기본 option을 제외한 나머지를 제거한다.
    elements.sampleSelect.replaceChildren();

    const defaultOption = document.createElement("option");

    defaultOption.value = "";
    defaultOption.textContent = "샘플을 선택하세요";

    elements.sampleSelect.appendChild(defaultOption);

    for (const sample of samples) {
        const option = document.createElement("option");

        option.value = sample.id;
        option.textContent = sample.title;

        elements.sampleSelect.appendChild(option);
    }
}


async function handleScan() {
    const selectedFile = elements.toolsFile.files[0];
    const selectedSampleId = elements.sampleSelect.value;

    if (!selectedFile && !selectedSampleId) {
        setStatus(
            "error",
            "tools.json 파일 또는 실습 샘플을 선택하세요."
        );

        return;
    }

    setScanningState(true);

    try {
        let result;

        if (selectedFile) {
            result = await scanUploadedFile(selectedFile);
        } else {
            result = await scanSample(selectedSampleId);
        }

        renderScanResult(result);

        setStatus(
            "success",
            `검사가 완료되었습니다. ` +
            `${result.summary.finding_count}개의 Finding이 탐지되었습니다.`
        );
    } catch (error) {
        setStatus(
            "error",
            `검사에 실패했습니다: ${error.message}`
        );
    } finally {
        setScanningState(false);
    }
}


async function scanUploadedFile(file) {
    const formData = new FormData();

    // FastAPI endpoint의 UploadFile 매개변수 이름이 file이므로
    // 여기에서도 "file"이라는 이름으로 전달한다.
    formData.append("file", file);

    const response = await fetch(
        "/api/scans/upload",
        {
            method: "POST",
            body: formData,
        }
    );

    return readApiResponse(response);
}


async function scanSample(sampleId) {
    const encodedSampleId =
        encodeURIComponent(sampleId);

    const response = await fetch(
        `/api/scans/sample/${encodedSampleId}`,
        {
            method: "POST",
        }
    );

    return readApiResponse(response);
}


async function readApiResponse(response) {
    let body = null;

    try {
        body = await response.json();
    } catch {
        body = null;
    }

    if (response.ok) {
        return body;
    }

    throw new Error(
        extractErrorMessage(
            body,
            response.status
        )
    );
}


function extractErrorMessage(body, statusCode) {
    if (!body) {
        return `서버 오류가 발생했습니다. HTTP ${statusCode}`;
    }

    if (typeof body.detail === "string") {
        return body.detail;
    }

    if (body.detail && typeof body.detail === "object") {
        const detail = body.detail;

        if (
            detail.message &&
            Array.isArray(detail.available_files)
        ) {
            return (
                `${detail.message} ` +
                `사용 가능한 파일: ` +
                `${detail.available_files.join(", ")}`
            );
        }

        return JSON.stringify(detail);
    }

    if (typeof body.error === "string") {
        return body.error;
    }

    return `요청에 실패했습니다. HTTP ${statusCode}`;
}


function renderScanResult(result) {
    renderSummary(result.summary);
    renderFindings(result.findings ?? []);
    configureDownloadLinks(result.downloads);
}


function renderSummary(summary) {
    const severity = summary.by_severity;

    elements.toolCount.textContent =
        summary.tool_count;

    elements.findingCount.textContent =
        summary.finding_count;

    elements.affectedTargetCount.textContent =
        summary.affected_target_count;

    elements.criticalCount.textContent =
        severity.critical;

    elements.highCount.textContent =
        severity.high;

    elements.mediumCount.textContent =
        severity.medium;

    elements.lowCount.textContent =
        severity.low;

    elements.infoCount.textContent =
        severity.info;
}


function renderFindings(findings) {
    elements.findingsTableBody.replaceChildren();

    clearFindingDetail();

    if (findings.length === 0) {
        elements.findingsEmpty.hidden = false;
        elements.findingsEmpty.textContent =
            "보안 Finding이 발견되지 않았습니다.";

        elements.findingsTableContainer.hidden = true;

        return;
    }

    elements.findingsEmpty.hidden = true;
    elements.findingsTableContainer.hidden = false;

    findings.forEach((finding, index) => {
        const row = createFindingRow(
            finding,
            index
        );

        elements.findingsTableBody.appendChild(row);
    });

    // 검사 직후 첫 번째 Finding을 상세 영역에 표시한다.
    renderFindingDetail(findings[0]);

    const firstRow =
        elements.findingsTableBody.querySelector("tr");

    if (firstRow) {
        firstRow.classList.add("selected-row");
    }
}


function createFindingRow(finding, index) {
    const row = document.createElement("tr");

    row.tabIndex = 0;
    row.dataset.index = String(index);

    appendSeverityCell(
        row,
        finding.severity
    );

    appendTextCell(
        row,
        finding.title
    );

    appendTextCell(
        row,
        finding.category
    );

    appendTextCell(
        row,
        finding.target
    );

    appendTextCell(
        row,
        finding.location
    );

    appendTextCell(
        row,
        finding.confidence
    );

    row.addEventListener(
        "click",
        () => selectFindingRow(row, finding)
    );

    row.addEventListener(
        "keydown",
        (event) => {
            if (
                event.key === "Enter" ||
                event.key === " "
            ) {
                event.preventDefault();
                selectFindingRow(row, finding);
            }
        }
    );

    return row;
}


function appendSeverityCell(row, severity) {
    const cell = document.createElement("td");
    const badge = document.createElement("span");

    badge.className =
        `severity-badge severity-badge-${severity}`;

    badge.textContent =
        String(severity).toUpperCase();

    cell.appendChild(badge);
    row.appendChild(cell);
}


function appendTextCell(row, value) {
    const cell = document.createElement("td");

    cell.textContent = value ?? "-";

    row.appendChild(cell);
}


function selectFindingRow(row, finding) {
    const rows =
        elements.findingsTableBody.querySelectorAll("tr");

    for (const currentRow of rows) {
        currentRow.classList.remove("selected-row");
    }

    row.classList.add("selected-row");

    renderFindingDetail(finding);
}


function renderFindingDetail(finding) {
    elements.findingDetail.replaceChildren();

    addDetailItem(
        "ID",
        finding.id
    );

    addDetailItem(
        "OWASP",
        finding.owasp
    );

    addDetailItem(
        "Severity",
        finding.severity
    );

    addDetailItem(
        "Confidence",
        finding.confidence
    );

    addDetailItem(
        "Title",
        finding.title
    );

    addDetailItem(
        "Category",
        finding.category
    );

    addDetailItem(
        "Target",
        finding.target
    );

    addDetailItem(
        "Location",
        finding.location
    );

    addDetailItem(
        "Evidence",
        finding.evidence,
        true
    );

    addDetailItem(
        "Recommendation",
        finding.recommendation,
        true
    );

    addDetailItem(
        "Redacted",
        finding.redacted ? "Yes" : "No"
    );

    addDetailItem(
        "Fingerprint",
        finding.fingerprint,
        true
    );

    elements.findingDetailEmpty.hidden = true;
    elements.findingDetail.hidden = false;
}


function addDetailItem(
    label,
    value,
    preserveWhitespace = false
) {
    const item = document.createElement("div");
    const labelElement = document.createElement("strong");
    const valueElement = document.createElement("div");

    item.className = "detail-item";
    labelElement.className = "detail-label";
    valueElement.className = "detail-value";

    if (preserveWhitespace) {
        valueElement.classList.add(
            "detail-value-preformatted"
        );
    }

    labelElement.textContent = label;
    valueElement.textContent = value ?? "-";

    item.appendChild(labelElement);
    item.appendChild(valueElement);

    elements.findingDetail.appendChild(item);
}


function configureDownloadLinks(downloads) {
    if (!downloads) {
        disableDownloadLink(
            elements.markdownDownload
        );

        disableDownloadLink(
            elements.jsonDownload
        );

        return;
    }

    enableDownloadLink(
        elements.markdownDownload,
        downloads.markdown
    );

    enableDownloadLink(
        elements.jsonDownload,
        downloads.json
    );
}


function enableDownloadLink(link, url) {
    link.href = url;
    link.classList.remove("disabled");
    link.setAttribute("aria-disabled", "false");
}


function disableDownloadLink(link) {
    link.href = "#";
    link.classList.add("disabled");
    link.setAttribute("aria-disabled", "true");
}


function setScanningState(isScanning) {
    elements.scanButton.disabled = isScanning;

    elements.toolsFile.disabled = isScanning;
    elements.sampleSelect.disabled = isScanning;

    elements.scanButton.textContent =
        isScanning ? "Scanning..." : "Scan";

    if (isScanning) {
        setStatus(
            "loading",
            "보안 검사를 실행하고 있습니다."
        );
    }
}


function setStatus(status, message) {
    elements.statusIndicator.className =
        `status-indicator status-${status}`;

    elements.statusMessage.textContent = message;
}


function clearFindingDetail() {
    elements.findingDetail.replaceChildren();
    elements.findingDetail.hidden = true;

    elements.findingDetailEmpty.hidden = false;
    elements.findingDetailEmpty.textContent =
        "선택된 Finding이 없습니다.";
}


function resetResultView() {
    elements.toolCount.textContent = "-";
    elements.findingCount.textContent = "-";
    elements.affectedTargetCount.textContent = "-";

    elements.criticalCount.textContent = "-";
    elements.highCount.textContent = "-";
    elements.mediumCount.textContent = "-";
    elements.lowCount.textContent = "-";
    elements.infoCount.textContent = "-";

    elements.findingsTableBody.replaceChildren();
    elements.findingsTableContainer.hidden = true;

    elements.findingsEmpty.hidden = false;
    elements.findingsEmpty.textContent =
        "아직 실행된 검사가 없습니다.";

    clearFindingDetail();

    disableDownloadLink(
        elements.markdownDownload
    );

    disableDownloadLink(
        elements.jsonDownload
    );
}