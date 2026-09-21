#!/usr/bin/env python3
"""Unified Backlog CLI.

One entry point with grouped subcommands: issue / bug / config / project /
story / metrics. Behaviour is consistent across groups:
- compact output by default, --json-full for raw JSON
- write commands are dry-run by default, --apply to write
- errors go to stderr
- every run is measured into logs/metrics.log
"""
import argparse
import json
import sys
import time
from dataclasses import dataclass

from backlog_tool import presenter
from backlog_tool import journal
from backlog_tool.issue_service import create_issue, get_issue, get_issues, update_issue
from backlog_tool.settings import (
    load_config,
    load_env_file,
    load_project_catalog,
    log_event,
    log_metric,
    project_keys,
    resolve_project_key,
    resolve_project_key_for_issue,
    resolve_user_id,
    save_config,
    summarize_metrics,
    view_base_url,
)
from workflows.guidance import field_guidance, resolve_rules
from workflows.audit import audit_workflows
from workflows.resolve_bug import get_bug_context, resolve_bug
from workflows.story_task_overview import my_story_task_overview
from workflows.ut_bug import create_subtask_bug


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def add_project(parser):
    parser.add_argument("--project", help="Project key. Resolved from workspace if omitted.")


def add_list_controls(parser):
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of issues to fetch.")
    parser.add_argument("--offset", type=int, default=0, help="Zero-based issue offset.")
    parser.add_argument("--sort", help="Backlog issue sort field, e.g. updated, dueDate, priority.")
    parser.add_argument("--order", choices=["asc", "desc"], help="Sort order.")


def add_json_full(parser):
    parser.add_argument("--json-full", dest="json_full", action="store_true",
                        help="Print raw JSON instead of compact output. Works in any position.")


def add_apply(parser):
    parser.add_argument("--apply", action="store_true", help="Write to Backlog. Omit for dry-run.")


def add_issue_fields(parser):
    parser.add_argument("--desc", help="Issue description")
    parser.add_argument("--priority", help="Priority ID or name")
    parser.add_argument("--assignee", help="Assignee user ref from config.users or raw user ID")
    parser.add_argument("--category", help="Category ID or name")
    parser.add_argument("--start-date", help="YYYY-MM-DD")
    parser.add_argument("--due-date", help="YYYY-MM-DD")
    parser.add_argument("--estimated-hours", type=float)
    parser.add_argument("--actual-hours", type=float)
    parser.add_argument("--custom", action="append", default=[], metavar="KEY=VALUE",
                        help="Custom field key/value, e.g. qc_activity='Unit Test'. Repeatable.")


def build_parser():
    parser = argparse.ArgumentParser(prog="backlog", description="Unified Backlog skill CLI.")
    add_json_full(parser)
    parser.add_argument("--table", action="store_true",
                        help="Format list outputs as a Markdown table. Works in any position.")
    groups = parser.add_subparsers(dest="group", required=True)

    # issue ----------------------------------------------------------------
    issue = groups.add_parser("issue", help="Generic issue operations").add_subparsers(dest="action", required=True)

    g = issue.add_parser("get", help="Get an issue by key/id")
    g.add_argument("issue_id")

    g = issue.add_parser("list", help="List/search issues")
    add_project(g)
    add_list_controls(g)
    g.add_argument("--query", help="Search keyword")
    g.add_argument("--all", action="store_true", help="Include Closed issues (default excludes Closed)")
    g.add_argument("--type", action="append", dest="types", metavar="TYPE",
                   help="Filter by issue type name (Bug, Story, Task...). Repeatable.")
    g.add_argument("--view", choices=["compact", "bug"], default="compact",
                   help="Presenter: compact (default), bug (parse description).")

    g = issue.add_parser("create", help="Create an issue (dry-run unless --apply)")
    add_project(g)
    g.add_argument("summary")
    g.add_argument("--issue-type", help="Issue type ID or name")
    g.add_argument("--parent", help="Parent issue key")
    add_issue_fields(g)
    add_apply(g)

    g = issue.add_parser("update", help="Update an issue (dry-run unless --apply)")
    add_project(g)
    g.add_argument("issue_id")
    g.add_argument("--summary")
    g.add_argument("--status", help="Status ID or name")
    g.add_argument("--comment")
    add_issue_fields(g)
    add_apply(g)

    # bug ------------------------------------------------------------------
    bug = groups.add_parser("bug", help="Personal bug workflow").add_subparsers(dest="action", required=True)

    g = bug.add_parser("list", help="List open bugs assigned to me")
    add_project(g)
    add_list_controls(g)
    g.add_argument("--query")

    g = bug.add_parser("context", help="Structured bug context from description")
    g.add_argument("issue_key")

    g = bug.add_parser("resolve", help="Resolve a bug (dry-run unless --apply)")
    g.add_argument("issue_key")
    g.add_argument("--status")
    g.add_argument("--actual-hours", type=float)
    g.add_argument("--estimated-hours", type=float)
    g.add_argument("--qc-activity")
    g.add_argument("--cause-category")
    g.add_argument("--bug-origin")
    g.add_argument("--impacted")
    g.add_argument("--resolution")
    g.add_argument("--comment")
    g.add_argument("--commit", help="Commit hash/ref appended to the update comment")
    g.add_argument("--fix-description", help="Text for Corrective Action: fixed <text lowercased>")
    add_apply(g)

    g = bug.add_parser("create-ut", help="Create a default UT sub-task bug (dry-run unless --apply)")
    add_project(g)
    g.add_argument("parent_key")
    g.add_argument("module")
    g.add_argument("description")
    add_apply(g)

    g = bug.add_parser("rules", help="Print the personal resolve-bug rule")
    add_project(g)

    g = bug.add_parser("fields", help="Print field guidance")
    add_project(g)
    g.add_argument("field", nargs="?")

    # config ---------------------------------------------------------------
    config_group = groups.add_parser("config", help="Skill config").add_subparsers(dest="action", required=True)
    config_group.add_parser("list-projects", help="List configured projects")
    config_group.add_parser("audit-workflows", help="Validate workflow config, policy, and project catalogs")
    config_group.add_parser("show", help="Print full config JSON")

    # project --------------------------------------------------------------
    project_group = groups.add_parser("project", help="Project metadata").add_subparsers(dest="action", required=True)
    g = project_group.add_parser("inspect", help="Refresh config/projects/<KEY>.json")
    g.add_argument("project_key")
    g.add_argument("--stdout", action="store_true", help="Print JSON instead of writing the catalog file")

    # story ----------------------------------------------------------------
    story_group = groups.add_parser("story", help="Story/Task overview").add_subparsers(dest="action", required=True)
    g = story_group.add_parser("overview", help="Story/Task overview assigned to me")
    add_project(g)
    add_list_controls(g)
    g.add_argument("--query")

    return parser


# ---------------------------------------------------------------------------
# Dispatch + presentation
# ---------------------------------------------------------------------------

def command_name(args):
    return f"{args.group}:{getattr(args, 'action', '')}".rstrip(":")


def is_dry_run(args):
    if getattr(args, "action", None) in ("create", "update", "resolve", "create-ut"):
        return not getattr(args, "apply", False)
    return None


def _extract_issue_key(result, args):
    """Best-effort issue key extraction for journal tagging."""
    # Direct issue key from args
    for attr in ("issue_id", "issue_key", "parent_key"):
        value = getattr(args, attr, None)
        if value:
            return str(value)
    # From result dict
    if isinstance(result, dict):
        return result.get("issueKey") or result.get("issue")
    # From list result (first item)
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            return first.get("issueKey")
    return None


def run_handler(config, args):
    group, action = args.group, getattr(args, "action", None)

    if group == "issue":
        if action == "get":
            return get_issue(config, args.issue_id)
        if action == "list":
            me = config.get("defaults", {}).get("assignee", "me")
            assignee_id = resolve_user_id(config, me)
            open_only = not getattr(args, "all", False)
            return get_issues(
                config, args.project, args.query, assignee_id,
                open_only=open_only, issue_types=args.types,
                limit=args.limit, offset=args.offset, sort=args.sort, order=args.order,
                start_path=getattr(args, "workspace_path", None),
            )
        if action == "create":
            args.dry_run = not args.apply
            return create_issue(config, args)
        if action == "update":
            args.dry_run = not args.apply
            return update_issue(config, args)

    if group == "bug":
        if action == "list":
            from workflows.resolve_bug import my_open_bugs_raw
            return my_open_bugs_raw(
                config,
                project_key=args.project,
                query=args.query,
                limit=args.limit,
                offset=args.offset,
                sort=args.sort,
                order=args.order,
                start_path=getattr(args, "workspace_path", None),
            )
        if action == "context":
            return get_bug_context(config, args.issue_key)
        if action == "rules":
            return resolve_rules(config, args.project, start_path=getattr(args, "workspace_path", None))
        if action == "fields":
            return field_guidance(args.field, config, args.project, start_path=getattr(args, "workspace_path", None))
        if action == "resolve":
            return resolve_bug(
                config, args.issue_key, dry_run=not args.apply,
                status=args.status, actual_hours=args.actual_hours, estimated_hours=args.estimated_hours,
                qc_activity=args.qc_activity, cause_category=args.cause_category, bug_origin=args.bug_origin,
                impacted=args.impacted, resolution=args.resolution, comment=args.comment,
                commit=args.commit, fix_description=args.fix_description,
                start_path=getattr(args, "workspace_path", None),
            )
        if action == "create-ut":
            return create_subtask_bug(
                config, args.project, args.parent_key, args.module, args.description, dry_run=not args.apply,
                start_path=getattr(args, "workspace_path", None),
            )

    if group == "config":
        return run_config(config, args)
    if group == "project":
        return run_project(config, args)
    if group == "story":
        return my_story_task_overview(
            config,
            project_key=args.project,
            query=args.query,
            limit=args.limit,
            offset=args.offset,
            sort=args.sort,
            order=args.order,
            start_path=getattr(args, "workspace_path", None),
        )
    return None


def run_config(config, args):
    if args.action == "list-projects":
        return config_projects(config)
    if args.action == "show":
        return config
    if args.action == "audit-workflows":
        return audit_workflows(config)
    return None


def config_projects(config):
    rows = []
    for key in project_keys(config):
        try:
            catalog = load_project_catalog(key)
            rows.append({"key": key, "id": catalog.get("id"), "name": catalog.get("name")})
        except Exception:
            rows.append({"key": key, "id": None, "name": "(missing catalog)"})
    return rows


def run_project(config, args):
    from backlog_tool.inspect import build_project_config, write_catalog
    project_config = build_project_config(config, args.project_key)
    if args.stdout:
        return project_config
    path = write_catalog(project_config)
    return {"wrote": path, "key": project_config["key"]}


def present(result, args):
    if getattr(args, "json_full", False):
        return result
    group, action = args.group, getattr(args, "action", None)
    view = getattr(args, "view", "compact")

    if group == "issue" and action == "list":
        return [presenter.compact_issue(item, view=view) for item in result]
    if group == "issue" and action == "get":
        return presenter.compact_issue(result, view=view)
    if group == "issue" and action in ("create", "update"):
        if isinstance(result, dict) and result.get("dryRun"):
            return result
        return presenter.compact_issue(result, view=view)

    if group == "bug" and action == "list":
        return [presenter.compact_issue(item, view=view) for item in result]
    if group == "bug" and action == "context":
        return result
    if group == "bug" and action == "resolve":
        if isinstance(result, dict) and result.get("dryRun"):
            return {
                "dryRun": True, "issue": result.get("issue"), "project": result.get("project"),
                "assignment": result.get("assignment"),
                "changes": result.get("changes", []), "warnings": result.get("warnings", []),
            }
        return presenter.compact_issue(result, view=view)
    if group == "bug" and action == "create-ut":
        if isinstance(result, dict) and result.get("dryRun"):
            return result
        return {"issueKey": result.get("issueKey"), "applied": True}

    if group == "story":
        return result
    return result


@dataclass(frozen=True)
class CommandResult:
    data: object
    text: str


def execute(argv, workspace_path=None):
    """Execute one Backlog command and return both structured and rendered output."""
    load_env_file()
    # Let --json-full, --raw, --full and --table appear in any position (root or after the action).
    json_full = any(t in argv for t in ("--json-full", "--raw", "--full"))
    argv = [token for token in argv if token not in ("--json-full", "--raw", "--full")]
    table = "--table" in argv
    argv = [token for token in argv if token != "--table"]

    parser = build_parser()
    args = parser.parse_args(argv)
    if json_full:
        args.json_full = True
    # Default to table format unless JSON output is requested
    args.table = table or not json_full
    args.workspace_path = workspace_path

    name = command_name(args)
    dry_run = is_dry_run(args)
    config = load_config()

    pre_project = getattr(args, "project", None)
    if args.group in ("issue", "bug", "story"):
        issue_id = getattr(args, "issue_id", None) or getattr(args, "issue_key", None) or getattr(args, "parent_key", None)
        try:
            if issue_id:
                pre_project = resolve_project_key_for_issue(config, issue_id, pre_project, start_path=workspace_path)
            else:
                pre_project = resolve_project_key(config, pre_project, start_path=workspace_path)
        except Exception:
            pre_project = None

    log_event("info", "command_start", command=name, project=pre_project, dry_run=dry_run)
    started = time.monotonic()
    try:
        result = run_handler(config, args)
        presented_data = present(result, args)

        project = getattr(args, "project", None)
        if args.group in ("issue", "bug", "story"):
            issue_key = _extract_issue_key(result, args)
            try:
                if issue_key:
                    project = resolve_project_key_for_issue(config, issue_key, project, start_path=workspace_path)
                else:
                    project = resolve_project_key(config, project, start_path=workspace_path)
            except Exception:
                project = pre_project

        # If --table is specified and the output is a list of issues/stories, format it as a table
        if getattr(args, "table", False) and isinstance(presented_data, list) and args.group in ("issue", "bug", "story"):
            is_story = (args.group == "story" or getattr(args, "view", None) == "story")
            text = presenter.format_issues_as_table(presented_data, is_story_view=is_story)
        else:
            text = json.dumps(presented_data, indent=2, ensure_ascii=False)

        duration_ms = round((time.monotonic() - started) * 1000)
        log_event("info", "command_end", command=name)
        log_metric(name, len(text.encode("utf-8")), duration_ms, "ok", dry_run=dry_run, project=project)
        # Journal: record CLI output for durable cross-session memory.
        if args.group in ("issue", "bug", "story"):
            journal.log_cli(name, text, project=project, issue_key=issue_key)
        # create-ut --apply: surface a friendly link too.
        if args.group == "bug" and getattr(args, "action", None) == "create-ut" and not dry_run and isinstance(result, dict):
            key = result.get("issueKey")
            if key:
                log_event("info", "issue_created", issue=key, url=f"{view_base_url(config)}/view/{key}")
        return CommandResult(data=presented_data, text=text)
    except Exception as error:
        duration_ms = round((time.monotonic() - started) * 1000)
        log_event("error", "command_error", command=name, error=error)
        
        project = getattr(args, "project", None)
        if args.group in ("issue", "bug", "story"):
            issue_id = getattr(args, "issue_id", None) or getattr(args, "issue_key", None) or getattr(args, "parent_key", None)
            try:
                if issue_id:
                    project = resolve_project_key_for_issue(config, issue_id, project, start_path=workspace_path)
                else:
                    project = resolve_project_key(config, project, start_path=workspace_path)
            except Exception:
                project = pre_project

        log_metric(name, 0, duration_ms, "error", dry_run=dry_run, project=project)
        raise


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        result = execute(argv)
        print(result.text)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
