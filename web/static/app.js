"use strict";


const uiState = {
    activeView: "dashboard",
};


const viewMeta = {
    dashboard: {
        eyebrow: "검사 결과",
        title: "AI 도구 안전검진",
        subtitle: "전체 MCP 서버의 현재 안전 상태를 확인합니다.",
    },
    "scan-detail": {
        eyebrow: "상세 결과",
        title: "MCP 서버 상세 결과",
        subtitle: "선택한 서버의 최근 검사 Finding을 확인합니다.",
    },
    "scan-start": {
        eyebrow: "검사 시작",
        title: "MCP 서버 검사",
        subtitle: "검사할 MCP 서버를 선택하고 순서대로 검사합니다.",
    },
    "server-management": {
        eyebrow: "MCP 서버 관리",
        title: "MCP 서버 관리",
        subtitle: "등록 상태와 안전한 연결 요약을 확인합니다.",
    },
    "baseline-history": {
        eyebrow: "기준선 이력",
        title: "기준선 이력",
        subtitle: "기준선 후보 승인·거절과 승인 기준선 변경 기록을 확인합니다.",
    },
    "static-scan": {
        eyebrow: "파일·샘플 검사",
        title: "파일·샘플 검사",
        subtitle: "tools.json 파일이나 등록된 테스트 샘플을 검사합니다.",
    },
    help: {
        eyebrow: "도움말",
        title: "도움말",
        subtitle: "화면별 역할을 간단히 확인합니다.",
    },
};


const dashboardState = {
    status: "idle",
    label: "결과 대기",
    headline: "표시할 검사 결과가 없습니다.",
    description: "검사 시작 화면에서 서버를 선택해 검사를 실행하세요.",
    counts: {
        safe: 0,
        warning: 0,
        danger: 0,
    },
    attentionItems: [],
    lastUpdatedAt: null,
};


const mcpUiState = {
    security: {
        token: null,
        headerName: null,
        loading: false,
        error: null,
    },
    serverCatalog: {
        loading: false,
        loaded: false,
        error: null,
        includeTrustedProjectConfig: false,
        loadedIncludeTrustedProjectConfig: null,
        servers: [],
        total: 0,
        lastLoadedAt: null,
    },
    selection: {
        selectedServerIds: new Set(),
    },
    scanBatch: {
        phase: "setup",
        running: false,
        currentIndex: 0,
        total: 0,
        currentSelectionId: null,
        resultsBySelectionId: new Map(),
        statusesBySelectionId: new Map(),
        completedItems: [],
        startedAt: null,
        completedAt: null,
        error: null,
    },
    scanDetail: {
        selectionId: null,
        selectedFindingIndex: 0,
    },
    serverManagement: {
        selectedSelectionId: null,
        targetDetailsByKey: new Map(),
        loadingTargetKey: null,
        error: null,
    },
    baselineHistory: {
        selectedTargetKey: null,
        recordsByTargetKey: new Map(),
        loadingTargetKey: null,
        deletingTargetKey: null,
        deleteConfirmTargetKey: null,
        error: null,
        deleteError: null,
        deleteSuccess: null,
    },
    candidateReview: {
        selectedCandidateId: null,
        expandedCandidateId: null,
        candidateDetailsById: new Map(),
        loadingCandidateId: null,
        error: null,
        decisionMode: null,
        decisionCandidateId: null,
        decisionRunning: false,
        decisionError: null,
        decisionSuccess: null,
    },
    baselineRevoke: {
        panelOpen: false,
        targetKey: null,
        baselineId: null,
        running: false,
        error: null,
        success: null,
    },
};


const unsafeHttpMethods = new Set([
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
]);


const bannerToneByStatus = {
    idle: "unscanned",
    safe: "safe",
    warning: "warning",
    danger: "danger",
    error: "danger",
};


const bannerIconByTone = {
    safe: "✓",
    warning: "!",
    danger: "×",
    unscanned: "◌",
};


const productLabelByValue = {
    codex: "Codex",
    claude: "Claude",
};


const scopeLabelByValue = {
    user: "사용자",
    project: "프로젝트",
    local: "로컬 프로젝트",
};


const transportLabelByValue = {
    stdio: "STDIO",
    streamable_http: "HTTP",
};


const scanStatusLabelByValue = {
    not_scanned: "검사 전",
    scanning: "검사 중",
    success: "검사 성공",
    partial_success: "검사 성공",
    failed: "검사 실패",
    timed_out: "시간 초과",
    skipped: "건너뜀",
};


const baselineLifecycleLabelByValue = {
    none: "기준선 없음",
    candidate_pending: "승인 대기",
    approved: "승인됨",
    rejected: "거절됨",
};


const comparisonStatusLabelByValue = {
    not_compared: "비교 전",
    matched: "일치",
    changed: "변경됨",
    comparison_failed: "비교 실패",
};


const verificationStatusLabelByValue = {
    unverified: "미검증",
    verified: "검증 완료",
    review_required: "검토 필요",
    unavailable: "확인 불가",
};


const enabledStateLabelByValue = {
    enabled: "활성",
    disabled: "비활성",
};


const supportStateLabelByValue = {
    supported: "지원",
    unsupported: "미지원",
};


const progressStatusLabelByValue = {
    queued: "대기 중",
    scanning: "검사 중",
    completed: "완료",
    failed: "실패",
    skipped: "건너뜀",
};


const historyEventLabelByValue = {
    candidate_created: "후보 기준선 생성",
    candidate_approved: "후보 기준선 승인",
    candidate_rejected: "후보 기준선 거절",
    baseline_superseded: "기존 기준선 교체",
    baseline_revoked: "승인 기준선 삭제",
};


const historyReasonLabelByValue = {
    user_approved: "사용자가 기준선 후보를 승인함",
    user_rejected: "사용자가 기준선 후보를 거절함",
    user_revoked_baseline: "사용자가 승인 기준선을 삭제함",
    user_reconsidered: "사용자가 이전 거절 상태를 다시 검토함",
    reconsidered_rejected: "이전에 거절한 상태를 다시 검토함",
};


const safeConfigLabelByKey = {
    transport: "연결 방식",
    command_basename: "실행 프로그램",
    argument_count: "인자 개수",
    cwd_present: "작업 디렉터리 설정 여부",
    env_key_count: "환경변수 항목 수",
    env_literal_key_count: "Literal 환경변수 수",
    env_reference_key_count: "참조 환경변수 수",
    env_reference_count: "환경변수 참조 수",
    origin: "원격 Origin",
    header_name_count: "Header 이름 수",
    token_reference_present: "Token 참조 여부",
    verify_tls: "TLS 검증",
    follow_redirects: "Redirect 허용",
    trust_env: "환경 Proxy 사용",
};


const toolChangeLabelByValue = {
    added: "추가됨",
    removed: "삭제됨",
    changed: "변경됨",
    unchanged: "변경 없음",
};


const fieldNameLabelByValue = {
    server_name: "서버 이름",
    tool_name: "Tool 이름",
    title: "제목",
    description: "설명",
    input_schema: "입력 Schema",
    output_schema: "출력 Schema",
    annotations: "Annotations",
    meta: "Meta",
};


const fieldPresenceLabelByValue = {
    missing: "필드 없음",
    null: "null",
    value: "값 있음",
};


const attentionToneByStatus = {
    safe: "safe",
    warning: "warning",
    danger: "danger",
    failed: "failed",
    timed_out: "failed",
    scan_failed: "failed",
    unscanned: "unscanned",
    candidate: "candidate",
    candidate_pending: "candidate",
    rejected: "candidate",
    config: "config",
    config_changed: "config",
    tool: "tool",
    tool_changed: "tool",
    unavailable: "warning",
};


const attentionLabelByTone = {
    safe: "안전",
    warning: "주의",
    danger: "위험",
    failed: "검사 실패",
    unscanned: "검사 필요",
    candidate: "기준선 승인 대기",
    config: "설정 변경",
    tool: "Tool 변경",
};


const elements = {
    navigationButtons: Array.from(
        document.querySelectorAll("[data-view-target]")
    ),
    views: Array.from(
        document.querySelectorAll("[data-view]")
    ),
    workspaceEyebrow: document.getElementById("workspace-eyebrow"),
    workspaceTitle: document.getElementById("workspace-title"),
    workspaceSubtitle: document.getElementById("workspace-subtitle"),
    dashboardStatusBanner: document.getElementById(
        "dashboard-status-banner"
    ),
    dashboardStatusIcon: document.getElementById(
        "dashboard-status-icon"
    ),
    dashboardStatusLabel: document.getElementById(
        "dashboard-status-label"
    ),
    dashboardHeadline: document.getElementById("dashboard-headline"),
    dashboardDescription: document.getElementById(
        "dashboard-description"
    ),
    dashboardSafeCount: document.getElementById(
        "dashboard-safe-count"
    ),
    dashboardWarningCount: document.getElementById(
        "dashboard-warning-count"
    ),
    dashboardDangerCount: document.getElementById(
        "dashboard-danger-count"
    ),
    dashboardAttentionList: document.getElementById(
        "dashboard-attention-list"
    ),
    dashboardAttentionEmpty: document.getElementById(
        "dashboard-attention-empty"
    ),
    dashboardLastUpdated: document.getElementById(
        "dashboard-last-updated"
    ),
    scanDetailBackButton: document.getElementById(
        "scan-detail-back-button"
    ),
    scanDetailTitle: document.getElementById("scan-detail-title"),
    scanDetailRiskPanel: document.getElementById(
        "scan-detail-risk-panel"
    ),
    scanDetailRiskIcon: document.getElementById("scan-detail-risk-icon"),
    scanDetailRiskTitle: document.getElementById(
        "scan-detail-risk-title"
    ),
    scanDetailRiskDescription: document.getElementById(
        "scan-detail-risk-description"
    ),
    scanDetailMeta: document.getElementById("scan-detail-meta"),
    scanDetailSeveritySummary: document.getElementById(
        "scan-detail-severity-summary"
    ),
    scanDetailFindingCount: document.getElementById(
        "scan-detail-finding-count"
    ),
    scanDetailFindingList: document.getElementById(
        "scan-detail-finding-list"
    ),
    scanDetailFindingEmpty: document.getElementById(
        "scan-detail-finding-empty"
    ),
    scanDetailFindingDetail: document.getElementById(
        "scan-detail-finding-detail"
    ),
    scanDetailFindingDetailEmpty: document.getElementById(
        "scan-detail-finding-detail-empty"
    ),

    scanDetailBaselineSection: document.getElementById(
        "scan-detail-baseline-section"
    ),
    scanDetailBaselineEmpty: document.getElementById(
        "scan-detail-baseline-empty"
    ),
    scanDetailBaselineContent: document.getElementById(
        "scan-detail-baseline-content"
    ),
    scanDetailComparisonSummary: document.getElementById(
        "scan-detail-comparison-summary"
    ),
    scanDetailToolDiff: document.getElementById(
        "scan-detail-tool-diff"
    ),

    includeProjectConfigToggle: document.getElementById(
        "scan-include-project-config"
    ),
    scanRefreshServersButton: document.getElementById(
        "scan-refresh-servers-button"
    ),
    scanSelectAllButton: document.getElementById(
        "scan-select-all-button"
    ),
    scanClearSelectionButton: document.getElementById(
        "scan-clear-selection-button"
    ),
    scanServerStatus: document.getElementById("scan-server-status"),
    scanServerError: document.getElementById("scan-server-error"),
    scanSetupSection: document.getElementById("scan-setup-section"),
    scanRunningSection: document.getElementById("scan-running-section"),
    scanServerList: document.getElementById("scan-server-list"),
    scanSelectedCount: document.getElementById("scan-selected-count"),
    scanAvailableCount: document.getElementById("scan-available-count"),
    scanSelectedServersButton: document.getElementById(
        "scan-selected-servers-button"
    ),
    scanProgressPanel: document.getElementById("scan-progress-panel"),
    scanProgressCurrent: document.getElementById("scan-progress-current"),
    scanProgressTotal: document.getElementById("scan-progress-total"),
    scanProgressLabel: document.getElementById("scan-progress-label"),
    scanProgressBar: document.getElementById("scan-progress-bar"),
    scanCurrentServerName: document.getElementById(
        "scan-current-server-name"
    ),
    scanProgressServerList: document.getElementById(
        "scan-progress-server-list"
    ),

    serverManagementStatus: document.getElementById(
        "server-management-status"
    ),
    serverManagementError: document.getElementById(
        "server-management-error"
    ),
    serverManagementList: document.getElementById("server-management-list"),
    serverManagementDetail: document.getElementById(
        "server-management-detail"
    ),
    serverManagementDetailEmpty: document.getElementById(
        "server-management-detail-empty"
    ),
    serverManagementDetailContent: document.getElementById(
        "server-management-detail-content"
    ),
    serverName: document.getElementById("server-name"),
    serverProduct: document.getElementById("server-product"),
    serverScope: document.getElementById("server-scope"),
    serverTransport: document.getElementById("server-transport"),
    serverEnabledState: document.getElementById("server-enabled-state"),
    serverSupportState: document.getElementById("server-support-state"),
    serverCanScan: document.getElementById("server-can-scan"),
    serverLastScanStatus: document.getElementById(
        "server-last-scan-status"
    ),
    serverLastScanAt: document.getElementById("server-last-scan-at"),
    serverBaselineLifecycle: document.getElementById(
        "server-baseline-lifecycle"
    ),
    serverComparisonStatus: document.getElementById(
        "server-comparison-status"
    ),
    serverVerificationStatus: document.getElementById(
        "server-verification-status"
    ),
    serverCommandBasename: document.getElementById(
        "server-command-basename"
    ),
    serverArgumentCount: document.getElementById("server-argument-count"),
    serverEnvReferenceCount: document.getElementById(
        "server-env-reference-count"
    ),
    serverRemoteOrigin: document.getElementById("server-remote-origin"),
    serverTlsVerified: document.getElementById("server-tls-verified"),
    serverCurrentApprovedId: document.getElementById(
        "server-current-approved-id"
    ),
    serverRevokeBaselineButton: document.getElementById(
        "server-revoke-baseline-button"
    ),
    baselineRevokePanel: document.getElementById("baseline-revoke-panel"),
    baselineRevokeTitle: document.getElementById("baseline-revoke-title"),
    baselineRevokeSummary: document.getElementById("baseline-revoke-summary"),
    baselineRevokeReasonCode: document.getElementById(
        "baseline-revoke-reason-code"
    ),
    baselineRevokeConfirmButton: document.getElementById(
        "baseline-revoke-confirm-button"
    ),
    baselineRevokeCancelButton: document.getElementById(
        "baseline-revoke-cancel-button"
    ),
    baselineRevokeError: document.getElementById("baseline-revoke-error"),
    candidateReviewStatus: document.getElementById(
        "candidate-review-status"
    ),
    candidateReviewError: document.getElementById(
        "candidate-review-error"
    ),
    candidateList: document.getElementById("candidate-list"),
    candidateListEmpty: document.getElementById("candidate-list-empty"),
    candidateDetailEmpty: document.getElementById(
        "candidate-detail-empty"
    ),
    candidateDetail: document.getElementById("candidate-detail"),
    candidateBasicInfo: document.getElementById("candidate-basic-info"),
    candidateSnapshotSummary: document.getElementById(
        "candidate-snapshot-summary"
    ),
    candidateConfigSummary: document.getElementById(
        "candidate-config-summary"
    ),
    candidateComparisonSummary: document.getElementById(
        "candidate-comparison-summary"
    ),
    candidateToolDiff: document.getElementById("candidate-tool-diff"),
    candidateApproveButton: document.getElementById(
        "candidate-approve-button"
    ),
    candidateRejectButton: document.getElementById(
        "candidate-reject-button"
    ),
    candidateDecisionPanel: document.getElementById(
        "candidate-decision-panel"
    ),
    candidateDecisionTitle: document.getElementById(
        "candidate-decision-title"
    ),
    candidateDecisionDescription: document.getElementById(
        "candidate-decision-description"
    ),
    candidateDecisionSummary: document.getElementById(
        "candidate-decision-summary"
    ),
    candidateReasonCode: document.getElementById("candidate-reason-code"),
    candidateDecisionConfirmButton: document.getElementById(
        "candidate-decision-confirm-button"
    ),
    candidateDecisionCancelButton: document.getElementById(
        "candidate-decision-cancel-button"
    ),

    baselineHistoryStatus: document.getElementById(
        "baseline-history-status"
    ),
    baselineHistoryError: document.getElementById(
        "baseline-history-error"
    ),
    baselineHistoryServerList: document.getElementById(
        "baseline-history-server-list"
    ),
    baselineHistoryList: document.getElementById(
        "baseline-history-list"
    ),
    baselineHistoryDeleteButton: document.getElementById(
        "baseline-history-delete-button"
    ),
    baselineHistoryDeleteConfirmPanel: document.getElementById(
        "baseline-history-delete-confirm-panel"
    ),
    baselineHistoryDeleteConfirmSummary: document.getElementById(
        "baseline-history-delete-confirm-summary"
    ),
    baselineHistoryDeleteConfirmButton: document.getElementById(
        "baseline-history-delete-confirm-button"
    ),
    baselineHistoryDeleteCancelButton: document.getElementById(
        "baseline-history-delete-cancel-button"
    ),

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
    bindNavigationEvents();
    bindMcpUiEvents();
    bindStaticScanEvents();
    showView(
        uiState.activeView,
        {
            focusTitle: false,
        }
    );
    renderDashboardSummary(dashboardState);
    resetResultView();
    renderAllMcpViews();

    try {
        await ensureRequestToken();
    } catch {
        setStatus(
            "error",
            "Request Token을 준비하지 못했습니다. 검사 실행은 사용할 수 없습니다."
        );
    }

    await loadSamples();

    if (mcpUiState.security.error) {
        setStatus(
            "error",
            "Request Token을 준비하지 못했습니다. 검사 실행은 사용할 수 없습니다."
        );
    }

    await loadMcpServers();
}


function bindNavigationEvents() {
    for (const button of elements.navigationButtons) {
        button.addEventListener(
            "click",
            () => showView(
                button.dataset.viewTarget,
                {
                    focusTitle: true,
                }
            )
        );
    }

}


function bindMcpUiEvents() {
    if (elements.scanDetailBackButton) {
        elements.scanDetailBackButton.addEventListener(
            "click",
            closeScanDetail
        );
    }

    elements.includeProjectConfigToggle.addEventListener(
        "change",
        handleProjectConfigToggleChange
    );

    elements.scanRefreshServersButton.addEventListener(
        "click",
        () => loadMcpServers()
    );

    elements.scanSelectAllButton.addEventListener(
        "click",
        selectAllScannableServers
    );

    elements.scanClearSelectionButton.addEventListener(
        "click",
        clearServerSelection
    );

    elements.scanSelectedServersButton.addEventListener(
        "click",
        runSelectedServerScans
    );

    elements.serverRevokeBaselineButton.addEventListener(
        "click",
        startBaselineRevocation
    );

    elements.baselineRevokeConfirmButton.addEventListener(
        "click",
        submitBaselineRevocation
    );

    elements.baselineRevokeCancelButton.addEventListener(
        "click",
        clearBaselineRevocationPanel
    );

    elements.baselineHistoryDeleteButton.addEventListener(
        "click",
        startBaselineHistoryDeletionConfirmation
    );

    elements.baselineHistoryDeleteConfirmButton.addEventListener(
        "click",
        deleteSelectedBaselineHistory
    );

    elements.baselineHistoryDeleteCancelButton.addEventListener(
        "click",
        clearBaselineHistoryDeletionConfirmation
    );

    elements.candidateApproveButton.addEventListener(
        "click",
        () => startCandidateDecision("approve")
    );

    elements.candidateRejectButton.addEventListener(
        "click",
        () => startCandidateDecision("reject")
    );

    elements.candidateDecisionConfirmButton.addEventListener(
        "click",
        submitCandidateDecision
    );

    elements.candidateDecisionCancelButton.addEventListener(
        "click",
        clearCandidateDecisionPanel
    );
}


function bindStaticScanEvents() {
    if (elements.toolsFile) {
        elements.toolsFile.addEventListener(
            "change",
            handleFileSelection
        );
    }

    if (elements.sampleSelect) {
        elements.sampleSelect.addEventListener(
            "change",
            handleSampleSelection
        );
    }

    if (elements.scanButton) {
        elements.scanButton.addEventListener(
            "click",
            handleScan
        );
    }
}


function showView(
    viewName,
    options = {}
) {
    if (!viewMeta[viewName]) {
        return;
    }

    handleViewTransition(
        uiState.activeView,
        viewName
    );

    uiState.activeView = viewName;

    for (const view of elements.views) {
        view.hidden = view.dataset.view !== viewName;
    }

    updateActiveNavigation(viewName);
    updateWorkspaceTitle(viewName);

    if (
        viewName === "server-management" &&
        !mcpUiState.serverCatalog.loaded &&
        !mcpUiState.serverCatalog.loading
    ) {
        loadMcpServers();
    }

    if (
        viewName === "baseline-history" &&
        !mcpUiState.serverCatalog.loaded &&
        !mcpUiState.serverCatalog.loading
    ) {
        loadMcpServers();
    }

    if (viewName === "scan-detail") {
        renderScanDetail();
    }

    if (options.focusTitle && elements.workspaceTitle) {
        elements.workspaceTitle.focus();
    }
}


function handleViewTransition(
    previousView,
    nextView
) {
    if (
        previousView === "server-management" &&
        nextView !== "server-management"
    ) {
        clearServerManagementTransientMessages();
    }
}


function clearServerManagementTransientMessages() {
    clearCandidateReviewTransientMessages();

    if (!mcpUiState.baselineRevoke.running) {
        mcpUiState.baselineRevoke.error = null;
        mcpUiState.baselineRevoke.success = null;
    }
}


function clearCandidateReviewTransientMessages() {
    if (mcpUiState.candidateReview.decisionRunning) {
        return;
    }

    mcpUiState.candidateReview.decisionError = null;
    mcpUiState.candidateReview.decisionSuccess = null;
}


function updateActiveNavigation(viewName) {
    for (const button of elements.navigationButtons) {
        const isActive = button.dataset.viewTarget === viewName;

        button.classList.toggle(
            "is-active",
            isActive
        );

        if (isActive) {
            button.setAttribute(
                "aria-current",
                "page"
            );
        } else {
            button.removeAttribute("aria-current");
        }
    }
}


function updateWorkspaceTitle(viewName) {
    const meta = viewMeta[viewName];

    elements.workspaceEyebrow.textContent = meta.eyebrow;
    elements.workspaceTitle.textContent = meta.title;
    elements.workspaceSubtitle.textContent = meta.subtitle;
    document.title = `${meta.title} - MCP-AuditGuard`;
}


async function ensureRequestToken() {
    if (mcpUiState.security.token && mcpUiState.security.headerName) {
        return;
    }

    await refreshRequestToken();
}


async function refreshRequestToken() {
    mcpUiState.security.loading = true;
    mcpUiState.security.error = null;
    updateMcpControls();

    try {
        const response = await fetch(
            "/api/security/request-token",
            {
                cache: "no-store",
            }
        );
        const payload = await parseResponsePayload(response);

        if (!response.ok) {
            throw createApiError(
                response,
                payload,
                "Request Token을 준비하지 못했습니다."
            );
        }

        if (
            !payload ||
            typeof payload.header_name !== "string" ||
            typeof payload.request_token !== "string"
        ) {
            throw new Error("Request Token 응답 형식이 올바르지 않습니다.");
        }

        mcpUiState.security.headerName = payload.header_name;
        mcpUiState.security.token = payload.request_token;
        mcpUiState.security.error = null;
    } catch (error) {
        mcpUiState.security.token = null;
        mcpUiState.security.headerName = null;
        mcpUiState.security.error = getErrorMessage(
            error,
            "Request Token을 준비하지 못했습니다."
        );
        throw error;
    } finally {
        mcpUiState.security.loading = false;
        updateMcpControls();
    }
}


function getSecureRequestHeaders() {
    if (!mcpUiState.security.token || !mcpUiState.security.headerName) {
        throw new Error("Request Token을 준비하지 못했습니다.");
    }

    return {
        [mcpUiState.security.headerName]: mcpUiState.security.token,
    };
}


async function apiFetch(
    url,
    {
        method = "GET",
        headers = {},
        body = undefined,
        json = undefined,
        retryRequestToken = true,
    } = {}
) {
    const requestMethod = method.toUpperCase();
    const requestHeaders = {
        ...headers,
    };
    let requestBody = body;

    if (json !== undefined) {
        requestHeaders["Content-Type"] = "application/json";
        requestBody = JSON.stringify(json);
    }

    if (unsafeHttpMethods.has(requestMethod)) {
        if (!mcpUiState.security.token || !mcpUiState.security.headerName) {
            await ensureRequestToken();
        }

        Object.assign(
            requestHeaders,
            getSecureRequestHeaders()
        );
    }

    const response = await fetch(
        url,
        {
            method: requestMethod,
            headers: requestHeaders,
            body: requestBody,
            cache: requestMethod === "GET" ? "no-store" : "default",
        }
    );
    const payload = await parseResponsePayload(response);

    if (response.ok) {
        return payload;
    }

    if (
        retryRequestToken &&
        unsafeHttpMethods.has(requestMethod) &&
        response.status === 403 &&
        payload &&
        payload.error_code === "request_token_invalid"
    ) {
        await refreshRequestToken();
        return apiFetch(
            url,
            {
                method: requestMethod,
                headers,
                body,
                json,
                retryRequestToken: false,
            }
        );
    }

    throw createApiError(
        response,
        payload,
        "요청에 실패했습니다."
    );
}


async function parseResponsePayload(response) {
    if (response.status === 204) {
        return null;
    }

    try {
        return await response.json();
    } catch {
        return null;
    }
}


function createApiError(
    response,
    payload,
    fallbackMessage
) {
    const error = new Error(
        getSafeErrorMessage(
            payload,
            fallbackMessage
        )
    );

    error.statusCode = response.status;
    error.errorCode = payload && payload.error_code
        ? payload.error_code
        : null;

    return error;
}


function getSafeErrorMessage(
    payload,
    fallbackMessage
) {
    if (!payload) {
        return fallbackMessage;
    }

    if (typeof payload.message === "string") {
        return payload.message;
    }

    if (typeof payload.detail === "string") {
        return payload.detail;
    }

    if (payload.detail && typeof payload.detail === "object") {
        if (typeof payload.detail.message === "string") {
            return payload.detail.message;
        }

        if (
            Array.isArray(payload.detail.available_files) &&
            typeof payload.detail.error === "string"
        ) {
            return `${payload.detail.error} 사용 가능한 파일을 확인하세요.`;
        }
    }

    if (typeof payload.error === "string") {
        return payload.error;
    }

    if (typeof payload.error_code === "string") {
        return fallbackMessage;
    }

    return fallbackMessage;
}


function getErrorMessage(
    error,
    fallbackMessage
) {
    if (error && typeof error.message === "string") {
        return error.message;
    }

    return fallbackMessage;
}


async function loadMcpServers() {
    if (mcpUiState.serverCatalog.loading) {
        return;
    }

    mcpUiState.serverCatalog.loading = true;
    mcpUiState.serverCatalog.error = null;
    renderAllMcpViews();

    const params = new URLSearchParams();
    params.set(
        "include_trusted_project_config",
        String(mcpUiState.serverCatalog.includeTrustedProjectConfig)
    );

    try {
        const payload = await apiFetch(
            `/api/mcp/servers?${params.toString()}`
        );
        const normalized = normalizeServerListResponse(payload);

        mcpUiState.serverCatalog.servers = normalized.servers;
        mcpUiState.serverCatalog.total = normalized.total;
        mcpUiState.serverCatalog.loaded = true;
        mcpUiState.serverCatalog.loadedIncludeTrustedProjectConfig =
            normalized.includeTrustedProjectConfig;
        mcpUiState.serverCatalog.lastLoadedAt = new Date().toISOString();
        mcpUiState.serverCatalog.error = null;
        reconcileSelectionWithCatalog();
        reconcileActiveServerViews();
        reconcileScanResultCacheWithCatalog();
    } catch (error) {
        mcpUiState.serverCatalog.error = getErrorMessage(
            error,
            "서버 목록을 불러오지 못했습니다."
        );
    } finally {
        mcpUiState.serverCatalog.loading = false;
        ensureCandidateSelectionForCurrentServer();
        renderAllMcpViews();
    }
}


function reconcileScanResultCacheWithCatalog() {
    const serversBySelectionId = new Map(
        mcpUiState.serverCatalog.servers.map((server) => [
            server.selectionId,
            server,
        ])
    );

    for (const selectionId of mcpUiState.scanBatch.resultsBySelectionId.keys()) {
        const server = serversBySelectionId.get(selectionId);

        if (!server) {
            clearCachedScanResultForSelection(selectionId);
        }
    }
}


function clearCachedScanResultForSelection(selectionId) {
    if (!selectionId) {
        return;
    }

    mcpUiState.scanBatch.resultsBySelectionId.delete(selectionId);
    mcpUiState.scanBatch.completedItems =
        mcpUiState.scanBatch.completedItems.filter(
            (item) => item.selectionId !== selectionId
        );
}


function normalizeServerListResponse(response) {
    const items = Array.isArray(response && response.servers)
        ? response.servers
        : [];
    const servers = items
        .map((item) => normalizeServerItem(item))
        .filter((server) => Boolean(server.selectionId));

    return {
        servers,
        total: Number.isFinite(response && response.total)
            ? response.total
            : servers.length,
        includeTrustedProjectConfig: Boolean(
            response && response.include_trusted_project_config
        ),
    };
}


function normalizeServerItem(
    item,
    existingServer = null
) {
    const server = item && item.server ? item.server : {};
    const identity = item && item.identity ? item.identity : {};
    const monitoringState =
        item && item.monitoring_state ? item.monitoring_state : {};
    const selectionId =
        server.selection_id ||
        identity.selection_id ||
        existingServer?.selectionId ||
        null;
    const pendingCandidateIds = Array.isArray(
        monitoringState.pending_candidate_ids
    )
        ? monitoringState.pending_candidate_ids
        : [];
    const rejectedCandidateIds = Array.isArray(
        monitoringState.rejected_candidate_ids
    )
        ? monitoringState.rejected_candidate_ids
        : [];
    const historyIds = Array.isArray(monitoringState.history_ids)
        ? monitoringState.history_ids
        : [];
    const hasLastFindingSummary = Object.prototype.hasOwnProperty.call(
        monitoringState,
        "last_finding_summary"
    );
    const lastFindingSummary = hasLastFindingSummary
        ? normalizeSeveritySummary(monitoringState.last_finding_summary)
        : existingServer?.lastFindingSummary || null;

    return {
        selectionId,
        serverName:
            server.server_name ||
            identity.display_server_name ||
            existingServer?.serverName ||
            selectionId ||
            "-",
        product:
            server.product ||
            identity.product ||
            existingServer?.product ||
            null,
        scope:
            server.scope ||
            identity.scope ||
            existingServer?.scope ||
            null,
        transport:
            server.transport ||
            existingServer?.transport ||
            null,
        enabledState:
            server.enabled_state ||
            existingServer?.enabledState ||
            null,
        supportState:
            server.support_state ||
            existingServer?.supportState ||
            null,
        supportReasonCode:
            server.support_reason_code ||
            existingServer?.supportReasonCode ||
            null,
        canScan: typeof item?.can_scan === "boolean"
            ? item.can_scan
            : Boolean(existingServer?.canScan),
        safeActionReason:
            item?.safe_action_reason ||
            server.support_reason_code ||
            existingServer?.safeActionReason ||
            null,
        monitoringGroupKey:
            identity.monitoring_group_key ||
            monitoringState.monitoring_group_key ||
            existingServer?.monitoringGroupKey ||
            null,
        monitoringTargetKey:
            identity.monitoring_target_key ||
            monitoringState.monitoring_target_key ||
            existingServer?.monitoringTargetKey ||
            null,
        lastScanStatus:
            monitoringState.last_scan_status ||
            existingServer?.lastScanStatus ||
            null,
        lastScanAt:
            monitoringState.last_scan_at ||
            existingServer?.lastScanAt ||
            null,
        lastFindingSummary,
        baselineLifecycle:
            monitoringState.baseline_lifecycle ||
            existingServer?.baselineLifecycle ||
            null,
        comparisonStatus:
            monitoringState.comparison_status ||
            existingServer?.comparisonStatus ||
            null,
        verificationStatus:
            monitoringState.verification_status ||
            existingServer?.verificationStatus ||
            null,
        currentApprovedId:
            monitoringState.current_approved_id ||
            existingServer?.currentApprovedId ||
            null,
        pendingCandidateCount: pendingCandidateIds.length,
        rejectedCandidateCount: rejectedCandidateIds.length,
        historyIds,
        relatedTargetCount: numberOrNull(item?.related_target_count),
        relatedApprovedTargetCount: numberOrNull(
            item?.related_approved_target_count
        ),
        commandBasename:
            server.command_basename ||
            existingServer?.commandBasename ||
            null,
        argumentCount: numberOrNull(server.argument_count),
        remoteOrigin:
            server.remote_origin ||
            existingServer?.remoteOrigin ||
            null,
        sourceLabel:
            server.source_label ||
            identity.source_label ||
            existingServer?.sourceLabel ||
            null,
        contextLabel:
            identity.context_label ||
            existingServer?.contextLabel ||
            null,
        stateVersion: numberOrNull(monitoringState.state_version),
        updatedAt:
            monitoringState.updated_at ||
            existingServer?.updatedAt ||
            null,
        lastComparison:
            monitoringState.last_comparison ||
            existingServer?.lastComparison ||
            null,
        rawMonitoringState: monitoringState,
    };
}


function normalizeServerFromScanResponse(
    response,
    existingServer
) {
    const relatedTargetKeys = Array.isArray(response.related_target_keys)
        ? response.related_target_keys
        : [];
    const relatedApprovedTargetKeys = Array.isArray(
        response.related_approved_target_keys
    )
        ? response.related_approved_target_keys
        : [];

    return normalizeServerItem(
        {
            server: response.server,
            identity: response.identity,
            monitoring_state: response.monitoring_state,
            related_target_count: relatedTargetKeys.length,
            related_approved_target_count: relatedApprovedTargetKeys.length,
            can_scan: existingServer ? existingServer.canScan : true,
            safe_action_reason: existingServer
                ? existingServer.safeActionReason
                : null,
        },
        existingServer
    );
}


function numberOrNull(value) {
    return typeof value === "number" && Number.isFinite(value)
        ? value
        : null;
}


function normalizeSeveritySummary(summary) {
    if (!summary || typeof summary !== "object") {
        return null;
    }

    return {
        critical: numberOrZero(summary.critical),
        high: numberOrZero(summary.high),
        medium: numberOrZero(summary.medium),
        low: numberOrZero(summary.low),
        info: numberOrZero(summary.info),
    };
}


function reconcileSelectionWithCatalog() {
    const availableIds = new Set(
        mcpUiState.serverCatalog.servers
            .filter((server) => server.canScan)
            .map((server) => server.selectionId)
    );

    for (const selectedId of mcpUiState.selection.selectedServerIds) {
        if (!availableIds.has(selectedId)) {
            mcpUiState.selection.selectedServerIds.delete(selectedId);
        }
    }
}


function reconcileActiveServerViews() {
    const selectionIds = new Set(
        mcpUiState.serverCatalog.servers.map(
            (server) => server.selectionId
        )
    );
    const targetKeys = new Set(
        mcpUiState.serverCatalog.servers
            .map((server) => server.monitoringTargetKey)
            .filter(Boolean)
    );

    if (
        mcpUiState.serverManagement.selectedSelectionId &&
        !selectionIds.has(mcpUiState.serverManagement.selectedSelectionId)
    ) {
        mcpUiState.serverManagement.selectedSelectionId = null;
        mcpUiState.serverManagement.error = null;
    }

    if (
        mcpUiState.baselineHistory.selectedTargetKey &&
        !targetKeys.has(mcpUiState.baselineHistory.selectedTargetKey)
    ) {
        mcpUiState.baselineHistory.selectedTargetKey = null;
        mcpUiState.baselineHistory.error = null;
    }
}


function handleProjectConfigToggleChange() {
    mcpUiState.serverCatalog.includeTrustedProjectConfig =
        elements.includeProjectConfigToggle.checked;

    renderAllMcpViews();
}


function selectAllScannableServers() {
    for (const server of mcpUiState.serverCatalog.servers) {
        if (server.canScan) {
            mcpUiState.selection.selectedServerIds.add(server.selectionId);
        }
    }

    renderAllMcpViews();
}


function clearServerSelection() {
    mcpUiState.selection.selectedServerIds.clear();
    renderAllMcpViews();
}


function setServerSelected(
    selectionId,
    selected
) {
    if (selected) {
        mcpUiState.selection.selectedServerIds.add(selectionId);
    } else {
        mcpUiState.selection.selectedServerIds.delete(selectionId);
    }

    renderAllMcpViews();
}


async function runSelectedServerScans() {
    if (mcpUiState.scanBatch.running) {
        return;
    }

    const selectedServers = getSelectedScannableServers();

    if (!selectedServers.length) {
        setScanServerStatus(
            "검사할 MCP 서버를 선택하세요.",
            false
        );
        return;
    }

    try {
        await ensureRequestToken();
    } catch {
        setScanServerStatus(
            "Request Token을 준비하지 못했습니다. 검사 실행은 사용할 수 없습니다.",
            true
        );
        return;
    }

    mcpUiState.scanBatch.phase = "running";
    mcpUiState.scanBatch.running = true;
    mcpUiState.scanBatch.currentIndex = 0;
    mcpUiState.scanBatch.total = selectedServers.length;
    mcpUiState.scanBatch.currentSelectionId = null;
    mcpUiState.scanBatch.startedAt = new Date().toISOString();
    mcpUiState.scanBatch.completedAt = null;
    mcpUiState.scanBatch.error = null;
    mcpUiState.scanBatch.completedItems = [];
    mcpUiState.scanBatch.resultsBySelectionId.clear();
    mcpUiState.scanBatch.statusesBySelectionId.clear();

    for (const server of selectedServers) {
        mcpUiState.scanBatch.statusesBySelectionId.set(
            server.selectionId,
            {
                status: "queued",
                message: "대기 중",
            }
        );
    }

    renderAllMcpViews();

    let blockingError = null;

    for (const server of selectedServers) {
        mcpUiState.scanBatch.currentSelectionId = server.selectionId;
        mcpUiState.scanBatch.statusesBySelectionId.set(
            server.selectionId,
            {
                status: "scanning",
                message: "검사 중",
            }
        );
        renderAllMcpViews();

        try {
            const response = await scanOneServer(server);
            mcpUiState.scanBatch.resultsBySelectionId.set(
                server.selectionId,
                response
            );
            upsertServerFromScanResponse(response);

            const dynamicStatus = response?.dynamic_scan_result?.status;
            const progressStatus = isFailedScanStatus(dynamicStatus)
                ? "failed"
                : "completed";

            mcpUiState.scanBatch.statusesBySelectionId.set(
                server.selectionId,
                {
                    status: progressStatus,
                    message: progressStatus === "failed"
                        ? displayScanStatus(dynamicStatus)
                        : "완료",
                }
            );
        } catch (error) {
            mcpUiState.scanBatch.statusesBySelectionId.set(
                server.selectionId,
                {
                    status: "failed",
                    message: getErrorMessage(
                        error,
                        "MCP 서버 검사를 완료하지 못했습니다."
                    ),
                }
            );

            if (isBatchBlockingError(error)) {
                blockingError = error;
                break;
            }
        } finally {
            mcpUiState.scanBatch.currentIndex =
                countFinishedScanStatuses();
            renderAllMcpViews();
        }
    }

    if (blockingError) {
        mcpUiState.scanBatch.error = getErrorMessage(
            blockingError,
            "MCP 서버 검사를 완료하지 못했습니다."
        );

        for (const server of selectedServers) {
            const current = mcpUiState.scanBatch.statusesBySelectionId.get(
                server.selectionId
            );

            if (current && current.status === "queued") {
                mcpUiState.scanBatch.statusesBySelectionId.set(
                    server.selectionId,
                    {
                        status: "skipped",
                        message: "건너뜀",
                    }
                );
            }
        }
    }

    mcpUiState.scanBatch.running = false;
    mcpUiState.scanBatch.currentSelectionId = null;
    mcpUiState.scanBatch.completedAt = new Date().toISOString();
    mcpUiState.scanBatch.completedItems =
        buildCompletedScanItems(selectedServers);
    mcpUiState.selection.selectedServerIds.clear();
    mcpUiState.scanBatch.phase = "setup";
    dashboardState.lastUpdatedAt = mcpUiState.scanBatch.completedAt;
    renderAllMcpViews();
    showView(
        "dashboard",
        {
            focusTitle: true,
        }
    );

    await loadMcpServers();
}


function buildCompletedScanItems(servers) {
    return servers.map((server) => {
        const result = mcpUiState.scanBatch.resultsBySelectionId.get(
            server.selectionId
        );
        const statusEntry = mcpUiState.scanBatch.statusesBySelectionId.get(
            server.selectionId
        );
        return createCompletedScanItem(
            server,
            result,
            statusEntry
        );
    });
}


function createCompletedScanItem(
    server,
    result,
    statusEntry
) {
    const dynamicStatus = result?.dynamic_scan_result?.status || null;
    const lastScanStatus =
        result?.monitoring_state?.last_scan_status ||
        server.lastScanStatus ||
        null;
    const classification = classifyCompletedScanResult(
        result,
        statusEntry,
        lastScanStatus
    );
    const severity = getSeveritySummary(result);

    return {
        selectionId: server.selectionId,
        serverName: server.serverName,
        monitoringTargetKey:
            result?.monitoring_state?.monitoring_target_key ||
            server.monitoringTargetKey ||
            null,
        scanStatus: dynamicStatus || lastScanStatus || statusEntry?.status || null,
        resultType: classification.resultType,
        badgeLabel: classification.badgeLabel,
        badgeTone: classification.badgeTone,
        headline: classification.headline,
        description: classification.description,
        candidateId: result?.candidate?.candidate_id || null,
        candidateCreated: Boolean(result?.candidate_created),
        candidateReused: Boolean(result?.candidate_reused),
        rejectedSameSnapshot: Boolean(result?.rejected_same_snapshot),
        comparisonMatched: Boolean(
            result?.comparison_result?.matched ||
            result?.comparison_result?.comparison_status === "matched"
        ),
        canReconsiderRejected: Boolean(result?.can_reconsider_rejected),
        severity,
        errorMessage: statusEntry?.status === "failed"
            ? statusEntry.message
            : null,
    };
}


function classifyCompletedScanResult(
    result,
    statusEntry,
    lastScanStatus
) {
    const dynamicStatus = result?.dynamic_scan_result?.status || null;
    const comparison = result?.comparison_result || null;

    if (
        dynamicStatus === "failed" ||
        lastScanStatus === "failed" ||
        statusEntry?.status === "failed" && !result
    ) {
        return {
            resultType: "failed",
            badgeLabel: "검사 실패",
            badgeTone: "danger",
            headline: "검사를 완료하지 못했습니다.",
            description: statusEntry?.message || "서버 검사 중 오류가 발생했습니다.",
        };
    }

    if (statusEntry?.status === "skipped" && !result) {
        return {
            resultType: "skipped",
            badgeLabel: "건너뜀",
            badgeTone: "neutral",
            headline: "검사를 실행하지 않았습니다.",
            description: statusEntry?.message || "앞선 오류로 인해 이 서버 검사를 건너뛰었습니다.",
        };
    }

    if (dynamicStatus === "timed_out") {
        return {
            resultType: "timed_out",
            badgeLabel: "시간 초과",
            badgeTone: "danger",
            headline: "검사 시간이 초과되었습니다.",
            description: "서버 응답이 제한 시간 안에 완료되지 않았습니다.",
        };
    }

    if (result?.candidate_created) {
        return {
            resultType: "candidate_created",
            badgeLabel: "새 후보",
            badgeTone: "warning",
            headline: "새 기준선 후보가 생성되었습니다.",
            description: "변경 내용을 검토한 뒤 승인하거나 거절하세요.",
        };
    }

    if (result?.candidate_reused) {
        return {
            resultType: "candidate_reused",
            badgeLabel: "기존 후보",
            badgeTone: "warning",
            headline: "동일한 승인 대기 후보가 이미 있습니다.",
            description: "새 후보를 만들지 않고 기존 후보를 사용했습니다.",
        };
    }

    if (result?.rejected_same_snapshot) {
        return {
            resultType: "rejected_same_snapshot",
            badgeLabel: "이전 거절과 동일",
            badgeTone: "neutral",
            headline: "이전에 거절한 변경 내용과 동일합니다.",
            description: "새 기준선 후보를 만들지 않았습니다.",
        };
    }

    if (comparison?.matched || comparison?.comparison_status === "matched") {
        return {
            resultType: "matched",
            badgeLabel: "기준선 일치",
            badgeTone: "safe",
            headline: "승인된 기준선과 변경 내용이 없습니다.",
            description: "새 기준선 후보나 추가 승인이 필요하지 않습니다.",
        };
    }

    if (dynamicStatus === "partial_success") {
        return {
            resultType: "success",
            badgeLabel: "검사 성공",
            badgeTone: "safe",
            headline: "검사가 완료되었습니다.",
            description: "Finding 결과를 확인할 수 있습니다.",
        };
    }

    return {
        resultType: "success",
        badgeLabel: "검사 성공",
        badgeTone: "safe",
        headline: "검사가 완료되었습니다.",
        description: result?.candidate
            ? "기준선 후보 정보를 확인할 수 있습니다."
            : "추가로 처리할 기준선 변경이 없습니다.",
    };
}


async function scanOneServer(server) {
    const includeTrustedProjectConfig =
        mcpUiState.serverCatalog.loadedIncludeTrustedProjectConfig ??
        mcpUiState.serverCatalog.includeTrustedProjectConfig;
    const selectionId = encodeURIComponent(server.selectionId);

    return apiFetch(
        `/api/mcp/servers/${selectionId}/scan`,
        {
            method: "POST",
            json: {
                include_trusted_project_config: includeTrustedProjectConfig,
                // 이전에 거절한 스냅샷과 동일하더라도
                // 이번 검사 결과를 다시 승인 대기 후보로 만들 수 있게 요청한다.
                reconsider_rejected: true,
            },
        }
    );
}


function upsertServerFromScanResponse(response) {
    const selectionId =
        response?.server?.selection_id ||
        response?.identity?.selection_id;

    if (!selectionId) {
        return;
    }

    const index = mcpUiState.serverCatalog.servers.findIndex(
        (server) => server.selectionId === selectionId
    );
    const existingServer = index >= 0
        ? mcpUiState.serverCatalog.servers[index]
        : null;
    const normalized = normalizeServerFromScanResponse(
        response,
        existingServer
    );

    if (index >= 0) {
        mcpUiState.serverCatalog.servers[index] = normalized;
    } else {
        mcpUiState.serverCatalog.servers.push(normalized);
        mcpUiState.serverCatalog.total =
            mcpUiState.serverCatalog.servers.length;
    }

    if (normalized.monitoringTargetKey) {
        mcpUiState.serverManagement.targetDetailsByKey.set(
            normalized.monitoringTargetKey,
            response.monitoring_state
        );
    }
}


function isBatchBlockingError(error) {
    if (!error) {
        return false;
    }

    if (
        error.errorCode === "request_token_invalid" ||
        error.errorCode === "origin_not_allowed" ||
        error.errorCode === "host_not_allowed"
    ) {
        return true;
    }

    return error instanceof TypeError;
}


function isFailedScanStatus(status) {
    return status === "failed" || status === "timed_out";
}


function countFinishedScanStatuses() {
    let count = 0;

    for (const status of mcpUiState.scanBatch.statusesBySelectionId.values()) {
        if (
            status.status === "completed" ||
            status.status === "failed" ||
            status.status === "skipped"
        ) {
            count += 1;
        }
    }

    return count;
}


function getSelectedScannableServers() {
    return mcpUiState.serverCatalog.servers.filter(
        (server) =>
            server.canScan &&
            mcpUiState.selection.selectedServerIds.has(server.selectionId)
    );
}


function renderAllMcpViews() {
    updateDashboardFromMcpState();
    renderScanDetail();
    renderScanPhaseSections();
    renderScanServerList();
    renderScanProgressPanel();
    renderServerManagementList();
    renderServerManagementDetail();
    renderCandidateReview();
    renderBaselineHistoryServerList();
    renderBaselineHistoryList();
    updateMcpControls();
}


function updateDashboardFromMcpState() {
    const servers = getDashboardResultServers();
    const counts = {
        safe: 0,
        warning: 0,
        danger: 0,
    };
    const attentionItems = [];

    for (const server of servers) {
        const scanResult = mcpUiState.scanBatch.resultsBySelectionId.get(
            server.selectionId
        );
        const securityClassification = classifySecurityFindingStatus(
            scanResult
        );

        if (securityClassification.counted) {
            counts[securityClassification.status] += 1;
        }

        attentionItems.push(
            ...createDashboardAttentionItems(
                server,
                scanResult,
                securityClassification
            )
        );
    }

    attentionItems.sort(compareAttentionItems);

    dashboardState.counts = counts;
    dashboardState.attentionItems = attentionItems;
    dashboardState.lastUpdatedAt =
        mcpUiState.scanBatch.completedAt ||
        mcpUiState.serverCatalog.lastLoadedAt;

    if (mcpUiState.serverCatalog.error) {
        dashboardState.status = "warning";
        dashboardState.label = "목록 조회 실패";
        dashboardState.headline = "서버 목록을 불러오지 못했습니다.";
        dashboardState.description =
            "서버 목록 새로고침을 다시 시도해 주세요.";
    } else if (servers.length === 0) {
        dashboardState.status = "idle";
        dashboardState.label = "결과 대기";
        dashboardState.headline = "표시할 검사 결과가 없습니다.";
        dashboardState.description =
            "검사 시작 화면에서 서버를 선택해 검사를 실행하세요.";
    } else if (counts.danger > 0) {
        dashboardState.status = "danger";
        dashboardState.label = "위험";
        dashboardState.headline = "즉시 확인이 필요해요";
        dashboardState.description =
            "Critical 또는 High Finding이 발견된 MCP 서버가 있습니다.";
    } else if (counts.warning > 0) {
        dashboardState.status = "warning";
        dashboardState.label = "주의";
        dashboardState.headline = "확인이 필요한 항목이 있어요";
        dashboardState.description =
            "Medium 또는 Low Finding이 발견된 MCP 서버가 있습니다.";
    } else if (counts.safe > 0) {
        dashboardState.status = "safe";
        dashboardState.label = "안전";
        dashboardState.headline = "현재 상태가 양호해요";
        dashboardState.description =
            "이번 검사에서 보안 Finding이 발견되지 않았습니다.";
    } else if (servers.length > 0) {
        dashboardState.status = "idle";
        dashboardState.label = "결과 없음";
        dashboardState.headline = "표시할 Finding 결과가 없습니다.";
        dashboardState.description =
            "보안 Finding 결과가 있는 검사만 안전/주의/위험에 반영됩니다.";
    }

    renderDashboardSummary(dashboardState);
}


function getDashboardResultServers() {
    const completedIds = new Set(
        (mcpUiState.scanBatch.completedItems || [])
            .map((item) => item.selectionId)
            .filter(Boolean)
    );

    if (!completedIds.size) {
        return [];
    }

    return mcpUiState.serverCatalog.servers.filter((server) =>
        completedIds.has(server.selectionId)
    );
}


function normalizeDashboardStatus(status) {
    if (status === "danger" || status === "safe") {
        return status;
    }

    return "warning";
}


function classifySecurityFindingStatus(scanResult) {
    const hasScanResult = Boolean(
        scanResult?.dynamic_scan_result?.scan_result
    );
    const severity = getSeveritySummary(scanResult);

    return classifySeveritySummary(severity, hasScanResult);
}


function classifySeveritySummary(
    severity,
    hasScanResult
) {
    const dangerFindingCount = severity.critical + severity.high;
    const warningFindingCount = severity.medium + severity.low;

    if (!hasScanResult) {
        return {
            status: "unscanned",
            reason: "보안 Finding 결과가 생성되지 않았습니다.",
            priority: 4,
            counted: false,
            dangerFindingCount,
            warningFindingCount,
        };
    }

    if (dangerFindingCount > 0) {
        return {
            status: "danger",
            reason: `위험 Finding ${dangerFindingCount}건이 발견되었습니다.`,
            priority: 1,
            counted: true,
            dangerFindingCount,
            warningFindingCount,
        };
    }

    if (warningFindingCount > 0) {
        return {
            status: "warning",
            reason: `주의 Finding ${warningFindingCount}건이 발견되었습니다.`,
            priority: 3,
            counted: true,
            dangerFindingCount,
            warningFindingCount,
        };
    }

    return {
        status: "safe",
        reason: "이번 검사에서 보안 Finding이 발견되지 않았습니다.",
        priority: 5,
        counted: true,
        dangerFindingCount,
        warningFindingCount,
    };
}


function createDashboardAttentionItems(
    server,
    scanResult,
    securityClassification
) {
    const items = [];

    if (
        securityClassification.status === "danger" ||
        securityClassification.status === "warning"
    ) {
        items.push({
            status: securityClassification.status,
            title: securityClassification.reason,
            serverName: server.serverName,
            selectionId: server.selectionId,
            monitoringTargetKey: server.monitoringTargetKey,
            actionType: "management",
            actionLabel: "서버 보기",
            priority: securityClassification.priority,
            category: "security",
        });
    }

    if (!items.length && securityClassification.status === "safe") {
        items.push({
            status: "safe",
            title: securityClassification.reason,
            serverName: server.serverName,
            selectionId: server.selectionId,
            monitoringTargetKey: server.monitoringTargetKey,
            actionType: "management",
            actionLabel: "서버 보기",
            priority: securityClassification.priority,
            category: "security",
        });
    }

    return items;
}


function classifyServerStatus(
    server,
    currentSessionScanResult = null
) {
    const hasCurrentScanResult = Boolean(
        currentSessionScanResult?.dynamic_scan_result?.scan_result
    );

    if (hasCurrentScanResult) {
        return classifySecurityFindingStatus(currentSessionScanResult);
    }

    if (server?.lastFindingSummary) {
        return classifySeveritySummary(server.lastFindingSummary, true);
    }

    return classifySecurityFindingStatus(null);
}


function buildServerListPresentation(server) {
    const currentSessionScanResult =
        mcpUiState.scanBatch.resultsBySelectionId.get(server.selectionId);
    const securityClassification = classifyServerStatus(
        server,
        currentSessionScanResult
    );
    const badges = [];

    if (securityClassification.counted) {
        badges.push({
            tone: securityClassification.status,
            label: displayRepresentativeStatus(securityClassification.status),
            title: securityClassification.reason,
        });
    }

    badges.push(getServerScanStatusBadge(server, currentSessionScanResult));

    return {
        badges,
        reason: !server.canScan
            ? server.safeActionReason || "검사 불가"
            : "",
    };
}


function getServerScanStatusBadge(
    server,
    currentSessionScanResult = null
) {
    const dynamicStatus =
        currentSessionScanResult?.dynamic_scan_result?.status || null;
    const resultState = currentSessionScanResult?.monitoring_state || null;
    const status =
        dynamicStatus ||
        resultState?.last_scan_status ||
        server.lastScanStatus ||
        "not_scanned";

    if (!server.canScan) {
        return {
            tone: "warning",
            label: "검사 불가",
            title: server.safeActionReason || "이 서버는 검사할 수 없습니다.",
        };
    }

    return {
        tone: scanStatusBadgeTone(status),
        label: displayScanStatus(status),
        title: "서버의 최근 검사 실행 상태입니다.",
    };
}


function scanStatusBadgeTone(status) {
    if (status === "success" || status === "partial_success") {
        return "safe";
    }

    if (status === "failed" || status === "timed_out") {
        return "danger";
    }

    if (status === "scanning") {
        return "warning";
    }

    return "neutral";
}


function appendServerListBadges(
    container,
    badges
) {
    container.replaceChildren();

    for (const badge of badges) {
        const element = createStatusBadge(badge.tone, badge.label);
        if (badge.title) {
            element.title = badge.title;
        }
        container.appendChild(element);
    }
}


function getSeveritySummary(scanResult) {
    const severity =
        scanResult?.dynamic_scan_result?.scan_result?.summary?.by_severity;

    return {
        critical: numberOrZero(severity?.critical),
        high: numberOrZero(severity?.high),
        medium: numberOrZero(severity?.medium),
        low: numberOrZero(severity?.low),
        info: numberOrZero(severity?.info),
    };
}


function numberOrZero(value) {
    return typeof value === "number" && Number.isFinite(value)
        ? value
        : 0;
}


function createAttentionModel(
    server,
    classification,
    options = {}
) {
    if (classification.status === "safe" && !options.includeSafe) {
        return null;
    }

    const scanResult = mcpUiState.scanBatch.resultsBySelectionId.get(
        server.selectionId
    );

    if (scanResult) {
        return createScanResultAttentionModel(
            server,
            scanResult,
            classification
        );
    }

    const state = server.rawMonitoringState || scanResult?.monitoring_state;
    const allowScanPrompt = options.allowScanPrompt !== false;
    let status = classification.status;
    let title = classification.reason;
    let actionType = "management";
    let actionLabel = "서버 보기";
    let priority = classification.priority;

    if (
        state?.last_scan_status === "failed" ||
        scanResult?.dynamic_scan_result?.status === "failed"
    ) {
        status = "failed";
        title = "검사 실패 상태입니다.";
        priority = 2;
    } else if (
        state?.last_scan_status === "timed_out" ||
        scanResult?.dynamic_scan_result?.status === "timed_out"
    ) {
        status = "timed_out";
        title = "검사 시간이 초과되었습니다.";
        priority = 2;
    } else if (state?.baseline_lifecycle === "candidate_pending") {
        status = "candidate";
        title = "기준선 승인 대기 상태입니다.";
        priority = 3;
    } else if (state?.baseline_lifecycle === "rejected") {
        status = "rejected";
        title = "기준선 거절 상태입니다.";
        priority = 3;
    } else if (classification.status === "unscanned" && allowScanPrompt) {
        status = "unscanned";
        title = "검사가 필요합니다.";
        actionType = "scan";
        actionLabel = "검사 시작";
        priority = 4;
    } else if (classification.status === "warning") {
        status = "warning";
        title = title || "검토가 필요한 상태입니다.";
        priority = Math.min(priority, 3);
    } else if (!server.canScan) {
        status = "warning";
        title = "검사 불가 상태입니다.";
        priority = 3;
    }

    return {
        status,
        title,
        serverName: server.serverName,
        selectionId: server.selectionId,
        monitoringTargetKey: server.monitoringTargetKey,
        actionType,
        actionLabel,
        priority,
    };
}


function createScanResultAttentionModel(
    server,
    scanResult,
    classification
) {
    const securityClassification =
        classifySecurityFindingStatus(scanResult);
    let status = securityClassification.status;
    let title = securityClassification.reason;
    let priority = securityClassification.priority;

    if (status === "unscanned") {
        status = normalizeDashboardStatus(classification.status);
        title = classification.reason;
        priority = classification.priority;
    }

    return {
        status,
        title,
        serverName: server.serverName,
        selectionId: server.selectionId,
        monitoringTargetKey: server.monitoringTargetKey,
        actionType: "management",
        actionLabel: "서버 보기",
        priority,
    };
}


function compareAttentionItems(left, right) {
    if (left.priority !== right.priority) {
        return left.priority - right.priority;
    }

    return left.serverName.localeCompare(
        right.serverName,
        "ko"
    );
}


function limitAttentionItems(items) {
    const limit = 5;

    if (items.length <= limit) {
        return items;
    }

    return [
        ...items.slice(0, limit),
        {
            status: "warning",
            title: `추가 항목 ${items.length - limit}개`,
            serverName: "추가 확인 필요",
            actionType: "none",
            actionLabel: "서버 보기",
            priority: 9,
        },
    ];
}


function renderScanServerList() {
    elements.scanServerList.replaceChildren();

    if (mcpUiState.serverCatalog.loading) {
        elements.scanServerList.appendChild(
            createEmptyState(
                "서버 목록을 불러오는 중입니다.",
                "잠시만 기다려 주세요."
            )
        );
        setScanServerStatus("서버 목록을 불러오는 중입니다.", false);
        return;
    }

    if (mcpUiState.serverCatalog.error) {
        elements.scanServerList.appendChild(
            createEmptyState(
                "서버 목록을 불러오지 못했습니다.",
                "서버 목록 새로고침을 다시 시도해 주세요."
            )
        );
        setScanServerStatus(mcpUiState.serverCatalog.error, true);
        return;
    }

    if (!mcpUiState.serverCatalog.servers.length) {
        elements.scanServerList.appendChild(
            createEmptyState(
                "등록된 MCP 서버를 불러오면",
                "검사 가능한 서버가 여기에 표시됩니다."
            )
        );
        setScanServerStatus("", false);
        return;
    }

    for (const server of mcpUiState.serverCatalog.servers) {
        elements.scanServerList.appendChild(
            createScanServerListItem(server)
        );
    }

    if (
        mcpUiState.serverCatalog.loadedIncludeTrustedProjectConfig !== null &&
        mcpUiState.serverCatalog.loadedIncludeTrustedProjectConfig !==
            mcpUiState.serverCatalog.includeTrustedProjectConfig
    ) {
        setScanServerStatus(
            "프로젝트 설정 포함 변경 사항은 서버 목록 새로고침 후 적용됩니다.",
            false
        );
    } else if (mcpUiState.scanBatch.error) {
        setScanServerStatus(mcpUiState.scanBatch.error, true);
    } else {
        setScanServerStatus("", false);
    }
}


function renderScanPhaseSections() {
    const phase = mcpUiState.scanBatch.phase || "setup";

    elements.scanSetupSection.hidden = phase !== "setup";
    elements.scanRunningSection.hidden = phase !== "running";
}


function createCompletedResultCard(item) {
    const card = document.createElement("article");
    const header = document.createElement("div");
    const title = document.createElement("strong");
    const badge = createStatusBadge(item.badgeTone, item.badgeLabel);
    const status = document.createElement("span");
    const headline = document.createElement("p");
    const description = document.createElement("p");
    const severity = document.createElement("p");
    const actions = document.createElement("div");

    card.className = "scan-result-card";
    header.className = "scan-result-card-header";
    title.textContent = item.serverName || item.selectionId;
    status.className = "scan-result-status";
    status.textContent = `검사 상태: ${displayScanStatus(item.scanStatus)}`;
    headline.className = "scan-result-headline";
    headline.textContent = item.headline;
    description.className = "scan-result-description";
    description.textContent = item.description;
    severity.className = "scan-result-severity";
    severity.textContent = formatSeveritySummary(item.severity);
    actions.className = "scan-result-actions";

    header.appendChild(title);
    header.appendChild(badge);
    card.appendChild(header);
    card.appendChild(status);
    card.appendChild(headline);
    card.appendChild(description);
    card.appendChild(severity);

    if (
        item.resultType === "candidate_created" ||
        item.resultType === "candidate_reused"
    ) {
        const candidateButton = document.createElement("button");

        candidateButton.className = "secondary-button";
        candidateButton.type = "button";
        candidateButton.textContent = item.resultType === "candidate_created"
            ? "후보 검토하기"
            : "기존 후보 확인하기";
        candidateButton.addEventListener(
            "click",
            () => openCandidateReviewFromResult(item)
        );
        actions.appendChild(candidateButton);
    }

    const detailButton = document.createElement("button");

    detailButton.className = "secondary-button";
    detailButton.type = "button";
    detailButton.textContent = "상세 결과 보기";
    detailButton.addEventListener(
        "click",
        () => openScanDetailFromResult(item)
    );
    actions.appendChild(detailButton);
    card.appendChild(actions);

    return card;
}


function formatSeveritySummary(severity) {
    return [
        `Critical ${numberOrZero(severity?.critical)}`,
        `High ${numberOrZero(severity?.high)}`,
        `Medium ${numberOrZero(severity?.medium)}`,
        `Low ${numberOrZero(severity?.low)}`,
    ].join(" / ");
}


function resetScanBatchForNewScan() {
    mcpUiState.scanBatch.phase = "setup";
    mcpUiState.scanBatch.running = false;
    mcpUiState.scanBatch.currentIndex = 0;
    mcpUiState.scanBatch.total = 0;
    mcpUiState.scanBatch.currentSelectionId = null;
    mcpUiState.scanBatch.statusesBySelectionId.clear();
    mcpUiState.scanBatch.resultsBySelectionId.clear();
    mcpUiState.scanBatch.completedItems = [];
    mcpUiState.scanBatch.completedAt = null;
    mcpUiState.scanBatch.error = null;
    mcpUiState.selection.selectedServerIds.clear();
    renderAllMcpViews();
}


function selectFailedCompletedServersForRetry() {
    const failedIds = mcpUiState.scanBatch.completedItems
        .filter((item) =>
            item.resultType === "failed" || item.resultType === "timed_out"
        )
        .map((item) => item.selectionId);

    mcpUiState.selection.selectedServerIds = new Set(failedIds);
    mcpUiState.scanBatch.phase = "setup";
    mcpUiState.scanBatch.running = false;
    renderAllMcpViews();
    showView(
        "scan-start",
        {
            focusTitle: true,
        }
    );
}


function openServerManagementFromResult(item) {
    showView(
        "server-management",
        {
            focusTitle: true,
        }
    );
    selectServerForManagement(item.selectionId);
}


function openCandidateReviewFromResult(item) {
    openServerManagementFromResult(item);

    if (item.candidateId) {
        mcpUiState.candidateReview.selectedCandidateId = item.candidateId;
        mcpUiState.candidateReview.expandedCandidateId = item.candidateId;
        maybeLoadSelectedCandidateDetail();
        renderCandidateReview();
    }

    focusCandidateReviewSection();
}


function focusCandidateReviewSection() {
    const section = document.getElementById("candidate-review-section");

    if (!section) {
        return;
    }

    section.scrollIntoView({
        block: "start",
        behavior: "smooth",
    });
    section.setAttribute("tabindex", "-1");
    section.focus({
        preventScroll: true,
    });
}


function createScanServerListItem(server) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    const content = document.createElement("span");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const badges = document.createElement("span");
    const reason = document.createElement("span");
    const presentation = buildServerListPresentation(server);

    label.className = "server-select-item";
    label.classList.toggle(
        "is-selected",
        mcpUiState.selection.selectedServerIds.has(server.selectionId)
    );
    label.classList.toggle("is-disabled", !server.canScan);

    checkbox.type = "checkbox";
    checkbox.value = server.selectionId;
    checkbox.dataset.selectionId = server.selectionId;
    checkbox.checked = mcpUiState.selection.selectedServerIds.has(
        server.selectionId
    );
    checkbox.disabled = !server.canScan || mcpUiState.scanBatch.running;
    checkbox.addEventListener(
        "change",
        () => setServerSelected(
            server.selectionId,
            checkbox.checked
        )
    );

    content.className = "server-select-copy";
    title.textContent = server.serverName;

    meta.className = "server-identity-row";
    appendLabeledMetaText(meta, "제품", displayProduct(server.product));
    appendLabeledMetaText(meta, "범위", displayScope(server.scope));

    badges.className = "server-badge-row";
    appendServerListBadges(badges, presentation.badges);

    content.appendChild(title);
    content.appendChild(meta);
    content.appendChild(badges);

    if (!server.canScan) {
        reason.className = "server-safe-reason";
        reason.textContent = presentation.reason || "검사 불가";
        content.appendChild(reason);
    }

    label.appendChild(checkbox);
    label.appendChild(content);

    return label;
}


function appendMetaText(container, text) {
    const item = document.createElement("span");

    item.textContent = text;
    container.appendChild(item);
}


function getBatchStatusForServer(selectionId) {
    return (
        mcpUiState.scanBatch.statusesBySelectionId.get(selectionId) ||
        null
    );
}


function renderScanProgressPanel() {
    const batch = mcpUiState.scanBatch;

    elements.scanProgressPanel.hidden =
        !batch.running && batch.total === 0 && !batch.completedAt;

    if (elements.scanProgressPanel.hidden) {
        return;
    }

    const completedCount = countFinishedScanStatuses();

    elements.scanProgressCurrent.textContent = String(completedCount);
    elements.scanProgressTotal.textContent = String(batch.total);
    elements.scanProgressBar.max = batch.total;
    elements.scanProgressBar.value = completedCount;
    elements.scanProgressBar.setAttribute("aria-valuemin", "0");
    elements.scanProgressBar.setAttribute(
        "aria-valuemax",
        String(batch.total)
    );
    elements.scanProgressBar.setAttribute(
        "aria-valuenow",
        String(completedCount)
    );

    if (batch.running) {
        elements.scanProgressLabel.textContent =
            "선택한 MCP 서버를 순서대로 검사하고 있습니다.";
    } else if (batch.error) {
        elements.scanProgressLabel.textContent =
            "일부 검사를 완료하지 못했습니다.";
    } else {
        elements.scanProgressLabel.textContent =
            "선택한 MCP 서버 검사가 완료되었습니다.";
    }

    const currentServer = findServerBySelectionId(batch.currentSelectionId);
    elements.scanCurrentServerName.textContent =
        currentServer?.serverName || "-";

    elements.scanProgressServerList.replaceChildren();

    for (const server of mcpUiState.serverCatalog.servers) {
        const status = mcpUiState.scanBatch.statusesBySelectionId.get(
            server.selectionId
        );

        if (!status) {
            continue;
        }

        const item = document.createElement("div");
        const name = document.createElement("strong");
        const message = document.createElement("span");

        item.className = "progress-server-item";
        name.textContent = server.serverName;
        message.textContent = status.message || progressStatusLabelByValue[
            status.status
        ];

        item.appendChild(name);
        item.appendChild(createProgressBadge(status.status));
        item.appendChild(message);
        elements.scanProgressServerList.appendChild(item);
    }
}


function renderServerManagementList() {
    elements.serverManagementList.replaceChildren();

    if (mcpUiState.serverCatalog.loading) {
        elements.serverManagementList.appendChild(
            createEmptyState(
                "서버 목록을 불러오는 중입니다.",
                "잠시만 기다려 주세요."
            )
        );
        setInlineMessage(
            elements.serverManagementStatus,
            elements.serverManagementError,
            "서버 목록을 불러오는 중입니다.",
            false
        );
        return;
    }

    if (mcpUiState.serverCatalog.error) {
        elements.serverManagementList.appendChild(
            createEmptyState(
                "표시할 MCP 서버를 불러오지 못했습니다.",
                "검사 시작 화면에서 서버 목록 새로고침을 다시 시도해 주세요."
            )
        );
        setInlineMessage(
            elements.serverManagementStatus,
            elements.serverManagementError,
            mcpUiState.serverCatalog.error,
            true
        );
        return;
    }

    if (!mcpUiState.serverCatalog.servers.length) {
        elements.serverManagementList.appendChild(
            createEmptyState(
                "표시할 MCP 서버가 없습니다.",
                "서버 목록을 새로고침하면 등록된 서버가 여기에 표시됩니다."
            )
        );
        setInlineMessage(
            elements.serverManagementStatus,
            elements.serverManagementError,
            "",
            false
        );
        return;
    }

    for (const server of mcpUiState.serverCatalog.servers) {
        elements.serverManagementList.appendChild(
            createServerManagementListItem(server)
        );
    }

    setInlineMessage(
        elements.serverManagementStatus,
        elements.serverManagementError,
        "",
        false
    );
}


function createServerManagementListItem(server) {
    const button = document.createElement("button");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const badges = document.createElement("span");
    const presentation = buildServerListPresentation(server);

    button.className = "server-management-item";
    button.type = "button";
    button.dataset.selectionId = server.selectionId;

    if (
        mcpUiState.serverManagement.selectedSelectionId ===
        server.selectionId
    ) {
        button.classList.add("is-selected");
        button.setAttribute("aria-current", "true");
    }

    title.textContent = server.serverName;

    meta.className = "server-identity-row";
    appendLabeledMetaText(meta, "제품", displayProduct(server.product));
    appendLabeledMetaText(meta, "범위", displayScope(server.scope));

    badges.className = "server-badge-row";
    appendServerListBadges(badges, presentation.badges);

    button.appendChild(title);
    button.appendChild(meta);
    button.appendChild(badges);
    button.addEventListener(
        "click",
        () => selectServerForManagement(server.selectionId)
    );

    return button;
}


function selectServerForManagement(selectionId) {
    const selectionChanged =
        mcpUiState.serverManagement.selectedSelectionId !== selectionId;

    mcpUiState.serverManagement.selectedSelectionId = selectionId;
    mcpUiState.serverManagement.error = null;

    if (selectionChanged) {
        resetCandidateReviewStateForServerChange();
        resetBaselineRevocationStateForServerChange();
    }

    renderAllMcpViews();

    const server = findServerBySelectionId(selectionId);

    if (
        server?.monitoringTargetKey &&
        hasPersistedMonitoringState(server)
    ) {
        loadTargetDetails(
            server.monitoringTargetKey,
            selectionId
        );
    } else {
        ensureCandidateSelectionForCurrentServer();
    }
}


async function loadTargetDetails(
    monitoringTargetKey,
    selectionId
) {
    if (
        mcpUiState.serverManagement.targetDetailsByKey.has(
            monitoringTargetKey
        )
    ) {
        renderServerManagementDetail();
        ensureCandidateSelectionForCurrentServer();
        return;
    }

    mcpUiState.serverManagement.loadingTargetKey = monitoringTargetKey;
    mcpUiState.serverManagement.error = null;
    renderServerManagementDetail();

    try {
        const payload = await apiFetch(
            `/api/mcp/targets/${encodeURIComponent(monitoringTargetKey)}`
        );

        mcpUiState.serverManagement.targetDetailsByKey.set(
            monitoringTargetKey,
            payload
        );

        if (
            mcpUiState.serverManagement.selectedSelectionId === selectionId
        ) {
            mcpUiState.serverManagement.error = null;
        }
    } catch (error) {
        if (
            mcpUiState.serverManagement.selectedSelectionId === selectionId
        ) {
            if (isMonitoringNotFoundError(error)) {
                mcpUiState.serverManagement.targetDetailsByKey.set(
                    monitoringTargetKey,
                    null
                );
                mcpUiState.serverManagement.error = null;
            } else {
                mcpUiState.serverManagement.error = getErrorMessage(
                    error,
                    "서버 상세 정보를 불러오지 못했습니다."
                );
            }
        }
    } finally {
        if (
            mcpUiState.serverManagement.loadingTargetKey ===
            monitoringTargetKey
        ) {
            mcpUiState.serverManagement.loadingTargetKey = null;
        }

        renderServerManagementDetail();
        ensureCandidateSelectionForCurrentServer();
    }
}


function renderServerManagementDetail() {
    const selectedServer = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );

    if (!selectedServer) {
        elements.serverManagementDetailEmpty.hidden = false;
        elements.serverManagementDetailEmpty.textContent =
            "왼쪽 목록에서 서버를 선택하세요.";
        elements.serverManagementDetailContent.hidden = true;
        return;
    }

    if (mcpUiState.serverManagement.error) {
        elements.serverManagementDetailEmpty.hidden = false;
        elements.serverManagementDetailEmpty.textContent =
            mcpUiState.serverManagement.error;
        elements.serverManagementDetailContent.hidden = true;
        return;
    }

    const detail = selectedServer.monitoringTargetKey
        ? mcpUiState.serverManagement.targetDetailsByKey.get(
            selectedServer.monitoringTargetKey
        )
        : null;
    const state = detail || selectedServer.rawMonitoringState || {};
    const safeSummary = getLatestSafeSummary(selectedServer);
    const loadingCurrent =
        selectedServer.monitoringTargetKey &&
        mcpUiState.serverManagement.loadingTargetKey ===
            selectedServer.monitoringTargetKey;

    elements.serverManagementDetailEmpty.hidden = true;
    elements.serverManagementDetailContent.hidden = false;

    setText(elements.serverName, selectedServer.serverName);
    setText(elements.serverProduct, displayProduct(selectedServer.product));
    setText(elements.serverScope, displayScope(selectedServer.scope));
    setText(elements.serverTransport, displayTransport(selectedServer.transport));
    setText(
        elements.serverEnabledState,
        displayEnabledState(selectedServer.enabledState)
    );
    setText(
        elements.serverSupportState,
        displaySupportState(selectedServer.supportState)
    );
    setText(
        elements.serverCanScan,
        selectedServer.canScan ? "검사 가능" : "검사 불가"
    );
    setText(
        elements.serverLastScanStatus,
        loadingCurrent
            ? "조회 중"
            : displayScanStatus(
                state.last_scan_status || selectedServer.lastScanStatus
            )
    );
    setDateText(
        elements.serverLastScanAt,
        state.last_scan_at || selectedServer.lastScanAt
    );
    setText(
        elements.serverBaselineLifecycle,
        displayBaselineLifecycle(
            state.baseline_lifecycle || selectedServer.baselineLifecycle
        )
    );
    setText(
        elements.serverComparisonStatus,
        displayComparisonStatus(
            state.comparison_status || selectedServer.comparisonStatus
        )
    );
    setText(
        elements.serverVerificationStatus,
        displayVerificationStatus(
            state.verification_status || selectedServer.verificationStatus
        )
    );
    setText(
        elements.serverCommandBasename,
        selectedServer.commandBasename
    );
    setText(
        elements.serverArgumentCount,
        selectedServer.argumentCount
    );
    setText(
        elements.serverEnvReferenceCount,
        valueOrDash(safeSummary?.env_reference_count)
    );
    setText(
        elements.serverRemoteOrigin,
        selectedServer.remoteOrigin
    );
    setText(
        elements.serverTlsVerified,
        displayBooleanValue(safeSummary?.verify_tls)
    );
    setText(
        elements.serverCurrentApprovedId,
        state.current_approved_id || selectedServer.currentApprovedId
    );
    renderBaselineRevocationControls(selectedServer, state);
}


function resetBaselineRevocationStateForServerChange() {
    if (mcpUiState.baselineRevoke.running) {
        return;
    }

    mcpUiState.baselineRevoke.panelOpen = false;
    mcpUiState.baselineRevoke.targetKey = null;
    mcpUiState.baselineRevoke.baselineId = null;
    mcpUiState.baselineRevoke.error = null;
    mcpUiState.baselineRevoke.success = null;
}


function renderBaselineRevocationControls(server, state) {
    const revoke = mcpUiState.baselineRevoke;
    const currentApprovedId =
        state.current_approved_id || server.currentApprovedId || null;
    const stateVersion = state.state_version ?? server.stateVersion;
    const tokenReady = Boolean(
        mcpUiState.security.token && mcpUiState.security.headerName
    );
    const canRevoke = Boolean(currentApprovedId) &&
        typeof stateVersion === "number" &&
        tokenReady &&
        !mcpUiState.candidateReview.decisionRunning &&
        !revoke.running;

    elements.serverRevokeBaselineButton.hidden = !currentApprovedId;
    setButtonDisabled(elements.serverRevokeBaselineButton, !canRevoke);
    renderBaselineRevocationPanel(server, state);

    if (revoke.success) {
        setInlineMessage(
            elements.serverManagementStatus,
            elements.serverManagementError,
            revoke.success,
            false
        );
    }
}


function startBaselineRevocation() {
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const state = getTargetStateForServer(server);
    const currentApprovedId =
        state?.current_approved_id || server?.currentApprovedId || null;

    if (
        !server?.monitoringTargetKey ||
        !currentApprovedId ||
        mcpUiState.baselineRevoke.running
    ) {
        return;
    }

    mcpUiState.baselineRevoke.panelOpen = true;
    mcpUiState.baselineRevoke.targetKey = server.monitoringTargetKey;
    mcpUiState.baselineRevoke.baselineId = currentApprovedId;
    mcpUiState.baselineRevoke.error = null;
    mcpUiState.baselineRevoke.success = null;
    elements.baselineRevokeReasonCode.value = "";
    renderServerManagementDetail();
}


function clearBaselineRevocationPanel() {
    if (mcpUiState.baselineRevoke.running) {
        return;
    }

    mcpUiState.baselineRevoke.panelOpen = false;
    mcpUiState.baselineRevoke.targetKey = null;
    mcpUiState.baselineRevoke.baselineId = null;
    mcpUiState.baselineRevoke.error = null;
    renderServerManagementDetail();
}


function renderBaselineRevocationPanel(server, state) {
    const revoke = mcpUiState.baselineRevoke;

    if (!revoke.panelOpen || !revoke.targetKey || !revoke.baselineId) {
        elements.baselineRevokePanel.hidden = true;
        return;
    }

    elements.baselineRevokePanel.hidden = false;
    elements.baselineRevokeSummary.replaceChildren();
    appendDefinition(
        elements.baselineRevokeSummary,
        "서버 이름",
        server?.serverName
    );
    appendDefinition(
        elements.baselineRevokeSummary,
        "현재 승인 기준선",
        compactIdentifier(revoke.baselineId)
    );
    appendDefinition(
        elements.baselineRevokeSummary,
        "현재 State Version",
        state?.state_version ?? server?.stateVersion
    );

    elements.baselineRevokeReasonCode.disabled = revoke.running;
    setButtonDisabled(elements.baselineRevokeConfirmButton, revoke.running);
    setButtonDisabled(elements.baselineRevokeCancelButton, revoke.running);
    elements.baselineRevokeConfirmButton.textContent = revoke.running
        ? "기준선 삭제 처리 중..."
        : "기준선 삭제 확인";

    if (revoke.error) {
        elements.baselineRevokeError.hidden = false;
        elements.baselineRevokeError.textContent = revoke.error;
    } else {
        elements.baselineRevokeError.hidden = true;
        elements.baselineRevokeError.textContent = "";
    }
}


async function submitBaselineRevocation() {
    const revoke = mcpUiState.baselineRevoke;
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const reasonCode = elements.baselineRevokeReasonCode.value.trim();

    if (
        !server?.monitoringTargetKey ||
        !revoke.baselineId ||
        revoke.running
    ) {
        return;
    }

    if (reasonCode && !/^[a-z0-9_]{1,64}$/.test(reasonCode)) {
        revoke.error = "처리 사유 코드 형식을 확인해 주세요.";
        renderServerManagementDetail();
        return;
    }

    revoke.running = true;
    revoke.error = null;
    revoke.success = null;
    renderServerManagementDetail();

    try {
        const latestState = await fetchLatestTargetStateForBaselineRevocation(
            server.monitoringTargetKey
        );
        const latestApprovedId = latestState.current_approved_id;

        if (!latestApprovedId || latestApprovedId !== revoke.baselineId) {
            revoke.error =
                "서버 상태 또는 승인 기준선이 변경되어 삭제하지 못했습니다. 최신 상태를 확인한 뒤 다시 시도해 주세요.";
            await refreshAfterBaselineRevocation(
                server.monitoringTargetKey,
                server.selectionId,
                {
                    keepPanel: true,
                }
            );
            return;
        }

        await apiFetch(
            `/api/mcp/targets/${encodeURIComponent(server.monitoringTargetKey)}/baseline/revoke`,
            {
                method: "POST",
                json: {
                    expected_state_version: latestState.state_version,
                    expected_current_approved_id: latestApprovedId,
                    safe_reason_code: reasonCode || null,
                },
            }
        );

        revoke.panelOpen = false;
        revoke.targetKey = null;
        revoke.baselineId = null;
        revoke.success = "현재 승인 기준선을 삭제했습니다.";
        await refreshAfterBaselineRevocation(
            server.monitoringTargetKey,
            server.selectionId
        );
    } catch (error) {
        await handleBaselineRevocationError(
            error,
            server.monitoringTargetKey,
            server.selectionId
        );
    } finally {
        revoke.running = false;
        renderAllMcpViews();
    }
}


async function fetchLatestTargetStateForBaselineRevocation(monitoringTargetKey) {
    const state = await apiFetch(
        `/api/mcp/targets/${encodeURIComponent(monitoringTargetKey)}`
    );

    mcpUiState.serverManagement.targetDetailsByKey.set(
        monitoringTargetKey,
        state
    );

    return state;
}


async function handleBaselineRevocationError(
    error,
    monitoringTargetKey,
    selectionId
) {
    if (error.statusCode === 409) {
        mcpUiState.baselineRevoke.error =
            "서버 상태 또는 승인 기준선이 변경되어 삭제하지 못했습니다. 최신 상태를 확인한 뒤 다시 시도해 주세요.";
        await refreshAfterBaselineRevocation(
            monitoringTargetKey,
            selectionId,
            {
                keepPanel: true,
            }
        );
        return;
    }

    if (isMonitoringNotFoundError(error)) {
        mcpUiState.baselineRevoke.error =
            "현재 승인 기준선을 찾을 수 없습니다.";
        await refreshAfterBaselineRevocation(
            monitoringTargetKey,
            selectionId,
            {
                keepPanel: true,
            }
        );
        return;
    }

    if (error.statusCode === 422) {
        mcpUiState.baselineRevoke.error =
            "처리 사유 코드 형식을 확인해 주세요.";
        return;
    }

    mcpUiState.baselineRevoke.error = getErrorMessage(
        error,
        "현재 승인 기준선을 삭제하지 못했습니다."
    );
}


async function refreshAfterBaselineRevocation(
    monitoringTargetKey,
    selectionId,
    options = {}
) {
    mcpUiState.serverManagement.targetDetailsByKey.delete(monitoringTargetKey);
    mcpUiState.baselineHistory.recordsByTargetKey.delete(monitoringTargetKey);
    resetCandidateReviewStateForServerChange();

    if (!options.keepPanel) {
        mcpUiState.baselineRevoke.panelOpen = false;
        mcpUiState.baselineRevoke.targetKey = null;
        mcpUiState.baselineRevoke.baselineId = null;
        mcpUiState.baselineRevoke.error = null;
    }

    await loadTargetDetails(
        monitoringTargetKey,
        selectionId
    );

    if (mcpUiState.baselineHistory.selectedTargetKey === monitoringTargetKey) {
        await loadBaselineHistory(monitoringTargetKey);
    }

    await loadMcpServers();
}


function getLatestSafeSummary(server) {
    const result = mcpUiState.scanBatch.resultsBySelectionId.get(
        server.selectionId
    );

    return (
        result?.candidate?.configuration_fingerprint?.safe_summary ||
        null
    );
}


function resetCandidateReviewStateForServerChange() {
    mcpUiState.candidateReview.selectedCandidateId = null;
    mcpUiState.candidateReview.expandedCandidateId = null;
    mcpUiState.candidateReview.loadingCandidateId = null;
    mcpUiState.candidateReview.error = null;
    mcpUiState.candidateReview.decisionMode = null;
    mcpUiState.candidateReview.decisionCandidateId = null;
    mcpUiState.candidateReview.decisionError = null;
    mcpUiState.candidateReview.decisionSuccess = null;
}


function ensureCandidateSelectionForCurrentServer() {
    if (mcpUiState.candidateReview.decisionRunning) {
        return;
    }

    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const pendingIds = getPendingCandidateIdsForServer(server);

    if (!server || !pendingIds.length) {
        mcpUiState.candidateReview.selectedCandidateId = null;
        mcpUiState.candidateReview.expandedCandidateId = null;
        mcpUiState.candidateReview.decisionMode = null;
        mcpUiState.candidateReview.decisionCandidateId = null;
        renderCandidateReview();
        return;
    }

    if (
        !mcpUiState.candidateReview.selectedCandidateId ||
        !pendingIds.includes(mcpUiState.candidateReview.selectedCandidateId)
    ) {
        mcpUiState.candidateReview.selectedCandidateId =
            getPreferredPendingCandidateId(server, pendingIds);
        mcpUiState.candidateReview.expandedCandidateId = null;
        mcpUiState.candidateReview.decisionMode = null;
        mcpUiState.candidateReview.decisionCandidateId = null;
    }

    renderCandidateReview();
    maybeLoadSelectedCandidateDetail();
}


function getTargetStateForServer(server) {
    if (!server) {
        return null;
    }

    if (server.monitoringTargetKey) {
        const cached = mcpUiState.serverManagement.targetDetailsByKey.get(
            server.monitoringTargetKey
        );

        if (cached) {
            return cached;
        }
    }

    return server.rawMonitoringState || null;
}


function getPendingCandidateIdsForServer(server) {
    const state = getTargetStateForServer(server);

    return Array.isArray(state?.pending_candidate_ids)
        ? state.pending_candidate_ids
        : [];
}


function getPreferredPendingCandidateId(
    server,
    pendingIds
) {
    const latestScanCandidateId =
        mcpUiState.scanBatch.resultsBySelectionId.get(
            server.selectionId
        )?.candidate?.candidate_id || null;

    if (
        latestScanCandidateId &&
        pendingIds.includes(latestScanCandidateId)
    ) {
        return latestScanCandidateId;
    }

    return pendingIds[0] || null;
}


function renderCandidateReview() {
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const review = mcpUiState.candidateReview;

    elements.candidateList.replaceChildren();
    clearCandidateDetailBlocks();

    if (!server) {
        showCandidateListEmpty(
            "서버를 선택하세요.",
            "서버를 선택하면 승인 대기 기준선 후보가 표시됩니다."
        );
        showCandidateDetailEmpty(
            "Candidate를 선택하세요.",
            "승인 대기 후보를 선택하면 상세 정보와 변경 내용을 확인할 수 있습니다."
        );
        setInlineMessage(
            elements.candidateReviewStatus,
            elements.candidateReviewError,
            "",
            false
        );
        renderCandidateDecisionPanel();
        return;
    }

    const pendingIds = getPendingCandidateIdsForServer(server);

    if (
        review.selectedCandidateId &&
        !pendingIds.includes(review.selectedCandidateId)
    ) {
        review.selectedCandidateId = null;
        review.expandedCandidateId = null;
        review.decisionMode = null;
        review.decisionCandidateId = null;
    }

    if (!pendingIds.length) {
        review.expandedCandidateId = null;
        showCandidateListEmpty(
            "검토할 기준선 후보가 없습니다.",
            "서버 검사 후 승인 대기 후보가 생기면 여기에 표시됩니다."
        );
        showCandidateDetailEmpty(
            "검토할 기준선 후보가 없습니다.",
            "현재 서버에는 승인 대기 중인 기준선 후보가 없습니다."
        );
        setInlineMessage(
            elements.candidateReviewStatus,
            elements.candidateReviewError,
            review.decisionSuccess || "",
            false
        );
        renderCandidateDecisionPanel();
        return;
    }

    elements.candidateListEmpty.hidden = true;

    for (const candidateId of pendingIds) {
        elements.candidateList.appendChild(
            createCandidateListItem(candidateId)
        );
    }

    renderCandidateDetail();

    renderCandidateDecisionPanel();
}


function showCandidateListEmpty(
    title,
    description
) {
    elements.candidateListEmpty.hidden = false;
    elements.candidateListEmpty.replaceChildren(
        createInlineStrong(title),
        createInlineSpan(description)
    );
}


function showCandidateDetailEmpty(
    title,
    description
) {
    elements.candidateDetail.hidden = true;
    elements.candidateDetailEmpty.hidden = false;
    elements.candidateDetailEmpty.replaceChildren(
        createInlineStrong(title),
        createInlineSpan(description)
    );
    setCandidateDecisionButtonsDisabled(true);
}


function clearCandidateDetailBlocks() {
    elements.candidateBasicInfo.replaceChildren();
    elements.candidateSnapshotSummary.replaceChildren();
    elements.candidateConfigSummary.replaceChildren();
    elements.candidateComparisonSummary.replaceChildren();
    elements.candidateToolDiff.replaceChildren();
}


function createCandidateListItem(candidateId) {
    const button = document.createElement("button");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const detail = mcpUiState.candidateReview.candidateDetailsById.get(
        candidateId
    );

    const isSelected =
        mcpUiState.candidateReview.selectedCandidateId === candidateId;
    const isExpanded =
        mcpUiState.candidateReview.expandedCandidateId === candidateId;

    button.className = "candidate-list-item";
    button.type = "button";
    button.dataset.candidateId = candidateId;
    button.disabled = mcpUiState.candidateReview.decisionRunning;
    button.setAttribute(
        "aria-controls",
        "candidate-basic-info candidate-snapshot-summary candidate-config-summary"
    );
    button.setAttribute("aria-expanded", String(isExpanded));
    button.title = isExpanded
        ? "Candidate 요약 정보 접기"
        : "Candidate 요약 정보 펼치기";

    if (isSelected) {
        button.classList.add("is-selected");
        button.setAttribute("aria-current", "true");
    }

    title.textContent = candidateId;
    title.title = candidateId;

    meta.className = "candidate-list-meta";

    if (detail) {
        appendMetaText(meta, formatDateTime(detail.created_at));
        appendMetaText(meta, `Revision ${detail.candidate_revision}`);
        appendMetaText(meta, displayScanStatus(detail.dynamic_scan_status));
        appendMetaText(meta, `Tool ${detail.snapshot?.tool_count ?? "-"}`);

        if (detail.comparison_result) {
            const comparison = detail.comparison_result;

            appendMetaText(
                meta,
                [
                    `추가 ${comparison.added_count ?? 0}`,
                    `삭제 ${comparison.removed_count ?? 0}`,
                    `변경 ${comparison.changed_count ?? 0}`,
                ].join(" / ")
            );
        }
    } else {
        appendMetaText(meta, "승인 대기");
    }

    button.appendChild(title);
    button.appendChild(meta);
    button.addEventListener(
        "click",
        () => selectCandidateForReview(candidateId)
    );

    return button;
}


function selectCandidateForReview(candidateId) {
    const review = mcpUiState.candidateReview;

    if (review.decisionRunning) {
        return;
    }

    const shouldCollapse =
        review.selectedCandidateId === candidateId &&
        review.expandedCandidateId === candidateId;
    const candidateChanged = review.selectedCandidateId !== candidateId;

    review.selectedCandidateId = candidateId;
    review.expandedCandidateId = shouldCollapse
        ? null
        : candidateId;
    review.error = null;

    if (candidateChanged) {
        review.decisionMode = null;
        review.decisionCandidateId = null;
        review.decisionError = null;
        review.decisionSuccess = null;
    }

    renderCandidateReview();

    if (!shouldCollapse) {
        maybeLoadSelectedCandidateDetail();
    }
}


function maybeLoadSelectedCandidateDetail() {
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const candidateId = mcpUiState.candidateReview.selectedCandidateId;

    if (
        !server?.monitoringTargetKey ||
        !candidateId ||
        mcpUiState.candidateReview.candidateDetailsById.has(candidateId) ||
        mcpUiState.candidateReview.loadingCandidateId === candidateId
    ) {
        return;
    }

    loadCandidateDetail(
        candidateId,
        server.monitoringTargetKey
    );
}


async function loadCandidateDetail(
    candidateId,
    monitoringTargetKey
) {
    mcpUiState.candidateReview.loadingCandidateId = candidateId;
    mcpUiState.candidateReview.error = null;
    renderCandidateReview();

    const params = new URLSearchParams({
        monitoring_target_key: monitoringTargetKey,
    });

    try {
        const payload = await apiFetch(
            `/api/mcp/candidates/${encodeURIComponent(candidateId)}?${params.toString()}`
        );

        mcpUiState.candidateReview.candidateDetailsById.set(
            payload.candidate_id,
            payload
        );

        if (mcpUiState.candidateReview.selectedCandidateId === candidateId) {
            mcpUiState.candidateReview.error = null;
        }
    } catch (error) {
        if (mcpUiState.candidateReview.selectedCandidateId === candidateId) {
            if (isMonitoringNotFoundError(error)) {
                mcpUiState.candidateReview.error =
                    "Candidate를 찾을 수 없습니다. 최신 서버 상태를 다시 불러옵니다.";
                await refreshCandidateNotFoundState(monitoringTargetKey);
            } else {
                mcpUiState.candidateReview.error = getErrorMessage(
                    error,
                    "Candidate 상세 정보를 불러오지 못했습니다."
                );
            }
        }
    } finally {
        if (mcpUiState.candidateReview.loadingCandidateId === candidateId) {
            mcpUiState.candidateReview.loadingCandidateId = null;
        }

        renderCandidateReview();
    }
}


async function refreshCandidateNotFoundState(monitoringTargetKey) {
    const server = findServerByTargetKey(monitoringTargetKey);

    if (server) {
        mcpUiState.serverManagement.targetDetailsByKey.delete(
            monitoringTargetKey
        );
        await loadTargetDetails(
            monitoringTargetKey,
            server.selectionId
        );
    }

    await loadMcpServers();
}


function renderCandidateDetail() {
    const review = mcpUiState.candidateReview;
    const candidateId = review.selectedCandidateId;
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );

    if (!candidateId) {
        showCandidateDetailEmpty(
            "Candidate를 선택하세요.",
            "승인 대기 후보를 선택하면 상세 정보와 변경 내용을 확인할 수 있습니다."
        );
        return;
    }

    if (review.loadingCandidateId === candidateId) {
        showCandidateDetailEmpty(
            "Candidate 상세 정보를 불러오는 중입니다.",
            "잠시만 기다려 주세요."
        );
        setInlineMessage(
            elements.candidateReviewStatus,
            elements.candidateReviewError,
            "Candidate 상세 정보를 불러오는 중입니다.",
            false
        );
        return;
    }

    if (review.error) {
        showCandidateDetailEmpty(
            "Candidate 상세 정보를 표시할 수 없습니다.",
            review.error
        );
        setInlineMessage(
            elements.candidateReviewStatus,
            elements.candidateReviewError,
            review.error,
            true
        );
        return;
    }

    const candidate = review.candidateDetailsById.get(candidateId);

    if (!candidate) {
        showCandidateDetailEmpty(
            "Candidate 상세 정보를 불러오지 않았습니다.",
            "Candidate를 선택하면 상세 정보를 불러옵니다."
        );
        maybeLoadSelectedCandidateDetail();
        return;
    }

    elements.candidateDetailEmpty.hidden = true;
    elements.candidateDetail.hidden = false;

    renderCandidateBasicInfo(candidate);
    renderCandidateSnapshotSummary(candidate);
    renderCandidateConfigSummary(candidate);
    renderCandidateComparisonSummary(candidate);
    renderCandidateToolDiff(candidate);
    renderCandidateDecisionControls(candidate, server);
    setCandidateSupplementalBlocksHidden(
        review.expandedCandidateId !== candidateId
    );

    const targetState = getTargetStateForServer(server);
    const candidateStatusMessage = isCandidatePending(
        candidate.candidate_id,
        targetState
    )
        ? review.decisionSuccess || ""
        : "이미 처리되었거나 더 이상 대기 중인 후보가 아닙니다.";
    setInlineMessage(
        elements.candidateReviewStatus,
        elements.candidateReviewError,
        candidateStatusMessage,
        false
    );
}


function setCandidateSupplementalBlocksHidden(hidden) {
    elements.candidateBasicInfo.hidden = hidden;
    elements.candidateSnapshotSummary.hidden = hidden;
    elements.candidateConfigSummary.hidden = hidden;
}


function renderCandidateBasicInfo(candidate) {
    elements.candidateBasicInfo.replaceChildren(
        createCandidateBlockTitle("Candidate 기본 정보"),
        createDefinitionGrid(
            [
                ["Candidate ID", candidate.candidate_id],
                ["생성 시각", formatDateTime(candidate.created_at)],
                ["후보 Revision", candidate.candidate_revision],
                ["검사 상태", displayScanStatus(candidate.dynamic_scan_status)],
                ["원본 Scan ID", candidate.scan_id],
                ["생성 당시 서버 선택 ID", candidate.selection_id],
                [
                    "이전 거절 후보 대체 여부",
                    candidate.supersedes_rejected_candidate_id || "-",
                ],
                [
                    "생성 당시 State Version",
                    candidate.state_version_at_creation,
                ],
                ["Monitoring Target", candidate.monitoring_target_key],
            ]
        )
    );
}


function renderCandidateSnapshotSummary(candidate) {
    const snapshot = candidate.snapshot || {};
    const fragment = document.createDocumentFragment();

    fragment.appendChild(createCandidateBlockTitle("Snapshot 요약"));
    fragment.appendChild(
        createDefinitionGrid(
            [
                ["Snapshot ID", snapshot.snapshot_id],
                ["Snapshot Hash Prefix", snapshot.snapshot_hash_prefix],
                ["Normalization Version", snapshot.normalization_version],
                ["Tool 수", snapshot.tool_count],
                ["생성 시각", formatDateTime(snapshot.created_at)],
                ["Source Scan ID", snapshot.source_scan_id],
            ]
        )
    );

    const warnings = Array.isArray(snapshot.warnings)
        ? snapshot.warnings
        : [];

    if (warnings.length) {
        const warningList = document.createElement("div");
        warningList.className = "snapshot-warning-list";

        for (const warning of warnings) {
            warningList.appendChild(
                createDefinitionGrid(
                    [
                        ["Code", warning.code],
                        ["Message", warning.message],
                        ["Tool", warning.tool_name],
                        ["Occurrence", warning.occurrence_count],
                    ]
                )
            );
        }

        fragment.appendChild(warningList);
    }

    elements.candidateSnapshotSummary.replaceChildren(fragment);
}


function renderCandidateConfigSummary(candidate) {
    const fingerprint = candidate.configuration_fingerprint || {};
    const fragment = document.createDocumentFragment();
    const safeSummary = fingerprint.safe_summary || {};

    fragment.appendChild(createCandidateBlockTitle("기준선 비교 정보"));
    fragment.appendChild(
        createDefinitionGrid(
            [
                ["Fingerprint Hash Prefix", fingerprint.fingerprint_hash_prefix],
                ["연결 방식", displayTransport(fingerprint.transport)],
            ]
        )
    );

    const safeGrid = document.createElement("dl");
    safeGrid.className = "candidate-safe-config-grid";

    for (const key of Object.keys(safeConfigLabelByKey)) {
        if (!Object.prototype.hasOwnProperty.call(safeSummary, key)) {
            continue;
        }

        appendDefinition(
            safeGrid,
            safeConfigLabelByKey[key],
            displaySafeConfigValue(key, safeSummary[key])
        );
    }

    if (!safeGrid.children.length) {
        safeGrid.appendChild(
            createEmptyState(
                "표시할 기준선 비교 정보가 없습니다.",
                "DTO에 제공된 기준선 판단용 요약 값만 표시합니다."
            )
        );
    }

    fragment.appendChild(safeGrid);
    elements.candidateConfigSummary.replaceChildren(fragment);
}


function renderCandidateComparisonSummary(candidate) {
    const comparison = candidate.comparison_result;
    const fragment = document.createDocumentFragment();

    fragment.appendChild(
        createCandidateBlockTitle("기준선 비교 요약")
    );

    if (!comparison) {
        fragment.appendChild(
            createEmptyState(
                "비교할 승인 기준선이 없습니다.",
                "최초 기준선 후보이거나 저장된 비교 결과가 없습니다."
            )
        );

        elements.candidateComparisonSummary.replaceChildren(fragment);
        return;
    }

    fragment.appendChild(
        createComparisonSummaryDetails(
            comparison,
            candidate.candidate_id
        )
    );

    elements.candidateComparisonSummary.replaceChildren(fragment);
}


function renderCandidateToolDiff(candidate) {
    const comparison = candidate.comparison_result;
    const fragment = document.createDocumentFragment();

    fragment.appendChild(
        createCandidateBlockTitle("Tool Metadata 변경")
    );

    if (!comparison) {
        fragment.appendChild(
            createEmptyState(
                "비교할 Tool 변경 목록이 없습니다.",
                "최초 기준선 후보이거나 저장된 비교 결과가 없습니다."
            )
        );
    } else {
        fragment.appendChild(
            createToolDiffFragment(comparison)
        );
    }

    elements.candidateToolDiff.replaceChildren(fragment);
}


function createToolDiffItem(change) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const title = document.createElement("span");
    const meta = document.createElement("span");
    const body = document.createElement("div");

    details.className = `tool-diff-item tool-diff-${change.change_type}`;
    title.textContent = `${change.tool_name || "-"} · ${displayToolChangeType(change.change_type)}`;
    meta.textContent = change.tool_key || "-";
    summary.appendChild(title);
    summary.appendChild(meta);
    details.appendChild(summary);

    body.className = "tool-diff-body";
    body.appendChild(
        createDefinitionGrid(
            [
                ["Tool Key", change.tool_key],
                ["이전 Tool Hash Prefix", change.old_tool_hash_prefix],
                ["새 Tool Hash Prefix", change.new_tool_hash_prefix],
            ]
        )
    );

    if (change.change_type === "added") {
        body.appendChild(
            createEmptyState(
                "승인 기준선에 없던 Tool이 추가되었습니다.",
                "새 Tool Hash Prefix를 확인하세요."
            )
        );
    } else if (change.change_type === "removed") {
        body.appendChild(
            createEmptyState(
                "승인 기준선에 있던 Tool이 현재 목록에서 제거되었습니다.",
                "이전 Tool Hash Prefix를 확인하세요."
            )
        );
    } else if (
        change.change_type === "changed" &&
        Array.isArray(change.field_changes)
    ) {
        const fieldList = document.createElement("div");
        fieldList.className = "field-diff-list";

        for (const field of change.field_changes) {
            fieldList.appendChild(createFieldDiffItem(field));
        }

        body.appendChild(fieldList);
    }

    details.appendChild(body);

    return details;
}


function createFieldDiffItem(field) {
    const item = document.createElement("article");
    const title = document.createElement("h6");
    const grid = document.createElement("div");

    item.className = "field-diff-item";
    title.textContent = displayFieldName(field.field_name);
    grid.className = "field-diff-grid";

    grid.appendChild(
        createFieldValuePanel(
            "이전 값",
            field.old_presence,
            field.old_value_text,
            field.old_value_hash_prefix,
            field.old_value_truncated
        )
    );
    grid.appendChild(
        createFieldValuePanel(
            "현재 값",
            field.new_presence,
            field.new_value_text,
            field.new_value_hash_prefix,
            field.new_value_truncated
        )
    );

    item.appendChild(title);
    item.appendChild(grid);

    return item;
}


function createFieldValuePanel(
    title,
    presence,
    value,
    hashPrefix,
    truncated
) {
    const panel = document.createElement("section");
    const heading = document.createElement("strong");
    const presenceText = document.createElement("span");
    const pre = document.createElement("pre");
    const hash = document.createElement("span");

    panel.className = "field-value-panel";
    heading.textContent = title;
    presenceText.className = "field-presence";
    presenceText.textContent = displayFieldPresence(presence);
    pre.textContent = valueOrDash(value);
    hash.className = "field-hash-prefix";
    hash.textContent = `Hash Prefix: ${valueOrDash(hashPrefix)}`;

    panel.appendChild(heading);
    panel.appendChild(presenceText);
    panel.appendChild(pre);
    panel.appendChild(hash);

    if (truncated) {
        const note = document.createElement("span");

        note.className = "truncated-note";
        note.textContent = "보안·크기 제한으로 일부만 표시됩니다.";
        panel.appendChild(note);
    }

    return panel;
}


function renderCandidateDecisionControls(candidate, server) {
    const targetState = getTargetStateForServer(server);
    const pending = isCandidatePending(
        candidate.candidate_id,
        targetState
    );
    const tokenReady = Boolean(
        mcpUiState.security.token && mcpUiState.security.headerName
    );
    const disabled =
        !pending ||
        mcpUiState.candidateReview.decisionRunning ||
        !tokenReady ||
        typeof targetState?.state_version !== "number";

    setCandidateDecisionButtonsDisabled(disabled);

}


function setCandidateDecisionButtonsDisabled(disabled) {
    setButtonDisabled(elements.candidateApproveButton, disabled);
    setButtonDisabled(elements.candidateRejectButton, disabled);
}


function isCandidatePending(candidateId, targetState) {
    return (
        Array.isArray(targetState?.pending_candidate_ids) &&
        targetState.pending_candidate_ids.includes(candidateId)
    );
}


function startCandidateDecision(mode) {
    const candidateId = mcpUiState.candidateReview.selectedCandidateId;

    if (!candidateId || mcpUiState.candidateReview.decisionRunning) {
        return;
    }

    mcpUiState.candidateReview.decisionMode = mode;
    mcpUiState.candidateReview.decisionCandidateId = candidateId;
    mcpUiState.candidateReview.decisionError = null;
    mcpUiState.candidateReview.decisionSuccess = null;
    elements.candidateReasonCode.value = "";
    renderCandidateDecisionPanel();
}


function clearCandidateDecisionPanel() {
    mcpUiState.candidateReview.decisionMode = null;
    mcpUiState.candidateReview.decisionCandidateId = null;
    mcpUiState.candidateReview.decisionError = null;
    renderCandidateDecisionPanel();
}


function renderCandidateDecisionPanel() {
    const review = mcpUiState.candidateReview;
    const mode = review.decisionMode;
    const candidateId = review.decisionCandidateId;
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );

    if (!mode || !candidateId) {
        elements.candidateDecisionPanel.hidden = true;
        return;
    }

    const approving = mode === "approve";

    elements.candidateDecisionPanel.hidden = false;
    elements.candidateDecisionTitle.textContent = approving
        ? "기준선 후보를 승인하시겠습니까?"
        : "기준선 후보를 거절하시겠습니까?";
    elements.candidateDecisionDescription.textContent = approving
        ? "승인하면 이 후보가 현재 서버의 승인 기준선이 됩니다."
        : "거절하면 이 후보는 승인 기준선이 되지 않습니다. 기존 승인 기준선이 있다면 그대로 유지되며, 현재 변경 상태는 계속 검토가 필요할 수 있습니다.";

    elements.candidateDecisionSummary.replaceChildren();
    appendDefinition(
        elements.candidateDecisionSummary,
        "서버",
        server?.serverName
    );
    appendDefinition(
        elements.candidateDecisionSummary,
        "Candidate",
        candidateId
    );
    appendDefinition(
        elements.candidateDecisionSummary,
        "처리 종류",
        approving ? "승인" : "거절"
    );

    elements.candidateDecisionConfirmButton.textContent =
        review.decisionRunning
            ? (approving ? "승인 처리 중..." : "거절 처리 중...")
            : (approving ? "최종 승인" : "최종 거절");
    elements.candidateDecisionConfirmButton.classList.toggle(
        "candidate-decision-danger",
        !approving
    );
    setButtonDisabled(
        elements.candidateDecisionConfirmButton,
        review.decisionRunning
    );
    setButtonDisabled(
        elements.candidateDecisionCancelButton,
        review.decisionRunning
    );
    elements.candidateReasonCode.disabled = review.decisionRunning;

    if (review.decisionError) {
        setInlineMessage(
            elements.candidateReviewStatus,
            elements.candidateReviewError,
            review.decisionError,
            true
        );
    }
}


async function submitCandidateDecision() {
    const review = mcpUiState.candidateReview;
    const mode = review.decisionMode;
    const candidateId = review.decisionCandidateId;
    const server = findServerBySelectionId(
        mcpUiState.serverManagement.selectedSelectionId
    );
    const reasonCode = elements.candidateReasonCode.value.trim();

    if (
        !mode ||
        !candidateId ||
        !server?.monitoringTargetKey ||
        review.decisionRunning
    ) {
        return;
    }

    if (reasonCode && !/^[a-z0-9_]{1,64}$/.test(reasonCode)) {
        review.decisionError = "처리 사유 코드 형식을 확인해 주세요.";
        renderCandidateDecisionPanel();
        return;
    }

    review.decisionRunning = true;
    review.decisionError = null;
    review.decisionSuccess = null;
    renderCandidateReview();

    try {
        const latestState = await fetchLatestTargetStateForCandidateDecision(
            server.monitoringTargetKey
        );

        if (!isCandidatePending(candidateId, latestState)) {
            review.decisionError =
                "이미 처리되었거나 더 이상 대기 중인 후보가 아닙니다.";
            await refreshAfterCandidateDecision(
                server.monitoringTargetKey,
                server.selectionId,
                candidateId
            );
            return;
        }

        const body = {
            monitoring_target_key: server.monitoringTargetKey,
            expected_state_version: latestState.state_version,
            safe_reason_code: reasonCode || null,
        };
        const decisionEndpoint = mode === "approve"
            ? `/api/mcp/candidates/${encodeURIComponent(candidateId)}/approve`
            : `/api/mcp/candidates/${encodeURIComponent(candidateId)}/reject`;
        const decision = await apiFetch(
            decisionEndpoint,
            {
                method: "POST",
                json: body,
            }
        );

        review.decisionSuccess =
            mode === "approve"
                ? "기준선 후보를 승인했습니다."
                : "기준선 후보를 거절했습니다.";

        if (decision.baseline_id) {
            review.decisionSuccess += ` 기준선: ${compactIdentifier(decision.baseline_id)}`;
        }

        review.decisionMode = null;
        review.decisionCandidateId = null;
        review.selectedCandidateId = null;
        review.expandedCandidateId = null;
        await refreshAfterCandidateDecision(
            server.monitoringTargetKey,
            server.selectionId,
            candidateId
        );
    } catch (error) {
        await handleCandidateDecisionError(
            error,
            server.monitoringTargetKey,
            server.selectionId,
            candidateId
        );
    } finally {
        review.decisionRunning = false;
        renderAllMcpViews();
    }
}


async function fetchLatestTargetStateForCandidateDecision(monitoringTargetKey) {
    const state = await apiFetch(
        `/api/mcp/targets/${encodeURIComponent(monitoringTargetKey)}`
    );

    mcpUiState.serverManagement.targetDetailsByKey.set(
        monitoringTargetKey,
        state
    );

    return state;
}


async function handleCandidateDecisionError(
    error,
    monitoringTargetKey,
    selectionId,
    candidateId
) {
    if (error.statusCode === 409) {
        mcpUiState.candidateReview.decisionError =
            "서버 상태가 변경되어 요청을 완료하지 못했습니다. 최신 상태를 확인한 뒤 다시 시도해 주세요.";
        await refreshAfterCandidateDecision(
            monitoringTargetKey,
            selectionId,
            candidateId,
            {
                keepDecisionPanel: true,
            }
        );
        return;
    }

    if (isMonitoringNotFoundError(error)) {
        mcpUiState.candidateReview.decisionError =
            "Candidate를 찾을 수 없거나 이미 처리되었습니다.";
        await refreshAfterCandidateDecision(
            monitoringTargetKey,
            selectionId,
            candidateId,
            {
                keepDecisionPanel: true,
            }
        );
        return;
    }

    if (error.statusCode === 422) {
        mcpUiState.candidateReview.decisionError =
            "처리 사유 코드 형식을 확인해 주세요.";
        return;
    }

    mcpUiState.candidateReview.decisionError = getErrorMessage(
        error,
        "기준선 후보 처리를 완료하지 못했습니다."
    );
}


async function refreshAfterCandidateDecision(
    monitoringTargetKey,
    selectionId,
    candidateId,
    options = {}
) {
    mcpUiState.candidateReview.candidateDetailsById.delete(candidateId);
    mcpUiState.serverManagement.targetDetailsByKey.delete(monitoringTargetKey);
    mcpUiState.baselineHistory.recordsByTargetKey.delete(monitoringTargetKey);

    if (!options.keepDecisionPanel) {
        mcpUiState.candidateReview.decisionMode = null;
        mcpUiState.candidateReview.decisionCandidateId = null;
        mcpUiState.candidateReview.decisionError = null;
        mcpUiState.candidateReview.decisionSuccess = null;
    }

    await loadTargetDetails(
        monitoringTargetKey,
        selectionId
    );

    if (mcpUiState.baselineHistory.selectedTargetKey === monitoringTargetKey) {
        await loadBaselineHistory(monitoringTargetKey);
    }

    await loadMcpServers();
    ensureCandidateSelectionForCurrentServer();
}


function renderBaselineHistoryServerList() {
    elements.baselineHistoryServerList.replaceChildren();

    if (mcpUiState.serverCatalog.loading) {
        elements.baselineHistoryServerList.appendChild(
            createEmptyState(
                "서버 목록을 불러오는 중입니다.",
                "잠시만 기다려 주세요."
            )
        );
        setBaselineHistoryMessage(
            "서버 목록을 불러오는 중입니다.",
            false
        );
        return;
    }

    if (mcpUiState.serverCatalog.error) {
        elements.baselineHistoryServerList.appendChild(
            createEmptyState(
                "서버 목록을 불러오지 못했습니다.",
                "서버 목록 새로고침을 다시 시도해 주세요."
            )
        );
        setBaselineHistoryMessage(
            mcpUiState.serverCatalog.error,
            true
        );
        return;
    }

    if (!mcpUiState.serverCatalog.servers.length) {
        elements.baselineHistoryServerList.appendChild(
            createEmptyState(
                "표시할 서버가 없습니다.",
                "서버를 불러오면 기준선 이력을 조회할 대상을 선택할 수 있습니다."
            )
        );
        setBaselineHistoryMessage("", false);
        return;
    }

    for (const server of mcpUiState.serverCatalog.servers) {
        elements.baselineHistoryServerList.appendChild(
            createBaselineServerItem(server)
        );
    }

    setBaselineHistoryMessage("", false);
}


function createBaselineServerItem(server) {
    const button = document.createElement("button");
    const header = document.createElement("span");
    const title = document.createElement("strong");
    const identity = document.createElement("span");
    const availabilityBadge = createBaselineHistoryAvailabilityBadge(server);

    button.className = "baseline-server-item";
    button.type = "button";
    button.disabled = !server.monitoringTargetKey;
    button.dataset.monitoringTargetKey = server.monitoringTargetKey || "";

    if (
        server.monitoringTargetKey &&
        mcpUiState.baselineHistory.selectedTargetKey ===
            server.monitoringTargetKey
    ) {
        button.classList.add("is-selected");
        button.setAttribute("aria-current", "true");
    }

    header.className = "baseline-server-header";
    title.textContent = server.serverName;

    identity.className = "baseline-server-identity";
    appendLabeledMetaText(identity, "제품", displayProduct(server.product));
    appendLabeledMetaText(identity, "범위", displayScope(server.scope));

    header.appendChild(title);
    header.appendChild(availabilityBadge);
    button.appendChild(header);
    button.appendChild(identity);
    button.addEventListener(
        "click",
        () => selectBaselineHistoryTarget(server.monitoringTargetKey)
    );

    return button;
}


function selectBaselineHistoryTarget(monitoringTargetKey) {
    if (!monitoringTargetKey) {
        return;
    }

    mcpUiState.baselineHistory.selectedTargetKey = monitoringTargetKey;
    mcpUiState.baselineHistory.error = null;
    mcpUiState.baselineHistory.deleteError = null;
    mcpUiState.baselineHistory.deleteSuccess = null;
    mcpUiState.baselineHistory.deleteConfirmTargetKey = null;
    renderBaselineHistoryServerList();
    renderBaselineHistoryList();

    const server = findServerByTargetKey(monitoringTargetKey);

    if (server && !hasPersistedMonitoringState(server)) {
        mcpUiState.baselineHistory.recordsByTargetKey.set(
            monitoringTargetKey,
            []
        );
        renderBaselineHistoryList();
        return;
    }

    loadBaselineHistory(monitoringTargetKey);
}


function appendLabeledMetaText(
    container,
    label,
    value
) {
    const item = document.createElement("span");
    const labelElement = document.createElement("b");
    const valueElement = document.createElement("strong");

    labelElement.textContent = label;
    valueElement.textContent = valueOrDash(value);

    item.appendChild(labelElement);
    item.appendChild(valueElement);
    container.appendChild(item);
}


function createBaselineHistoryAvailabilityBadge(server) {
    const availability = getBaselineHistoryAvailability(server);
    const badge = createStatusBadge(
        availability.tone,
        availability.label
    );

    badge.classList.add("baseline-history-availability");
    badge.title = availability.description;

    return badge;
}


function getBaselineHistoryAvailability(server) {
    if (!server.monitoringTargetKey) {
        return {
            tone: "neutral",
            label: "조회 불가",
            description: "이 서버는 기준선 이력 조회 대상이 아닙니다.",
        };
    }

    if (getBaselineHistoryCountForServer(server) > 0) {
        return {
            tone: "history-present",
            label: "이력 있음",
            description: "저장된 기준선 Lifecycle 이벤트가 있습니다.",
        };
    }

    return {
        tone: "history-empty",
        label: "이력 없음",
        description: "아직 저장된 감시 상태나 기준선 이력이 없습니다.",
    };
}


function getBaselineHistoryCountForServer(server) {
    if (!server?.monitoringTargetKey) {
        return 0;
    }

    const cachedRecords = mcpUiState.baselineHistory.recordsByTargetKey.get(
        server.monitoringTargetKey
    );
    if (Array.isArray(cachedRecords)) {
        return cachedRecords.length;
    }

    return Array.isArray(server.historyIds)
        ? server.historyIds.length
        : 0;
}


async function loadBaselineHistory(monitoringTargetKey) {
    if (
        mcpUiState.baselineHistory.recordsByTargetKey.has(
            monitoringTargetKey
        )
    ) {
        renderBaselineHistoryList();
        return;
    }

    mcpUiState.baselineHistory.loadingTargetKey = monitoringTargetKey;
    mcpUiState.baselineHistory.error = null;
    renderBaselineHistoryList();

    try {
        const payload = await apiFetch(
            `/api/mcp/targets/${encodeURIComponent(monitoringTargetKey)}/history`
        );
        const records = Array.isArray(payload?.records)
            ? payload.records
            : [];

        mcpUiState.baselineHistory.recordsByTargetKey.set(
            monitoringTargetKey,
            records
        );
    } catch (error) {
        if (
            mcpUiState.baselineHistory.selectedTargetKey ===
            monitoringTargetKey
        ) {
            if (isMonitoringNotFoundError(error)) {
                mcpUiState.baselineHistory.recordsByTargetKey.set(
                    monitoringTargetKey,
                    []
                );
                mcpUiState.baselineHistory.error = null;
            } else {
                mcpUiState.baselineHistory.error = getErrorMessage(
                    error,
                    "기준선 이력을 불러오지 못했습니다."
                );
            }
        }
    } finally {
        if (
            mcpUiState.baselineHistory.loadingTargetKey ===
            monitoringTargetKey
        ) {
            mcpUiState.baselineHistory.loadingTargetKey = null;
        }

        renderBaselineHistoryList();
    }
}


function renderBaselineHistoryList() {
    elements.baselineHistoryList.replaceChildren();

    const targetKey = mcpUiState.baselineHistory.selectedTargetKey;

    if (!targetKey) {
        renderBaselineHistoryDeleteButton([]);
        renderBaselineHistoryDeleteConfirmation([]);
        elements.baselineHistoryList.appendChild(
            createEmptyState(
                "표시할 기준선 이력이 없습니다.",
                "서버를 선택하면 저장된 기준선 승인·거절·삭제 기록이 표시됩니다."
            )
        );
        return;
    }

    if (
        mcpUiState.baselineHistory.loadingTargetKey === targetKey
    ) {
        renderBaselineHistoryDeleteButton(null);
        renderBaselineHistoryDeleteConfirmation(null);
        elements.baselineHistoryList.appendChild(
            createEmptyState(
                "기준선 이력을 불러오는 중입니다.",
                "잠시만 기다려 주세요."
            )
        );
        setBaselineHistoryMessage(
            "기준선 이력을 불러오는 중입니다.",
            false
        );
        return;
    }

    if (mcpUiState.baselineHistory.error) {
        renderBaselineHistoryDeleteButton(null);
        renderBaselineHistoryDeleteConfirmation(null);
        elements.baselineHistoryList.appendChild(
            createEmptyState(
                "기준선 이력을 불러오지 못했습니다.",
                "다른 서버를 선택하거나 다시 시도해 주세요."
            )
        );
        setBaselineHistoryMessage(
            mcpUiState.baselineHistory.error,
            true
        );
        return;
    }

    const records =
        mcpUiState.baselineHistory.recordsByTargetKey.get(targetKey) || [];
    renderBaselineHistoryDeleteButton(records);
    renderBaselineHistoryDeleteConfirmation(records);

    if (!records.length) {
        elements.baselineHistoryList.appendChild(
            createEmptyState(
                "아직 생성된 기준선 이력이 없습니다.",
                "이 서버에서 기준선 후보를 승인·거절하거나 승인 기준선을 삭제하면 이력이 여기에 표시됩니다."
            )
        );
        setBaselineHistoryMessage("", false);
        return;
    }

    const sortedRecords = [...records].sort(
        (left, right) => getTimestamp(right.created_at) - getTimestamp(left.created_at)
    );

    for (const record of sortedRecords) {
        elements.baselineHistoryList.appendChild(
            createHistoryRecordItem(record)
        );
    }

    setBaselineHistoryMessage("", false);
}


function renderBaselineHistoryDeleteConfirmation(records) {
    const panel = elements.baselineHistoryDeleteConfirmPanel;
    const targetKey = mcpUiState.baselineHistory.selectedTargetKey;
    const confirmTargetKey =
        mcpUiState.baselineHistory.deleteConfirmTargetKey;
    const isDeleting =
        targetKey &&
        mcpUiState.baselineHistory.deletingTargetKey === targetKey;
    const recordCount = Array.isArray(records)
        ? records.length
        : 0;
    const shouldShow =
        Boolean(targetKey) &&
        confirmTargetKey === targetKey &&
        recordCount > 0;

    panel.hidden = !shouldShow;

    if (!shouldShow) {
        return;
    }

    const server = findServerByTargetKey(targetKey);

    elements.baselineHistoryDeleteConfirmSummary.textContent =
        `${server?.serverName || "선택한 서버"}의 기준선 이력 ` +
        `${recordCount}개를 삭제하고 현재 승인 기준선과 승인 대기/거절 상태도 함께 초기화합니다. ` +
        "삭제 후 이력 목록과 MCP 서버 관리 상태가 갱신됩니다.";
    setButtonDisabled(
        elements.baselineHistoryDeleteConfirmButton,
        Boolean(isDeleting)
    );
    setButtonDisabled(
        elements.baselineHistoryDeleteCancelButton,
        Boolean(isDeleting)
    );
    elements.baselineHistoryDeleteConfirmButton.textContent = isDeleting
        ? "이력 삭제 중..."
        : "이력 삭제 확인";
}


function renderBaselineHistoryDeleteButton(records) {
    const button = elements.baselineHistoryDeleteButton;
    const targetKey = mcpUiState.baselineHistory.selectedTargetKey;
    const isDeleting =
        targetKey &&
        mcpUiState.baselineHistory.deletingTargetKey === targetKey;
    const recordCount = Array.isArray(records)
        ? records.length
        : -1;
    const canDelete =
        Boolean(targetKey) &&
        recordCount > 0 &&
        !isDeleting;

    setButtonDisabled(button, !canDelete);
    button.textContent = isDeleting
        ? "이력 삭제 중..."
        : "이력 삭제";
    button.title = canDelete
        ? "선택한 서버의 기준선 Lifecycle 이벤트 이력을 삭제합니다."
        : "삭제할 기준선 이력이 없습니다.";
}


function startBaselineHistoryDeletionConfirmation() {
    const targetKey = mcpUiState.baselineHistory.selectedTargetKey;
    const server = findServerByTargetKey(targetKey);
    const records = targetKey
        ? mcpUiState.baselineHistory.recordsByTargetKey.get(targetKey) || []
        : [];

    if (
        !targetKey ||
        !server ||
        !records.length ||
        mcpUiState.baselineHistory.deletingTargetKey
    ) {
        return;
    }

    mcpUiState.baselineHistory.deleteConfirmTargetKey = targetKey;
    mcpUiState.baselineHistory.deleteError = null;
    mcpUiState.baselineHistory.deleteSuccess = null;
    renderBaselineHistoryList();
    setBaselineHistoryMessage(
        "삭제할 기준선 이력을 확인해 주세요.",
        false
    );
}


function clearBaselineHistoryDeletionConfirmation() {
    if (mcpUiState.baselineHistory.deletingTargetKey) {
        return;
    }

    mcpUiState.baselineHistory.deleteConfirmTargetKey = null;
    renderBaselineHistoryList();
    setBaselineHistoryMessage("", false);
}


async function deleteSelectedBaselineHistory() {
    const targetKey = mcpUiState.baselineHistory.selectedTargetKey;
    const server = findServerByTargetKey(targetKey);
    const records = targetKey
        ? mcpUiState.baselineHistory.recordsByTargetKey.get(targetKey) || []
        : [];

    if (
        !targetKey ||
        !server ||
        !records.length ||
        mcpUiState.baselineHistory.deletingTargetKey ||
        mcpUiState.baselineHistory.deleteConfirmTargetKey !== targetKey
    ) {
        return;
    }

    mcpUiState.baselineHistory.deletingTargetKey = targetKey;
    mcpUiState.baselineHistory.deleteError = null;
    mcpUiState.baselineHistory.deleteSuccess = null;
    renderBaselineHistoryList();
    setBaselineHistoryMessage("기준선 이력을 삭제하는 중입니다.", false);

    try {
        const latestState = await apiFetch(
            `/api/mcp/targets/${encodeURIComponent(targetKey)}`
        );
        const result = await apiFetch(
            `/api/mcp/targets/${encodeURIComponent(targetKey)}/history`,
            {
                method: "DELETE",
                json: {
                    expected_state_version: latestState.state_version,
                },
            }
        );

        mcpUiState.baselineHistory.recordsByTargetKey.set(targetKey, []);
        applyHistoryDeletionResultToServer(targetKey, result);
        mcpUiState.baselineHistory.deleteConfirmTargetKey = null;
        mcpUiState.baselineHistory.deleteSuccess =
            `${result.deleted_history_count || 0}개의 기준선 이력을 삭제하고 기준선 감시 상태를 초기화했습니다.`;
        await refreshAfterBaselineHistoryDeletion(
            targetKey,
            server.selectionId
        );
    } catch (error) {
        mcpUiState.baselineHistory.deleteError = getErrorMessage(
            error,
            "기준선 이력을 삭제하지 못했습니다."
        );
    } finally {
        if (mcpUiState.baselineHistory.deletingTargetKey === targetKey) {
            mcpUiState.baselineHistory.deletingTargetKey = null;
        }

        renderBaselineHistoryServerList();
        renderBaselineHistoryList();
        setBaselineHistoryMessage(
            mcpUiState.baselineHistory.deleteError ||
                mcpUiState.baselineHistory.deleteSuccess ||
                "",
            Boolean(mcpUiState.baselineHistory.deleteError)
        );
    }
}


async function refreshAfterBaselineHistoryDeletion(
    monitoringTargetKey,
    selectionId
) {
    mcpUiState.serverManagement.targetDetailsByKey.delete(monitoringTargetKey);
    resetCandidateReviewStateForServerChange();

    if (
        mcpUiState.serverManagement.selectedSelectionId === selectionId
    ) {
        await loadTargetDetails(
            monitoringTargetKey,
            selectionId
        );
    }

    await loadMcpServers();
}


function applyHistoryDeletionResultToServer(
    monitoringTargetKey,
    result
) {
    const index = mcpUiState.serverCatalog.servers.findIndex(
        (server) => server.monitoringTargetKey === monitoringTargetKey
    );

    if (index < 0) {
        return;
    }

    const server = mcpUiState.serverCatalog.servers[index];
    const rawState = {
        ...(server.rawMonitoringState || {}),
        history_ids: Array.isArray(result.history_ids)
            ? result.history_ids
            : [],
        state_version: result.state_version,
        current_approved_id: result.current_approved_id,
        baseline_lifecycle: result.baseline_lifecycle,
        comparison_status: result.comparison_status,
        verification_status: result.verification_status,
        last_scan_status: result.last_scan_status,
        last_comparison: null,
    };

    mcpUiState.serverCatalog.servers[index] = {
        ...server,
        historyIds: rawState.history_ids,
        stateVersion: numberOrNull(rawState.state_version),
        currentApprovedId: rawState.current_approved_id || null,
        baselineLifecycle: rawState.baseline_lifecycle || server.baselineLifecycle,
        comparisonStatus: rawState.comparison_status || server.comparisonStatus,
        verificationStatus: rawState.verification_status || server.verificationStatus,
        lastScanStatus: rawState.last_scan_status || server.lastScanStatus,
        lastComparison: null,
        rawMonitoringState: rawState,
    };

    mcpUiState.serverManagement.targetDetailsByKey.delete(monitoringTargetKey);
}


function createHistoryRecordItem(record) {
    const item = document.createElement("article");
    const header = document.createElement("div");
    const title = document.createElement("strong");
    const time = document.createElement("time");
    const toggle = document.createElement("button");
    const details = document.createElement("dl");

    item.className = "history-record";
    header.className = "history-record-header";
    title.textContent = displayHistoryEvent(record.event_type);

    time.className = "history-record-time";
    setDateText(time, record.created_at);

    toggle.className = "secondary-button history-record-toggle";
    toggle.type = "button";
    toggle.textContent = "기술 정보 보기";
    toggle.setAttribute("aria-expanded", "false");

    details.className = "history-record-details";
    details.hidden = true;

    appendDefinition(
        details,
        "처리 사유",
        displayHistoryReason(record.safe_reason_code)
    );
    appendDefinition(details, "후보 ID", record.candidate_id);
    appendDefinition(details, "기준선 ID", record.baseline_id);
    appendDefinition(details, "변경 전 승인 기준선", record.previous_approved_id);
    appendDefinition(details, "변경 후 승인 기준선", record.new_approved_id);

    toggle.addEventListener(
        "click",
        () => {
            const expanded = toggle.getAttribute("aria-expanded") === "true";

            toggle.setAttribute("aria-expanded", String(!expanded));
            toggle.textContent = expanded
                ? "기술 정보 보기"
                : "기술 정보 닫기";
            details.hidden = expanded;
        }
    );

    header.appendChild(title);
    header.appendChild(time);
    header.appendChild(toggle);
    item.appendChild(header);
    item.appendChild(details);

    return item;
}


function appendDefinition(
    container,
    label,
    value
) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");

    term.textContent = label;
    description.textContent = valueOrDash(value);

    wrapper.appendChild(term);
    wrapper.appendChild(description);
    container.appendChild(wrapper);
}


function createInlineStrong(text) {
    const strong = document.createElement("strong");

    strong.textContent = text;

    return strong;
}


function createInlineSpan(text) {
    const span = document.createElement("span");

    span.textContent = text;

    return span;
}


function createCandidateBlockTitle(text) {
    const title = document.createElement("h5");

    title.textContent = text;

    return title;
}


function createDefinitionGrid(items) {
    const grid = document.createElement("dl");

    grid.className = "detail-definition-list candidate-definition-list";

    for (const [label, value] of items) {
        appendDefinition(
            grid,
            label,
            value
        );
    }

    return grid;
}


function displaySafeConfigValue(
    key,
    value
) {
    if (
        key === "cwd_present" ||
        key === "token_reference_present" ||
        key === "verify_tls" ||
        key === "follow_redirects" ||
        key === "trust_env"
    ) {
        return displayBooleanValue(value);
    }

    if (key === "transport") {
        return displayTransport(value);
    }

    return valueOrDash(value);
}


function displayToolChangeType(value) {
    return displayMappedValue(value, toolChangeLabelByValue);
}


function displayFieldName(value) {
    return displayMappedValue(value, fieldNameLabelByValue);
}


function displayFieldPresence(value) {
    return displayMappedValue(value, fieldPresenceLabelByValue);
}


function compactIdentifier(value) {
    const text = valueOrDash(value);

    if (text.length <= 18) {
        return text;
    }

    return `${text.slice(0, 8)}...${text.slice(-6)}`;
}


function updateMcpControls() {
    const running = mcpUiState.scanBatch.running;
    const loading = mcpUiState.serverCatalog.loading;
    const hasServers = mcpUiState.serverCatalog.servers.length > 0;
    const availableCount = mcpUiState.serverCatalog.servers.filter(
        (server) => server.canScan
    ).length;
    const selectedCount = getSelectedScannableServers().length;
    const tokenReady = Boolean(
        mcpUiState.security.token && mcpUiState.security.headerName
    );

    elements.includeProjectConfigToggle.checked =
        mcpUiState.serverCatalog.includeTrustedProjectConfig;
    elements.includeProjectConfigToggle.disabled = running;

    setButtonDisabled(
        elements.scanRefreshServersButton,
        running || loading
    );
    setButtonDisabled(
        elements.scanSelectAllButton,
        running || loading || availableCount === 0
    );
    setButtonDisabled(
        elements.scanClearSelectionButton,
        running || loading || selectedCount === 0
    );
    setButtonDisabled(
        elements.scanSelectedServersButton,
        running || loading || selectedCount === 0 || !tokenReady
    );

    elements.scanSelectedCount.textContent = String(selectedCount);
    elements.scanAvailableCount.textContent = String(availableCount);

    if (!hasServers && !loading) {
        elements.scanProgressPanel.hidden =
            !mcpUiState.scanBatch.completedAt &&
            !mcpUiState.scanBatch.running;
    }
}


function setButtonDisabled(
    button,
    disabled
) {
    button.disabled = disabled;
    button.setAttribute(
        "aria-disabled",
        String(disabled)
    );
}


function setScanServerStatus(
    message,
    isError
) {
    setInlineMessage(
        elements.scanServerStatus,
        elements.scanServerError,
        message,
        isError
    );
}


function setBaselineHistoryMessage(
    message,
    isError
) {
    setInlineMessage(
        elements.baselineHistoryStatus,
        elements.baselineHistoryError,
        message,
        isError
    );
}


function setInlineMessage(
    statusElement,
    errorElement,
    message,
    isError
) {
    if (isError) {
        statusElement.textContent = "";
        errorElement.hidden = false;
        errorElement.textContent = message;
    } else {
        errorElement.hidden = true;
        errorElement.textContent = "";
        statusElement.textContent = message;
    }
}


function openScanDetailFromAttention(item) {
    openScanDetail(item.selectionId);
}


function openScanDetailFromResult(item) {
    openScanDetail(item.selectionId);
}


function openScanDetail(selectionId) {
    if (!selectionId) {
        return;
    }

    mcpUiState.scanDetail.selectionId = selectionId;
    mcpUiState.scanDetail.selectedFindingIndex = 0;
    showView(
        "scan-detail",
        {
            focusTitle: true,
        }
    );
}


function closeScanDetail() {
    showView(
        "dashboard",
        {
            focusTitle: true,
        }
    );
}


function renderScanDetail() {
    if (!elements.scanDetailTitle) {
        return;
    }

    const detail = getScanDetailData();
    const serverName =
        detail.server?.serverName ||
        detail.selectionId ||
        "MCP 서버";

    elements.scanDetailTitle.textContent = `${serverName} 상세 결과`;

    renderScanDetailRisk(detail);
    renderScanDetailMeta(detail);
    renderScanDetailSeveritySummary(detail);
    renderScanDetailBaselineComparison(detail);
    renderScanDetailFindingList(detail);
    renderScanDetailFindingDetail(
        detail.findings[detail.selectedFindingIndex] || null
    );
}


function getScanDetailData() {
    const selectionId = mcpUiState.scanDetail.selectionId;
    const server = findServerBySelectionId(selectionId);
    const result = selectionId
        ? mcpUiState.scanBatch.resultsBySelectionId.get(selectionId)
        : null;
    const scan = result?.dynamic_scan_result?.scan_result || null;
    const findings = Array.isArray(scan?.findings)
        ? scan.findings
        : [];
    const selectedFindingIndex = clampFindingIndex(
        mcpUiState.scanDetail.selectedFindingIndex,
        findings
    );

    mcpUiState.scanDetail.selectedFindingIndex = selectedFindingIndex;

    const comparison =
        result?.comparison_result ||
        result?.candidate?.comparison_result ||
        null;

    return {
        selectionId,
        server,
        result,
        scan,
        findings,
        comparison,
        candidate: result?.candidate || null,
        candidateCreated: Boolean(result?.candidate_created),
        candidateReused: Boolean(result?.candidate_reused),
        rejectedSameSnapshot: Boolean(result?.rejected_same_snapshot),
        severity: getSeveritySummary(result),
        dynamicStatus: result?.dynamic_scan_result?.status || null,
        selectedFindingIndex,
    };
}


function clampFindingIndex(
    index,
    findings
) {
    if (!findings.length) {
        return 0;
    }

    if (!Number.isInteger(index) || index < 0) {
        return 0;
    }

    return Math.min(index, findings.length - 1);
}


function renderScanDetailRisk(detail) {
    const tone = getScanDetailTone(detail);
    const riskCopy = getScanDetailRiskCopy(detail, tone);

    elements.scanDetailRiskPanel.className =
        `scan-detail-risk-panel scan-detail-risk-${tone}`;
    elements.scanDetailRiskIcon.textContent =
        tone === "safe" ? "OK" : "!";
    elements.scanDetailRiskTitle.textContent = riskCopy.title;
    elements.scanDetailRiskDescription.textContent = riskCopy.description;
}


function getScanDetailTone(detail) {
    if (!detail.scan) {
        return "warning";
    }

    if (
        detail.severity.critical > 0 ||
        detail.severity.high > 0
    ) {
        return "danger";
    }

    if (
        detail.severity.medium > 0 ||
        detail.severity.low > 0
    ) {
        return "warning";
    }

    return "safe";
}


function getScanDetailRiskCopy(
    detail,
    tone
) {
    const primaryDangerFinding = detail.findings.find((finding) =>
        ["critical", "high"].includes(
            normalizeFindingSeverity(finding.severity)
        )
    );
    const primaryWarningFinding = detail.findings.find((finding) =>
        ["medium", "low"].includes(
            normalizeFindingSeverity(finding.severity)
        )
    );

    if (!detail.scan) {
        return {
            title: "보안 결과 없음",
            description: "검사가 실패했거나 보안 Finding 결과가 생성되지 않았습니다.",
        };
    }

    if (tone === "danger") {
        return {
            title: "위험 Finding이 있습니다",
            description: primaryDangerFinding
                ? `${primaryDangerFinding.title} 항목이 발견되었습니다.`
                : "Critical 또는 High Finding이 있습니다.",
        };
    }

    if (tone === "warning") {
        return {
            title: "주의 Finding이 있습니다",
            description: primaryWarningFinding
                ? `${primaryWarningFinding.title} 항목을 확인해야 합니다.`
                : "Medium 또는 Low Finding이 있습니다.",
        };
    }

    return {
        title: "안전 상태입니다",
        description: "이번 검사에서 보안 Finding이 발견되지 않았습니다.",
    };
}


function renderScanDetailMeta(detail) {
    const scan = detail.scan || {};
    const source = getSafeScanDetailSource(detail);
    const definitionList = createDefinitionGrid(
        [
            ["Scan ID", scan.scan_id],
            ["Scan type", scan.scan_type],
            ["Source", source],
            ["Started", scan.started_at ? formatDateTime(scan.started_at) : null],
            ["Completed", scan.completed_at ? formatDateTime(scan.completed_at) : null],
            ["Duration", formatDurationMs(scan.duration_ms)],
            [
                "Baseline compared",
                typeof scan.baseline_compared === "boolean"
                    ? String(scan.baseline_compared)
                    : null,
            ],
            ["Status", displayScanStatus(detail.dynamicStatus)],
        ]
    );

    definitionList.classList.add("scan-detail-definition-list");
    elements.scanDetailMeta.replaceChildren(definitionList);
}


function renderScanDetailSeveritySummary(detail) {
    const severityItems = [
        ["critical", detail.severity.critical],
        ["high", detail.severity.high],
        ["medium", detail.severity.medium],
        ["low", detail.severity.low],
    ];
    const fragment = document.createDocumentFragment();

    severityItems.forEach(([label, count]) => {
        const item = document.createElement("article");
        const labelElement = document.createElement("span");
        const countElement = document.createElement("strong");

        item.className = `scan-detail-severity-item scan-detail-severity-${label}`;
        labelElement.textContent = label;
        countElement.textContent = String(numberOrZero(count));

        item.appendChild(labelElement);
        item.appendChild(countElement);
        fragment.appendChild(item);
    });

    elements.scanDetailSeveritySummary.replaceChildren(fragment);
}


function renderScanDetailBaselineComparison(detail) {
    const comparison = detail.comparison;

    elements.scanDetailComparisonSummary.replaceChildren();
    elements.scanDetailToolDiff.replaceChildren();

    if (!comparison) {
        elements.scanDetailBaselineEmpty.hidden = false;
        elements.scanDetailBaselineContent.hidden = true;

        const message = getScanDetailBaselineEmptyMessage(detail);

        elements.scanDetailBaselineEmpty.replaceChildren(
            createInlineStrong(message.title),
            createInlineSpan(message.description)
        );

        return;
    }

    elements.scanDetailBaselineEmpty.hidden = true;
    elements.scanDetailBaselineContent.hidden = false;

    renderScanDetailComparisonSummary(comparison, detail);
    renderScanDetailToolDiff(comparison);
}

function getScanDetailBaselineEmptyMessage(detail) {
    if (detail.candidateCreated && !detail.comparison) {
        return {
            title: "최초 기준선 후보가 생성되었습니다.",
            description:
                "비교할 승인 기준선이 없어 현재 Snapshot이 최초 후보로 생성되었습니다.",
        };
    }

    if (detail.rejectedSameSnapshot) {
        return {
            title: "이전에 거절한 변경과 동일합니다.",
            description:
                "동일한 Snapshot이므로 새로운 비교 후보가 생성되지 않았습니다.",
        };
    }

    if (!detail.result) {
        return {
            title: "표시할 검사 결과가 없습니다.",
            description:
                "현재 브라우저 세션에 해당 서버의 검사 결과가 없습니다.",
        };
    }

    return {
        title: "기준선 비교 결과가 없습니다.",
        description:
            "승인 기준선이 없거나 이번 검사에서 비교 결과가 생성되지 않았습니다.",
    };
}

function renderScanDetailComparisonSummary(
    comparison,
    detail
) {
    const fragment = document.createDocumentFragment();

    fragment.appendChild(
        createCandidateBlockTitle("기준선 비교 요약")
    );
    fragment.appendChild(
        createComparisonSummaryDetails(
            comparison,
            detail.candidate?.candidate_id || null
        )
    );

    elements.scanDetailComparisonSummary.replaceChildren(fragment);
}


function renderScanDetailToolDiff(comparison) {
    const fragment = document.createDocumentFragment();

    fragment.appendChild(
        createCandidateBlockTitle("Tool Metadata 변경")
    );
    fragment.appendChild(
        createToolDiffFragment(comparison)
    );

    elements.scanDetailToolDiff.replaceChildren(fragment);
}


function createComparisonSummaryDetails(
    comparison,
    candidateId
) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const cardGrid = document.createElement("span");
    const body = document.createElement("div");
    const detailItems = [
        [
            "승인 기준선 Tool 스냅샷 ID",
            comparison.approved_snapshot_id,
        ],
        [
            "후보 Tool 스냅샷 ID",
            comparison.current_snapshot_id,
        ],
        [
            "승인 기준선 Tool 스냅샷 해시",
            comparison.approved_snapshot_hash_prefix,
        ],
        [
            "후보 Tool 스냅샷 해시",
            comparison.current_snapshot_hash_prefix,
        ],
        [
            "MCP 등록 정보 변경",
            displayChangePresence(
                comparison.registration_changed
            ),
        ],
        [
            "MCP 연결 설정 변경",
            displayChangePresence(
                comparison.configuration_changed
            ),
        ],
        [
            "기준선 비교 실패 코드",
            comparison.comparison_error_code,
        ],
        [
            "Candidate ID",
            candidateId,
        ],
    ];

    details.className =
        "tool-diff-item comparison-summary-details";
    summary.className = "comparison-summary-toggle";
    summary.title = "기준선 비교 세부정보 열기";
    cardGrid.className = "comparison-summary-grid";
    body.className = "tool-diff-body";

    for (const [label, value, tone] of [
        ["추가 Tool", comparison.added_count, "added"],
        ["삭제 Tool", comparison.removed_count, "removed"],
        ["변경 Tool", comparison.changed_count, "changed"],
        ["변경 없음 Tool", comparison.unchanged_count, "unchanged"],
    ]) {
        const card = document.createElement("span");
        const labelElement = document.createElement("span");
        const valueElement = document.createElement("strong");

        card.className =
            `comparison-summary-card comparison-summary-card-${tone}`;
        labelElement.textContent = label;
        valueElement.textContent = valueOrDash(value);

        card.appendChild(labelElement);
        card.appendChild(valueElement);
        cardGrid.appendChild(card);
    }

    summary.appendChild(cardGrid);
    body.appendChild(createDefinitionGrid(detailItems));
    details.appendChild(summary);
    details.appendChild(body);

    return details;
}


function createToolDiffFragment(comparison) {
    const fragment = document.createDocumentFragment();
    const changes = Array.isArray(comparison?.tool_changes)
        ? comparison.tool_changes.filter(
            (change) => change.change_type !== "unchanged"
        )
        : [];

    if (!changes.length) {
        fragment.appendChild(
            createEmptyState(
                "표시할 Tool 변경이 없습니다.",
                "추가, 삭제 또는 변경된 Tool이 없습니다."
            )
        );

        return fragment;
    }

    const list = document.createElement("div");
    list.className = "tool-diff-list";

    for (const change of changes) {
        list.appendChild(createToolDiffItem(change));
    }

    fragment.appendChild(list);

    return fragment;
}

function getSafeScanDetailSource(detail) {
    const scan = detail.scan || {};
    const serverName =
        detail.result?.dynamic_scan_result?.target?.server_name ||
        detail.server?.serverName ||
        detail.selectionId;

    if (
        typeof scan.source === "string" &&
        scan.source.startsWith("mcp:")
    ) {
        return scan.source;
    }

    if (serverName) {
        return `mcp:${serverName}`;
    }

    return scan.source_type || null;
}


function formatDurationMs(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return "-";
    }

    if (value < 1000) {
        return `${value}ms`;
    }

    return `${(value / 1000).toFixed(2)}s`;
}


function renderScanDetailFindingList(detail) {
    elements.scanDetailFindingList.replaceChildren();
    elements.scanDetailFindingCount.textContent =
        `(${detail.findings.length})`;

    if (!detail.findings.length) {
        elements.scanDetailFindingEmpty.hidden = false;
        elements.scanDetailFindingList.hidden = true;
        return;
    }

    elements.scanDetailFindingEmpty.hidden = true;
    elements.scanDetailFindingList.hidden = false;

    detail.findings.forEach((finding, index) => {
        elements.scanDetailFindingList.appendChild(
            createScanDetailFindingItem(
                finding,
                index,
                index === detail.selectedFindingIndex
            )
        );
    });
}


function createScanDetailFindingItem(
    finding,
    index,
    selected
) {
    const button = document.createElement("button");
    const badge = document.createElement("span");
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const arrow = document.createElement("span");
    const severity = normalizeFindingSeverity(finding.severity);

    button.className = "scan-detail-finding-item";
    button.type = "button";
    button.dataset.findingIndex = String(index);
    copy.className = "scan-detail-finding-copy";
    meta.className = "scan-detail-finding-meta";

    if (selected) {
        button.classList.add("is-selected");
        button.setAttribute("aria-current", "true");
    }

    badge.className = `severity-badge severity-badge-${severity}`;
    badge.textContent = valueOrDash(finding.severity || severity);
    title.textContent = finding.title || finding.id || "Finding";
    meta.textContent = [
        finding.confidence,
        finding.category,
    ].filter(Boolean).join(" / ");
    arrow.className = "scan-detail-finding-arrow";
    arrow.textContent = ">";

    copy.appendChild(title);
    copy.appendChild(meta);
    button.appendChild(badge);
    button.appendChild(copy);
    button.appendChild(arrow);
    button.addEventListener(
        "click",
        () => selectScanDetailFinding(index)
    );

    return button;
}


function selectScanDetailFinding(index) {
    mcpUiState.scanDetail.selectedFindingIndex = index;
    renderScanDetail();
}


function renderScanDetailFindingDetail(finding) {
    elements.scanDetailFindingDetail.replaceChildren();

    if (!finding) {
        elements.scanDetailFindingDetail.hidden = true;
        elements.scanDetailFindingDetailEmpty.hidden = false;
        return;
    }

    const severity = normalizeFindingSeverity(finding.severity);
    const definitionList = createDefinitionGrid(
        [
            ["식별자", finding.id],
            ["제목", finding.title],
            ["위험도", finding.severity || severity],
            ["신뢰도", finding.confidence],
            ["분류", finding.category],
            ["OWASP", finding.owasp],
            ["대상", finding.target],
            ["위치", finding.location],
            ["민감정보 마스킹", finding.redacted],
        ]
    );

    definitionList.classList.add("scan-detail-definition-list");
    elements.scanDetailFindingDetail.appendChild(definitionList);
    elements.scanDetailFindingDetail.appendChild(
        createScanDetailTextBlock(
            "근거 원문",
            finding.evidence
        )
    );
    elements.scanDetailFindingDetail.appendChild(
        createScanDetailTextBlock(
            "권장 조치",
            finding.recommendation
        )
    );

    elements.scanDetailFindingDetailEmpty.hidden = true;
    elements.scanDetailFindingDetail.hidden = false;
}


function createScanDetailTextBlock(
    title,
    value
) {
    const section = document.createElement("section");
    const heading = document.createElement("h4");
    const body = document.createElement("div");

    heading.textContent = title;
    body.className = "scan-detail-evidence";
    body.textContent = valueOrDash(value);
    section.appendChild(heading);
    section.appendChild(body);

    return section;
}


function normalizeFindingSeverity(value) {
    const severity = String(value || "info").trim().toLowerCase();

    if (
        severity === "critical" ||
        severity === "high" ||
        severity === "medium" ||
        severity === "low" ||
        severity === "info"
    ) {
        return severity;
    }

    return "info";
}


function renderDashboardSummary(state) {
    renderStatusBanner(state);
    renderSummaryCounts(state.counts);
    renderAttentionItems(state.attentionItems);
    renderLastUpdated(state.lastUpdatedAt);
}


function renderStatusBanner(state) {
    const status = state.status || "idle";
    const tone = bannerToneByStatus[status] || "unscanned";

    elements.dashboardStatusBanner.className =
        `status-banner status-banner-${tone}`;
    elements.dashboardStatusIcon.textContent =
        bannerIconByTone[tone] || "!";
    elements.dashboardStatusLabel.textContent = state.label;
    elements.dashboardHeadline.textContent = state.headline;
    elements.dashboardDescription.textContent = state.description;
}


function renderSummaryCounts(counts) {
    elements.dashboardSafeCount.textContent = counts.safe ?? 0;
    elements.dashboardWarningCount.textContent = counts.warning ?? 0;
    elements.dashboardDangerCount.textContent = counts.danger ?? 0;
}


function renderAttentionItems(items) {
    elements.dashboardAttentionList.replaceChildren();

    if (!items.length) {
        elements.dashboardAttentionEmpty.hidden = false;
        elements.dashboardAttentionList.hidden = true;
        return;
    }

    elements.dashboardAttentionEmpty.hidden = true;
    elements.dashboardAttentionList.hidden = false;

    for (const item of items) {
        elements.dashboardAttentionList.appendChild(
            createAttentionItem(item)
        );
    }
}


function createAttentionItem(item) {
    const container = document.createElement("article");
    const badge = document.createElement("span");
    const copy = document.createElement("div");
    const serverName = document.createElement("strong");
    const title = document.createElement("span");
    const actions = document.createElement("div");
    const action = document.createElement("button");
    const detailAction = document.createElement("button");
    const tone = normalizeAttentionTone(item.status);

    container.className = "attention-item";
    actions.className = "attention-actions";
    badge.className = `attention-badge attention-badge-${tone}`;
    badge.textContent =
        item.statusLabel || attentionLabelByTone[tone] || "주의";

    serverName.textContent = item.serverName || "-";
    title.textContent = item.title || "확인이 필요한 항목";
    copy.appendChild(serverName);
    copy.appendChild(document.createTextNode(" "));
    copy.appendChild(title);

    action.className = "secondary-button";
    action.type = "button";
    action.textContent = item.actionLabel || "서버 보기";
    detailAction.className = "secondary-button";
    detailAction.type = "button";
    detailAction.textContent = "상세 보기";

    if (item.actionType === "none") {
        action.disabled = true;
        action.setAttribute("aria-disabled", "true");
        detailAction.disabled = true;
        detailAction.setAttribute("aria-disabled", "true");
    } else {
        action.addEventListener(
            "click",
            () => handleAttentionAction(item)
        );
        detailAction.addEventListener(
            "click",
            () => openScanDetailFromAttention(item)
        );
    }

    actions.appendChild(action);
    actions.appendChild(detailAction);

    container.appendChild(badge);
    container.appendChild(copy);
    container.appendChild(actions);

    return container;
}


function handleAttentionAction(item) {
    if (item.actionType === "scan" && item.selectionId) {
        mcpUiState.selection.selectedServerIds.add(item.selectionId);
        renderAllMcpViews();
        showView(
            "scan-start",
            {
                focusTitle: true,
            }
        );
        return;
    }

    if (item.selectionId) {
        selectServerForManagement(item.selectionId);
        showView(
            "server-management",
            {
                focusTitle: true,
            }
        );
    }
}


function normalizeAttentionTone(status) {
    return attentionToneByStatus[status] || "unscanned";
}


function renderLastUpdated(value) {
    if (value) {
        elements.dashboardLastUpdated.textContent = formatDateTime(value);
        elements.dashboardLastUpdated.title = value;
    } else {
        elements.dashboardLastUpdated.textContent = "아직 갱신되지 않음";
        elements.dashboardLastUpdated.removeAttribute("title");
    }
}


function formatDateTime(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "아직 갱신되지 않음";
    }

    return new Intl.DateTimeFormat(
        "ko-KR",
        {
            dateStyle: "medium",
            timeStyle: "short",
        }
    ).format(date);
}


function handleFileSelection() {
    const selectedFile = elements.toolsFile.files[0];

    if (selectedFile) {
        elements.sampleSelect.value = "";

        setStatus(
            "idle",
            `선택한 파일: ${selectedFile.name}`
        );
    }
}


function handleSampleSelection() {
    const sampleId = elements.sampleSelect.value;

    if (sampleId) {
        elements.toolsFile.value = "";

        const selectedOption =
            elements.sampleSelect.selectedOptions[0];

        setStatus(
            "idle",
            `선택한 샘플: ${selectedOption.textContent}`
        );
    }
}


async function loadSamples() {
    setStatus(
        "loading",
        "연습 샘플 목록을 불러오는 중입니다."
    );

    try {
        const samples = await apiFetch("/api/samples");

        renderSampleOptions(samples || []);

        setStatus(
            "idle",
            "검사할 파일이나 샘플을 선택하세요."
        );
    } catch (error) {
        setStatus(
            "error",
            `샘플 목록을 불러오지 못했습니다. ${getErrorMessage(
                error,
                "요청에 실패했습니다."
            )}`
        );
    }
}


function renderSampleOptions(samples) {
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
            "tools.json 파일 또는 연습 샘플을 선택하세요."
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
            `${result.summary.finding_count}개의 Finding을 탐지했습니다.`
        );
    } catch (error) {
        setStatus(
            "error",
            `검사에 실패했습니다: ${getErrorMessage(
                error,
                "요청에 실패했습니다."
            )}`
        );
    } finally {
        setScanningState(false);
    }
}


async function scanUploadedFile(file) {
    const formData = new FormData();

    formData.append("file", file);

    return apiFetch(
        "/api/scans/upload",
        {
            method: "POST",
            body: formData,
        }
    );
}


async function scanSample(sampleId) {
    const encodedSampleId =
        encodeURIComponent(sampleId);

    return apiFetch(
        `/api/scans/sample/${encodedSampleId}`,
        {
            method: "POST",
        }
    );
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
            "보안 Finding을 발견하지 않았습니다.";

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
        finding.fingerprint || finding.fingerprint_hash_prefix,
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
        isScanning ? "검사 중..." : "검사 시작";

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
        "아직 실행한 검사가 없습니다.";

    clearFindingDetail();

    disableDownloadLink(
        elements.markdownDownload
    );

    disableDownloadLink(
        elements.jsonDownload
    );
}


function findServerBySelectionId(selectionId) {
    return mcpUiState.serverCatalog.servers.find(
        (server) => server.selectionId === selectionId
    );
}


function findServerByTargetKey(monitoringTargetKey) {
    return mcpUiState.serverCatalog.servers.find(
        (server) => server.monitoringTargetKey === monitoringTargetKey
    );
}


function hasPersistedMonitoringState(server) {
    if (!server) {
        return false;
    }

    return (
        (typeof server.stateVersion === "number" && server.stateVersion >= 1) ||
        Boolean(
            server.lastScanStatus &&
            server.lastScanStatus !== "not_scanned"
        ) ||
        Boolean(server.currentApprovedId) ||
        server.pendingCandidateCount > 0 ||
        server.rejectedCandidateCount > 0
    );
}


function isMonitoringNotFoundError(error) {
    return (
        error &&
        (
            error.statusCode === 404 ||
            error.errorCode === "monitoring_not_found"
        )
    );
}


function createEmptyState(
    title,
    description
) {
    const container = document.createElement("div");
    const strong = document.createElement("strong");
    const span = document.createElement("span");

    container.className = "empty-state";
    strong.textContent = title;
    span.textContent = description;

    container.appendChild(strong);
    container.appendChild(span);

    return container;
}


function createStatusBadge(
    tone,
    label
) {
    const badge = document.createElement("span");

    badge.className = `status-badge status-badge-${tone}`;
    badge.textContent = label;

    return badge;
}


function createProgressBadge(status) {
    return createStatusBadge(
        `progress-${status}`,
        progressStatusLabelByValue[status] || "대기 중"
    );
}


function displayRepresentativeStatus(status) {
    const labels = {
        safe: "안전",
        warning: "주의",
        danger: "위험",
        unscanned: "검사 필요",
    };

    return labels[status] || "검사 필요";
}


function displayProduct(value) {
    return displayMappedValue(value, productLabelByValue);
}


function displayScope(value) {
    return displayMappedValue(value, scopeLabelByValue);
}


function displayTransport(value) {
    return displayMappedValue(value, transportLabelByValue);
}


function displayScanStatus(value) {
    return displayMappedValue(value, scanStatusLabelByValue);
}


function displayBaselineLifecycle(value) {
    return displayMappedValue(value, baselineLifecycleLabelByValue);
}


function displayComparisonStatus(value) {
    return displayMappedValue(value, comparisonStatusLabelByValue);
}


function displayVerificationStatus(value) {
    return displayMappedValue(value, verificationStatusLabelByValue);
}


function displayEnabledState(value) {
    return displayMappedValue(value, enabledStateLabelByValue);
}


function displaySupportState(value) {
    return displayMappedValue(value, supportStateLabelByValue);
}


function displayHistoryEvent(value) {
    return displayMappedValue(value, historyEventLabelByValue);
}


function displayHistoryReason(value) {
    if (!value) {
        return "기록된 처리 사유 없음";
    }

    return historyReasonLabelByValue[value] || "기타 처리 사유";
}


function getTimestamp(value) {
    const timestamp = new Date(value).getTime();

    return Number.isNaN(timestamp) ? 0 : timestamp;
}


function displayMappedValue(
    value,
    mapping
) {
    if (!value) {
        return "알 수 없음";
    }

    return mapping[value] || String(value);
}


function displayChangePresence(value) {
    if (typeof value !== "boolean") {
        return "-";
    }

    return value ? "있음" : "없음";
}


function displayBooleanValue(value) {
    if (typeof value !== "boolean") {
        return "-";
    }

    return value ? "예" : "아니요";
}


function valueOrDash(value) {
    if (value === null || value === undefined || value === "") {
        return "-";
    }

    return String(value);
}


function setText(
    element,
    value
) {
    element.textContent = valueOrDash(value);
}


function setDateText(
    element,
    value
) {
    if (!value) {
        element.textContent = "-";
        element.removeAttribute("datetime");
        element.removeAttribute("title");
        return;
    }

    element.textContent = formatDateTime(value);
    element.setAttribute("datetime", value);
    element.title = value;
}
