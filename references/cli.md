# CLI Reference

Run all commands from the skill directory with `python3 scripts/backlog.py`.

## Global Behavior

- Use compact output by default.
- Add `--json-full` anywhere in the command for raw JSON.
- Treat write commands as dry runs until `--apply` is supplied.
- Read errors from stderr.
- Use `--project KEY` to override workspace project key resolution for one command.
- When executing the CLI from a different workspace directory, use `uv --project /path/to/backlog-mcp run backlog-cli` instead of `--directory` to preserve the active working directory (CWD) context for path-based project resolution.

## Config And Project Metadata

```bash
python3 scripts/backlog.py config list-projects
python3 scripts/backlog.py config show
python3 scripts/backlog.py project inspect AQM
python3 scripts/backlog.py project inspect OOP --stdout
```

`project inspect` refreshes `config/projects/<KEY>.json`.

## Issues

```bash
python3 scripts/backlog.py issue get OOP-123
python3 scripts/backlog.py issue list --project OOP --query keyword
python3 scripts/backlog.py issue list --type Bug --view bug
python3 scripts/backlog.py issue list --type Story --type Task --view story
python3 scripts/backlog.py issue list --all
```

Create an issue:

```bash
python3 scripts/backlog.py issue create "Summary" \
  --issue-type Bug \
  --desc "Description" \
  --category "Category" \
  --custom key=value \
  [--apply]
```

Update an issue:

```bash
python3 scripts/backlog.py issue update OOP-123 \
  --status "In Progress" \
  --comment "Comment" \
  --custom key=value \
  [--apply]
```

Create and update also accept `--project`, `--priority`, `--assignee`,
`--category`, `--start-date`, `--due-date`, `--estimated-hours`,
`--actual-hours`, and repeatable `--custom KEY=VALUE`.

## Bug Workflows

```bash
python3 scripts/backlog.py bug list --project AQM
python3 scripts/backlog.py bug context AQM-123
python3 scripts/backlog.py bug rules
python3 scripts/backlog.py bug fields
python3 scripts/backlog.py bug fields bug_origin
python3 scripts/backlog.py bug resolve AQM-123 \
  --actual-hours 1.5 \
  --fix-description "Save issue" \
  --comment "Ready for QC." \
  --commit 30e0ca6 \
  [--apply]
python3 scripts/backlog.py bug create-ut OOP-123 \
  "A020100|FE" \
  "Issue description" \
  --project OOP \
  [--apply]
```

Audit workflow contracts after changing config, policy, guidance, or project
catalogs:

```bash
python3 scripts/backlog.py config audit-workflows
```

The command exits with an error when required keys, template placeholders,
policy field groups, story output fields, or project catalog labels drift.

`bug context` includes both the current assignee and `createdUser` reporter.
Resolve assigns the issue to that reporter by default. Its dry-run shows the
assignee names/IDs, assignment source, and status transition before applying.

`bug fields` provides option guidance only for `qc_activity`, `bug_origin`,
and `cause_category`. Workflow-managed values such as `impacted`,
`corrective_action`, and `resolution` are shown in the resolve dry-run.

## Story

```bash
python3 scripts/backlog.py story overview --project AQM
```
