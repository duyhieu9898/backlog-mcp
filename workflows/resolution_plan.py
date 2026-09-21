from dataclasses import dataclass, field
from typing import Any

from backlog_tool.resolver import resolve_custom_field_defaults, resolve_status


@dataclass
class ResolutionPlan:
    """Semantic resolve intent before Backlog-specific field mapping."""

    status: str
    assignee_id: int
    start_date: str | None = None
    due_date: str | None = None
    estimated_hours: float | int | None = None
    actual_hours: float | int | None = None
    comment: str | None = None
    custom_fields: dict[str, Any] = field(default_factory=dict)


def resolution_plan_to_payload(project: dict[str, Any], plan: ResolutionPlan) -> dict[str, Any]:
    """Map semantic resolve intent to Backlog's API payload representation."""
    payload: dict[str, Any] = {
        "statusId": resolve_status(project, plan.status),
        "assigneeId": plan.assignee_id,
    }
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
