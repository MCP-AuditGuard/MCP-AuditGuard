from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from web.app import app


BASE_URL = "http://127.0.0.1"
VIEW_SECTION_IDS = {
    "view-dashboard",
    "view-scan-detail",
    "view-scan-start",
    "view-server-management",
    "view-baseline-history",
    "view-static-scan",
    "view-help",
}
SCAN_PHASE_SECTION_IDS = {
    "scan-setup-section",
    "scan-running-section",
}
STACKED_HTML_TAGS = {
    "main",
    "section",
    "div",
    "article",
    "aside",
    "header",
    "nav",
}


class _DashboardStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, str | None, str | None]] = []
        self.view_depths: dict[str, int] = {}
        self.element_parents: dict[str, str | None] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        data_view = attr_map.get("data-view")

        if element_id in VIEW_SECTION_IDS:
            self.view_depths[element_id] = self._current_view_depth()

        if element_id in SCAN_PHASE_SECTION_IDS:
            self.element_parents[element_id] = self._nearest_parent_id()

        if tag in STACKED_HTML_TAGS:
            self._stack.append((tag, element_id, data_view))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return

    def _current_view_depth(self) -> int:
        return sum(1 for _, _, data_view in self._stack if data_view)

    def _nearest_parent_id(self) -> str | None:
        for _, element_id, _ in reversed(self._stack):
            if element_id:
                return element_id
        return None


def test_dashboard_home_page_contains_agreed_view_structure() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text

    for expected_text in (
        "MCP-AuditGuard",
        "검사 결과",
        "검사 시작",
        "MCP 서버 관리",
        "기준선 이력",
        "파일·샘플 검사",
        "도움말",
        "AI 도구 안전검진",
        "안전",
        "주의",
        "위험",
        "확인이 필요한 항목",
    ):
        assert expected_text in html

    for forbidden_text in (
        "위험 맵",
        "안전하게 비활성화",
        "사용자 계정",
        "로그아웃",
        "연결됨",
        "현재 연결 중",
        "전체 검사 기록",
        "모든 과거 Scan 결과",
        "과거 모든 검사 결과",
        "Scan Complete",
        "검사 완료 결과",
        "검사 필요",
        "최근 검사 결과",
        "권장 조치",
        "Latest Scan",
        "Next Step",
    ):
        assert forbidden_text not in html

    for marker in (
        'class="app-sidebar"',
        'id="view-dashboard"',
        'data-view="dashboard"',
        'id="view-scan-detail"',
        'data-view="scan-detail"',
        'id="view-scan-start"',
        'data-view="scan-start"',
        'id="view-server-management"',
        'data-view="server-management"',
        'id="view-baseline-history"',
        'data-view="baseline-history"',
        'id="view-static-scan"',
        'data-view="static-scan"',
        'id="view-help"',
        'data-view="help"',
        'aria-current="page"',
    ):
        assert marker in html

    for marker in (
        'id="dashboard-status-banner"',
        'id="dashboard-safe-count"',
        'id="dashboard-warning-count"',
        'id="dashboard-danger-count"',
        'id="dashboard-attention-list"',
        'id="dashboard-attention-empty"',
        'id="scan-detail-back-button"',
        'id="scan-detail-title"',
        'id="scan-detail-risk-panel"',
        'id="scan-detail-meta"',
        'id="scan-detail-severity-summary"',
        'id="scan-detail-finding-list"',
        'id="scan-detail-finding-detail"',
    ):
        assert marker in html

    for removed_marker in (
        'id="dashboard-unscanned-count"',
        'id="dashboard-scan-results-list"',
        'id="dashboard-scan-results-empty"',
        'id="dashboard-retry-failed-button"',
        'id="dashboard-start-scan-view-button"',
        'class="dashboard-criteria"',
        'class="view-intro"',
        'id="scan-detail-process-status"',
        'id="scan-detail-process-summary"',
        'id="scan-detail-process-issues"',
    ):
        assert removed_marker not in html


def test_dashboard_view_sections_are_independent_and_scan_phase_is_nested() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/")

    assert response.status_code == 200

    parser = _DashboardStructureParser()
    parser.feed(response.text)

    assert parser.view_depths == {
        "view-dashboard": 0,
        "view-scan-detail": 0,
        "view-scan-start": 0,
        "view-server-management": 0,
        "view-baseline-history": 0,
        "view-static-scan": 0,
        "view-help": 0,
    }
    assert parser.element_parents == {
        "scan-setup-section": "view-scan-start",
        "scan-running-section": "view-scan-start",
    }


def test_scan_start_management_and_history_skeleton_markers_exist() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text

    for marker in (
        'id="scan-include-project-config"',
        'id="scan-refresh-servers-button"',
        'id="scan-select-all-button"',
        'id="scan-clear-selection-button"',
        'id="scan-server-list"',
        'id="scan-server-list-empty"',
        'id="scan-selected-count"',
        'id="scan-available-count"',
        'id="scan-selected-servers-button"',
        'id="scan-progress-panel"',
        'id="scan-progress-bar"',
        'id="scan-progress-current"',
        'id="scan-progress-total"',
        'id="scan-progress-label"',
        'id="scan-current-server-name"',
        'id="scan-progress-server-list"',
        'id="scan-server-status"',
        'id="scan-server-error"',
        'id="scan-setup-section"',
        'id="scan-running-section"',
    ):
        assert marker in html

    for removed_marker in (
        'id="scan-completed-section"',
        'id="scan-completed-list"',
        'id="scan-new-scan-button"',
        'id="scan-retry-failed-button"',
    ):
        assert removed_marker not in html

    for marker in (
        'id="server-management-status"',
        'id="server-management-error"',
        'id="server-management-list"',
        'id="server-management-list-empty"',
        'id="server-management-detail"',
        'id="server-management-detail-empty"',
        'id="server-last-scan-status"',
        'id="server-last-scan-at"',
        'id="server-baseline-lifecycle"',
        'id="server-comparison-status"',
        'id="server-verification-status"',
        'id="server-name"',
        'id="server-product"',
        'id="server-scope"',
        'id="server-transport"',
        'id="server-enabled-state"',
        'id="server-support-state"',
        'id="server-can-scan"',
        'id="server-command-basename"',
        'id="server-argument-count"',
        'id="server-env-reference-count"',
        'id="server-remote-origin"',
        'id="server-tls-verified"',
        'id="server-current-approved-id"',
        'id="server-pending-candidate-count"',
        'id="server-rejected-candidate-count"',
        'id="server-related-approved-target-count"',
        'id="server-state-version"',
        'id="server-revoke-baseline-button"',
        'id="baseline-revoke-panel"',
        'id="baseline-revoke-summary"',
        'id="baseline-revoke-reason-code"',
        'id="baseline-revoke-confirm-button"',
        'id="baseline-revoke-cancel-button"',
        'id="baseline-revoke-error"',
    ):
        assert marker in html

    for marker in (
        'id="candidate-review-section"',
        'id="candidate-list"',
        'id="candidate-list-empty"',
        'id="candidate-detail"',
        'id="candidate-detail-empty"',
        'id="candidate-review-status"',
        'id="candidate-review-error"',
        'id="candidate-basic-info"',
        'id="candidate-snapshot-summary"',
        'id="candidate-config-summary"',
        'id="candidate-comparison-summary"',
        'id="candidate-tool-diff"',
        'id="candidate-approve-button"',
        'id="candidate-reject-button"',
        'id="candidate-decision-panel"',
        'id="candidate-decision-summary"',
        'id="candidate-reason-code"',
        'pattern="[a-z0-9_]{1,64}"',
        'maxlength="64"',
        'placeholder="reviewed_change"',
        'id="candidate-decision-confirm-button"',
        'id="candidate-decision-cancel-button"',
    ):
        assert marker in html

    for expected_text in (
        "기본 정보",
        "검사·기준선 검토 상태",
        "연결 요약",
        "기준선 관계",
        "실행 프로그램 이름",
        "인자 개수",
        "환경변수 참조 개수",
        "원격 Origin",
        "TLS 검증 여부",
    ):
        assert expected_text in html

    for marker in (
        'id="baseline-history-status"',
        'id="baseline-history-error"',
        'id="baseline-history-server-list"',
        'id="baseline-history-server-list-empty"',
        'id="baseline-history-list"',
        'id="baseline-history-empty"',
        'id="baseline-history-delete-button"',
        'id="baseline-history-delete-confirm-panel"',
        'id="baseline-history-delete-confirm-button"',
        'id="baseline-history-delete-cancel-button"',
    ):
        assert marker in html

    assert "기준선 후보의 승인·거절과 승인 기준선 변경 기록을 확인합니다." in html
    assert "기준선 이력을 삭제할까요?" in html
    assert "서버를 선택하면 저장된 기준선 승인·거절·삭제 기록이 표시됩니다." in html

    for fixed_event_text in (
        "후보 기준선 생성",
        "후보 기준선 승인",
        "후보 기준선 거절",
        "기존 기준선 교체",
    ):
        assert fixed_event_text not in html


def test_static_scan_view_preserves_existing_dom_contract() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text

    for marker in (
        'id="static-scan-panel"',
        'id="tools-file"',
        'id="sample-select"',
        'id="scan-button"',
        'id="status-indicator"',
        'id="status-message"',
        'id="tool-count"',
        'id="finding-count"',
        'id="affected-target-count"',
        'id="critical-count"',
        'id="high-count"',
        'id="medium-count"',
        'id="low-count"',
        'id="info-count"',
        'id="findings-empty"',
        'id="findings-table-container"',
        'id="findings-table-body"',
        'id="finding-detail-empty"',
        'id="finding-detail"',
        'id="markdown-download"',
        'id="json-download"',
    ):
        assert marker in html


def test_dashboard_does_not_hardcode_fake_mcp_data_or_unsafe_detail() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text

    for forbidden_text in (
        "fake-selection-id",
        "fake_selection_id",
        "fake-candidate-id",
        "fake_candidate_id",
        "fake-baseline-id",
        "fake_baseline_id",
        "C:\\",
        "/Users/",
        "/home/",
        "cmd.exe",
        "powershell.exe",
        "전체 command",
        "전체 args",
        "절대 경로",
        "설정 파일 경로",
        "URL path",
        "URL query",
        "Header 값",
        "Token",
        "env 값",
        "onclick=",
    ):
        assert forbidden_text not in html


def test_dashboard_static_assets_and_health_route_are_available() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        css = client.get("/static/style.css")
        javascript = client.get("/static/app.js")
        health = client.get("/health")

    assert css.status_code == 200
    assert "--color-sidebar: #ffffff" in css.text
    assert "status-banner-unscanned" in css.text
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css.text
    assert "server-management-grid" in css.text
    assert "server-select-item" in css.text
    assert "attention-actions" in css.text
    assert "dashboard-criteria" not in css.text
    assert "scan-detail-view" in css.text
    assert "scan-detail-severity-summary" in css.text
    assert "scan-detail-severity-critical" in css.text
    assert "scan-detail-severity-info" not in css.text
    assert "scan-detail-process-panel" not in css.text
    assert "scan-detail-process-issue-list" not in css.text
    assert "scan-detail-finding-list" in css.text
    assert "scan-detail-definition-list" in css.text
    assert "max-height: min(64vh, 620px)" in css.text
    assert "max-height: min(68vh, 720px)" in css.text
    assert "server-detail-sections::-webkit-scrollbar" in css.text
    assert "overscroll-behavior: contain" in css.text
    assert "status-badge-progress-scanning" in css.text
    assert "history-record" in css.text
    assert "baseline-history-note" in css.text
    assert "baseline-server-header" in css.text
    assert "server-identity-row" in css.text
    assert "baseline-server-identity" in css.text
    assert "baseline-history-availability" in css.text
    assert "baseline-history-delete-button" in css.text
    assert "baseline-history-delete-confirm-panel" in css.text
    assert "baseline-history-delete-confirm-actions" in css.text
    assert "history-record-toggle" in css.text
    assert "history-record-time" in css.text
    assert "candidate-review-section" in css.text
    assert "candidate-list-item" in css.text
    assert "candidate-decision-panel" in css.text
    assert "tool-diff-list" in css.text
    assert "field-diff-grid" in css.text
    assert "scan-result-card" in css.text
    assert "baseline-revoke-panel" in css.text
    assert "baseline-revoke-button" in css.text
    assert ".primary-button.candidate-decision-danger" in css.text
    assert javascript.status_code == 200
    assert "const uiState" in javascript.text
    assert 'activeView: "dashboard"' in javascript.text
    assert "const mcpUiState" in javascript.text
    assert "const dashboardState" in javascript.text
    assert "bannerToneByStatus" in javascript.text
    assert "/api/security/request-token" in javascript.text
    assert "/api/mcp/servers" in javascript.text
    assert "/scan" in javascript.text
    assert "apiFetch" in javascript.text
    assert "ensureRequestToken" in javascript.text
    assert "refreshRequestToken" in javascript.text
    assert "getSecureRequestHeaders" in javascript.text
    assert "normalizeServerListResponse" in javascript.text
    assert "normalizeServerItem" in javascript.text
    assert "classifyServerStatus" in javascript.text
    assert "hasPersistedMonitoringState" in javascript.text
    assert "isMonitoringNotFoundError" in javascript.text
    assert "runSelectedServerScans" in javascript.text
    assert "phase: \"setup\"" in javascript.text
    assert "completedItems" in javascript.text
    assert "getDashboardResultServers" in javascript.text
    assert "normalizeDashboardStatus" in javascript.text
    assert "reconcileScanResultCacheWithCatalog" in javascript.text
    assert "clearCachedScanResultForSelection" in javascript.text
    assert "createScanResultAttentionModel" in javascript.text
    assert "isCandidateLinkedToCurrentScanResult" in javascript.text
    assert "buildCompletedScanItems" in javascript.text
    assert "classifyCompletedScanResult" in javascript.text
    assert "resetScanBatchForNewScan" in javascript.text
    assert "scanDetail" in javascript.text
    assert "scanDetailSeveritySummary" in javascript.text
    assert "renderScanDetail" in javascript.text
    assert "renderScanDetailSeveritySummary" in javascript.text
    assert "classifySecurityFindingStatus" in javascript.text
    assert "scanDetailProcessStatus" not in javascript.text
    assert "renderScanDetailProcess" not in javascript.text
    assert "getScanProcessSummary" not in javascript.text
    assert "tool_activation_unknown" not in javascript.text
    assert "검사 완료, 경고 있음" not in javascript.text
    assert "검사 경고" not in javascript.text
    assert "openScanDetailFromAttention" in javascript.text
    assert "openScanDetailFromResult" in javascript.text
    assert "closeScanDetail" in javascript.text
    assert "식별자" in javascript.text
    assert "위험도" in javascript.text
    assert "신뢰도" in javascript.text
    assert "displayFindingSeverity" not in javascript.text
    assert "displayFindingConfidence" not in javascript.text
    assert "openServerDetailFromAttention" not in javascript.text
    assert "focusServerManagementDetail" not in javascript.text
    assert "openCandidateReviewFromResult" in javascript.text
    assert "candidateReview" in javascript.text
    assert "renderCandidateReview" in javascript.text
    assert "loadCandidateDetail" in javascript.text
    assert "renderCandidateToolDiff" in javascript.text
    assert "submitCandidateDecision" in javascript.text
    assert "fetchLatestTargetStateForCandidateDecision" in javascript.text
    assert "refreshAfterCandidateDecision" in javascript.text
    assert "baselineRevoke" in javascript.text
    assert "startBaselineRevocation" in javascript.text
    assert "submitBaselineRevocation" in javascript.text
    assert "fetchLatestTargetStateForBaselineRevocation" in javascript.text
    assert "refreshAfterBaselineRevocation" in javascript.text
    assert "appendLabeledMetaText(meta, \"제품\"" in javascript.text
    assert "appendLabeledMetaText(meta, \"범위\"" in javascript.text
    assert "appendLabeledMetaText(identity, \"제품\"" in javascript.text
    assert "appendLabeledMetaText(identity, \"범위\"" in javascript.text
    assert "createBaselineHistoryAvailabilityBadge" in javascript.text
    assert "getBaselineHistoryCountForServer" in javascript.text
    assert "startBaselineHistoryDeletionConfirmation" in javascript.text
    assert "clearBaselineHistoryDeletionConfirmation" in javascript.text
    assert "deleteSelectedBaselineHistory" in javascript.text
    assert "refreshAfterBaselineHistoryDeletion" in javascript.text
    assert "applyHistoryDeletionResultToServer" in javascript.text
    assert "method: \"DELETE\"" in javascript.text
    assert "historyIds" in javascript.text
    assert "이력 있음" in javascript.text
    assert "이력 없음" in javascript.text
    assert "installCompactBaselineHistoryStyles" not in javascript.text
    assert "저장된 상태 있음" not in javascript.text
    assert "아직 이력 없음" not in javascript.text
    assert "showView" in javascript.text
    assert "updateActiveNavigation" in javascript.text
    assert "updateWorkspaceTitle" in javascript.text
    assert "renderDashboardSummary" in javascript.text
    assert "renderAttentionItems" in javascript.text
    assert "renderDashboardScanResults" not in javascript.text

    scan_detail_tone = javascript.text.split(
        "function getScanDetailTone",
        maxsplit=1,
    )[1].split(
        "function getScanDetailRiskCopy",
        maxsplit=1,
    )[0]
    assert 'detail.dynamicStatus === "partial_success"' not in scan_detail_tone
    assert 'detail.dynamicStatus === "failed"' not in scan_detail_tone
    assert 'detail.dynamicStatus === "timed_out"' not in scan_detail_tone

    scan_detail_severity_summary = javascript.text.split(
        "function renderScanDetailSeveritySummary",
        maxsplit=1,
    )[1].split(
        "function getSafeScanDetailSource",
        maxsplit=1,
    )[0]
    assert "[\"critical\", detail.severity.critical]" in scan_detail_severity_summary
    assert "[\"high\", detail.severity.high]" in scan_detail_severity_summary
    assert "[\"medium\", detail.severity.medium]" in scan_detail_severity_summary
    assert "[\"low\", detail.severity.low]" in scan_detail_severity_summary
    assert "detail.severity.info" not in scan_detail_severity_summary

    scan_detail_finding_detail = javascript.text.split(
        "function renderScanDetailFindingDetail",
        maxsplit=1,
    )[1].split(
        "function createScanDetailTextBlock",
        maxsplit=1,
    )[0]
    assert "[\"위험도\", finding.severity || severity]" in scan_detail_finding_detail

    candidate_list_item = javascript.text.split(
        "function createCandidateListItem",
        maxsplit=1,
    )[1].split(
        "function selectCandidateForReview",
        maxsplit=1,
    )[0]
    assert "title.textContent = candidateId" in candidate_list_item
    assert "compactIdentifier(candidateId)" not in candidate_list_item

    candidate_decision_panel = javascript.text.split(
        "function startCandidateDecision",
        maxsplit=1,
    )[1].split(
        "function clearCandidateDecisionPanel",
        maxsplit=1,
    )[0]
    assert "compactIdentifier(candidateId)" not in candidate_decision_panel

    attention_model = javascript.text.split(
        "function createAttentionModel",
        maxsplit=1,
    )[1].split(
        "function createScanResultAttentionModel",
        maxsplit=1,
    )[0]
    assert "state?.last_comparison" not in attention_model

    baseline_revoke_refresh = javascript.text.split(
        "async function refreshAfterBaselineRevocation",
        maxsplit=1,
    )[1].split(
        "function getLatestSafeSummary",
        maxsplit=1,
    )[0]
    candidate_decision_refresh = javascript.text.split(
        "async function refreshAfterCandidateDecision",
        maxsplit=1,
    )[1].split(
        "function renderBaselineHistoryServerList",
        maxsplit=1,
    )[0]
    history_deletion_refresh = javascript.text.split(
        "async function refreshAfterBaselineHistoryDeletion",
        maxsplit=1,
    )[1].split(
        "function applyHistoryDeletionResultToServer",
        maxsplit=1,
    )[0]

    assert "clearCachedScanResultForSelection(selectionId)" not in baseline_revoke_refresh
    assert "clearCachedScanResultForSelection(selectionId)" not in candidate_decision_refresh
    assert "clearCachedScanResultForSelection(selectionId)" not in history_deletion_refresh

    batch_status_function = javascript.text.split(
        "function getBatchStatusForServer",
        1,
    )[1].split("function renderScanProgressPanel", 1)[0]
    assert "null" in batch_status_function
    assert 'status: "queued"' not in batch_status_function
    assert "if (batchStatus)" in javascript.text

    target_detail_function = javascript.text.split(
        "function selectServerForManagement",
        1,
    )[1].split("async function loadTargetDetails", 1)[0]
    assert "hasPersistedMonitoringState(server)" in target_detail_function

    assert "isMonitoringNotFoundError(error)" in javascript.text
    assert "/api/mcp/candidates/" in javascript.text
    assert "/approve" in javascript.text
    assert "/reject" in javascript.text
    assert "/baseline/revoke" in javascript.text
    assert "monitoring_target_key" in javascript.text
    assert "expected_state_version" in javascript.text
    assert "expected_current_approved_id" in javascript.text
    assert "safe_reason_code" in javascript.text
    assert "candidate_created" in javascript.text
    assert "candidate_reused" in javascript.text
    assert "rejected_same_snapshot" in javascript.text
    assert "comparison_status === \"matched\"" in javascript.text
    assert "state_version_at_creation" in javascript.text
    assert "comparison_result" in javascript.text
    assert "tool_changes" in javascript.text
    assert "field_changes" in javascript.text
    assert "old_value_text" in javascript.text
    assert "new_value_text" in javascript.text
    assert "old_value_truncated" in javascript.text
    assert "new_value_truncated" in javascript.text
    assert "textContent" in javascript.text

    candidate_decision_function = javascript.text.split(
        "async function submitCandidateDecision",
        1,
    )[1].split(
        "async function fetchLatestTargetStateForCandidateDecision",
        1,
    )[0]
    assert "fetchLatestTargetStateForCandidateDecision" in candidate_decision_function
    assert "isCandidatePending(candidateId, latestState)" in candidate_decision_function
    assert "expected_state_version: latestState.state_version" in candidate_decision_function
    assert "safe_reason_code: reasonCode || null" in candidate_decision_function
    assert "candidate.state_version_at_creation" not in candidate_decision_function
    assert "state_version_at_creation" not in candidate_decision_function

    candidate_detail_function = javascript.text.split(
        "function renderCandidateBasicInfo",
        1,
    )[1].split("function renderCandidateSnapshotSummary", 1)[0]
    assert "candidate.state_version_at_creation" in candidate_detail_function

    scan_completion_function = javascript.text.split(
        "async function runSelectedServerScans",
        1,
    )[1].split("async function scanOneServer", 1)[0]
    assert "buildCompletedScanItems(selectedServers)" in scan_completion_function
    assert "mcpUiState.selection.selectedServerIds.clear()" in scan_completion_function
    assert "mcpUiState.scanBatch.phase = \"setup\"" in scan_completion_function
    assert "showView(\n        \"dashboard\"" in scan_completion_function
    assert "mcpUiState.scanBatch.phase = \"completed\"" not in javascript.text

    scan_reset_function = javascript.text.split(
        "function resetScanBatchForNewScan",
        1,
    )[1].split("function selectFailedCompletedServersForRetry", 1)[0]
    assert "completedItems = []" in scan_reset_function
    assert "selectedServerIds.clear()" in scan_reset_function

    baseline_revoke_function = javascript.text.split(
        "async function submitBaselineRevocation",
        1,
    )[1].split(
        "async function fetchLatestTargetStateForBaselineRevocation",
        1,
    )[0]
    assert "fetchLatestTargetStateForBaselineRevocation" in baseline_revoke_function
    assert "expected_state_version: latestState.state_version" in baseline_revoke_function
    assert "expected_current_approved_id: latestApprovedId" in baseline_revoke_function
    assert "safe_reason_code: reasonCode || null" in baseline_revoke_function
    assert "기준선 이력을 불러오지 못했습니다." in javascript.text
    assert "아직 생성된 기준선 이력이 없습니다." in javascript.text

    for forbidden_text in (
        "innerHTML",
        "insertAdjacentHTML",
        "document.write",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "Promise.all",
        "Promise.allSettled",
        "window.confirm",
        "command_args",
        "command_path",
        "raw_command",
        "env_values",
        "header_values",
        "url_path",
        "url_query",
        "access_token",
    ):
        assert forbidden_text not in javascript.text

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
