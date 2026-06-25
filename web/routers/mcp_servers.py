from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Path as PathParam, Query

from core.dynamic_scan_models import DiscoveryContext
from core.mcp_baseline_store import (
    FileMcpBaselineRepository,
    get_default_monitoring_root,
)
from core.mcp_monitoring_service import McpMonitoringService
from web.mcp_schemas import (
    BaselineCandidateResponse,
    BaselineHistoryDeletionRequest,
    BaselineHistoryDeletionResponse,
    BaselineHistoryListResponse,
    BaselineRevocationRequest,
    BaselineRevocationResponse,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    McpServerListResponse,
    McpServerScanRequest,
    MonitoredScanResponse,
    MonitoringGroupResponse,
    MonitoringStateResponse,
)


router = APIRouter(prefix="/api/mcp", tags=["mcp-monitoring"])

MonitoringTargetKeyParam = PathParam(pattern=r"^mcptgt_[0-9a-f]{32}$")
MonitoringGroupKeyParam = PathParam(pattern=r"^mcpgrp_[0-9a-f]{32}$")
CandidateIdParam = PathParam(pattern=r"^cand_[A-Za-z0-9_-]{1,128}$")

DiscoveryContextFactory = Callable[[bool], DiscoveryContext]


@lru_cache(maxsize=1)
def get_mcp_monitoring_service() -> McpMonitoringService:
    repository = FileMcpBaselineRepository(get_default_monitoring_root())
    return McpMonitoringService(repository)


def get_discovery_context(
    include_trusted_project_config: bool = False,
) -> DiscoveryContext:
    current_directory = Path.cwd()
    return DiscoveryContext(
        current_working_directory=current_directory,
        project_root=_find_project_root(current_directory),
        user_home=Path.home(),
        include_trusted_project_config=include_trusted_project_config,
    )


def get_discovery_context_factory() -> DiscoveryContextFactory:
    return get_discovery_context


@router.get("/servers", response_model=McpServerListResponse)
def list_mcp_servers(
    include_trusted_project_config: bool = Query(default=False),
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
    context_factory: DiscoveryContextFactory = Depends(
        get_discovery_context_factory
    ),
) -> McpServerListResponse:
    context = context_factory(include_trusted_project_config)
    result = service.list_monitored_servers(context)
    return McpServerListResponse.from_core(
        result,
        include_trusted_project_config=include_trusted_project_config,
    )


@router.post(
    "/servers/{selection_id}/scan",
    response_model=MonitoredScanResponse,
)
async def scan_mcp_server(
    request: McpServerScanRequest,
    selection_id: str = PathParam(min_length=1),
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
    context_factory: DiscoveryContextFactory = Depends(
        get_discovery_context_factory
    ),
) -> MonitoredScanResponse:
    context = context_factory(request.include_trusted_project_config)
    result = await service.scan_monitored_server(
        context,
        selection_id,
        reconsider_rejected=request.reconsider_rejected,
    )
    return MonitoredScanResponse.from_core(result)


@router.get(
    "/targets/{monitoring_target_key}",
    response_model=MonitoringStateResponse,
)
def get_monitoring_target_state(
    monitoring_target_key: str = MonitoringTargetKeyParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> MonitoringStateResponse:
    state = service.get_monitoring_target_state(monitoring_target_key)
    return MonitoringStateResponse.from_core(state)


@router.get(
    "/groups/{monitoring_group_key}",
    response_model=MonitoringGroupResponse,
)
def get_monitoring_group(
    monitoring_group_key: str = MonitoringGroupKeyParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> MonitoringGroupResponse:
    group = service.get_monitoring_group(monitoring_group_key)
    return MonitoringGroupResponse.from_core(group)


@router.get(
    "/candidates/{candidate_id}",
    response_model=BaselineCandidateResponse,
)
def get_monitoring_candidate(
    candidate_id: str = CandidateIdParam,
    monitoring_target_key: str | None = Query(
        default=None,
        pattern=r"^mcptgt_[0-9a-f]{32}$",
    ),
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> BaselineCandidateResponse:
    candidate = service.get_candidate(
        candidate_id,
        monitoring_target_key=monitoring_target_key,
    )
    return BaselineCandidateResponse.from_core(candidate)


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=CandidateDecisionResponse,
)
def approve_monitoring_candidate(
    request: CandidateDecisionRequest,
    candidate_id: str = CandidateIdParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> CandidateDecisionResponse:
    result = service.approve_candidate(
        candidate_id,
        monitoring_target_key=request.monitoring_target_key,
        expected_state_version=request.expected_state_version,
        safe_reason_code=request.safe_reason_code,
    )
    return CandidateDecisionResponse.from_core(result)


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=CandidateDecisionResponse,
)
def reject_monitoring_candidate(
    request: CandidateDecisionRequest,
    candidate_id: str = CandidateIdParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> CandidateDecisionResponse:
    result = service.reject_candidate(
        candidate_id,
        monitoring_target_key=request.monitoring_target_key,
        expected_state_version=request.expected_state_version,
        safe_reason_code=request.safe_reason_code,
    )
    return CandidateDecisionResponse.from_core(result)


@router.post(
    "/targets/{monitoring_target_key}/baseline/revoke",
    response_model=BaselineRevocationResponse,
)
def revoke_current_baseline(
    request: BaselineRevocationRequest,
    monitoring_target_key: str = MonitoringTargetKeyParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> BaselineRevocationResponse:
    result = service.revoke_current_baseline(
        monitoring_target_key,
        expected_state_version=request.expected_state_version,
        expected_current_approved_id=request.expected_current_approved_id,
        safe_reason_code=request.safe_reason_code,
    )
    return BaselineRevocationResponse.from_core(result)


@router.get(
    "/targets/{monitoring_target_key}/history",
    response_model=BaselineHistoryListResponse,
)
def list_monitoring_target_history(
    monitoring_target_key: str = MonitoringTargetKeyParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> BaselineHistoryListResponse:
    records = service.list_target_history(monitoring_target_key)
    return BaselineHistoryListResponse.from_core(
        monitoring_target_key,
        records,
    )


@router.delete(
    "/targets/{monitoring_target_key}/history",
    response_model=BaselineHistoryDeletionResponse,
)
def delete_monitoring_target_history(
    request: BaselineHistoryDeletionRequest,
    monitoring_target_key: str = MonitoringTargetKeyParam,
    service: McpMonitoringService = Depends(get_mcp_monitoring_service),
) -> BaselineHistoryDeletionResponse:
    result = service.delete_target_history(
        monitoring_target_key,
        expected_state_version=request.expected_state_version,
    )
    return BaselineHistoryDeletionResponse.from_core(result)


def _find_project_root(current_directory: Path) -> Path:
    resolved = current_directory.resolve(strict=False)
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved
