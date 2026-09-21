"""Personal project-status aggregation for the configured Backlog user."""

from backlog_tool import presenter
from backlog_tool.settings import view_base_url
from workflows import story_task_overview
import workflows.resolve_bug as bug_workflow


def get_my_project_status(config, project_key=None, start_path=None):
    """Return one AI-ready personal status view for a project.

    This intentionally aggregates the two normal personal work queues so an
    agent can answer one user intent with one MCP call.
    """
    stories_tasks = story_task_overview.my_story_task_overview(
        config,
        project_key=project_key,
        start_path=start_path,
    )
    bugs_raw = bug_workflow.my_open_bugs_raw(
        config,
        project_key=project_key,
        start_path=start_path,
    )
    base_url = view_base_url(config)
    bugs = [
        presenter.compact_issue(item, view="compact", base_url=base_url)
        for item in bugs_raw
    ]

    overdue = [
        item for item in stories_tasks
        if item.get("daysUntilDue") is not None and item["daysUntilDue"] < 0
    ]
    due_soon = [
        item for item in stories_tasks
        if item.get("dueAlertLevel") == 2
    ]

    return {
        "storiesAndTasks": stories_tasks,
        "openBugs": bugs,
        "summary": {
            "storyTaskCount": len(stories_tasks),
            "openBugCount": len(bugs),
            "overdueCount": len(overdue),
            "dueSoonCount": len(due_soon),
        },
    }
