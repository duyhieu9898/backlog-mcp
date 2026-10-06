from dataclasses import dataclass, field
from typing import Any

from backlog_tool.resolver import resolve_custom_field_defaults, resolve_status


@dataclass
class ResolutionPlan:
    """Semantic resolve intent before Backlog-specific field mapping."""

    # None for a follow-up on a bug already resolved and with QC: status and assignee stay as they are.
    status: str | None = None
    assignee_id: int | None = None
    start_date: str | None = None
    due_date: str | None = None
    estimated_hours: float | int | None = None
    actual_hours: float | int | None = None
    comment: str | None = None
    custom_fields: dict[str, Any] = field(default_factory=dict)


def resolution_plan_to_payload(project: dict[str, Any], plan: ResolutionPlan) -> dict[str, Any]:
    """Map semantic resolve intent to Backlog's API payload representation."""
    payload: dict[str, Any] = {}
    if plan.status is not None:
        payload["statusId"] = resolve_status(project, plan.status)
    if plan.assignee_id is not None:
        payload["assigneeId"] = plan.assignee_id
    if plan.start_date is not None:
        payload["startDate"] = plan.start_date
    if plan.due_date is not None:
        payload["dueDate"] = plan.due_date
    if plan.estimated_hours is not None:
        payload["estimatedHours"] = plan.estimated_hours
    if plan.actual_hours is not None:
        payload["actualHours"] = plan.actual_hours
    if plan.comment:
        payload["comment"] = plan.comment
    if plan.custom_fields:
        payload.update(resolve_custom_field_defaults(project, plan.custom_fields))
    return payload
