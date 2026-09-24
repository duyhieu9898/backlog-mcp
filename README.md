# Backlog Local MCP

One local stdio MCP server serves every project on this workstation. Source,
configuration, credentials, project catalogs, logs, and metrics all live under
this directory.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cd hieund-backlog-mcp
cp .env.example .env
# Set BACKLOG_API_KEY in .env, then install the locked project environment.
uv sync --extra dev
```

Never commit `.env`.

## Register with Your MCP Client

All clients use the same stdio command. Capture the absolute path first:

```bash
BACKLOG_MCP_DIR="$(pwd)"
```

Then register it in your client's user-level MCP configuration:

```json
{
  "command": "uv",
  "args": ["--project", "/absolute/path/to/hieund-backlog-mcp", "run", "backlog-mcp-server"]
}
```

**Client-specific notes:**

- **Claude Code** — `claude mcp add --transport stdio --scope user backlog -- uv --project "$BACKLOG_MCP_DIR" run backlog-mcp-server`
- **Codex** — `codex mcp add backlog -- uv --project "$BACKLOG_MCP_DIR" run backlog-mcp-server`
- **Claude Desktop / Gemini** — paste the JSON above into the client's user-level MCP config file and restart.

The server is started on demand; no daemon or remote server is required.

## Personal Routing Contract

This MCP is intentionally personal and narrow. It should only be selected when
the user explicitly invokes Backlog (for example, says `backlog` or
`backlog mcp`) or supplies an identifiable Backlog issue key/URL.

Generic requests such as "what should I do?", "project status", or "what is my
plan?" must not be claimed by this MCP without a Backlog activation signal.

Normal personal intents map to domain tools:

| Personal Backlog intent | Preferred tool |
|---|---|
| What do I currently have to do in this Backlog project? | `get_my_project_status` |
| What open bugs are assigned to me? | `get_my_open_bugs` |
| Understand/investigate/fix a specific bug | `get_bug_context` |
| Resolve/close a bug | `resolve_bug` |
| Create a configured UT bug | `create_ut_bug` |

`get_issue`, `get_issues`, `create_issue`, and `update_issue` are escape
hatches for generic/custom operations. `get_bug_rules` and `get_bug_fields` are
diagnostic tools, not normal pre-steps for the personal workflows. Project and
config administration (list projects, inspect/refresh a catalog, show config,
audit workflows) is CLI-only: `backlog-cli config list-projects|show|audit-workflows`
and `backlog-cli project inspect <KEY>`.

The design target is one MCP call per intent. `resolve_bug` is called once with
`mode="apply"` when the user asks to resolve a bug; `create_issue`,
`update_issue` and `create_ut_bug` keep preview → confirm → apply.

## Usage Modes

This server supports two usage modes. Both require `BACKLOG_API_KEY` and a
valid `config/backlog.json`.

### Mode 1 — AI client inside a source repo

The AI client (Claude Code, Codex, Gemini, etc.) is opened **inside a
project's source repository**. The server automatically identifies the active
Backlog project from the workspace context; no `project_key` argument is
needed.

**How project resolution works (in priority order):**

1. Explicit `project_key` tool argument — always wins.
2. `.backlog-project.json` in the repo root (or any ancestor up to `.git`).
3. Directory name of the workspace path matches a configured project key.
4. → Server returns an error instead of guessing.

**Setup for a new repo:**

```bash
# 1. Add the project key to config/backlog.json "projects" list (one-time, per project).
#    Edit config/backlog.json and add "XYZ" to the "projects" array.

# 2. Fetch and cache the project catalog.
uv run backlog-cli project inspect XYZ

# 3. (Optional) Create a .backlog-project.json in the repo root so the server
#    can identify the project even when the directory name does not match.
echo '{"project_key": "XYZ"}' > /path/to/your-repo/.backlog-project.json
```

After these steps, an AI client opened in that repo can call any tool without
supplying `project_key`.

---

### Mode 2 — Standalone agent across any repo

An agent (script, automation, CI job) calls the MCP tools **without a fixed
workspace context**. The agent must supply `project_key` explicitly on every
call.

**Prerequisites before the agent can use a project:**

> **The project must be registered and its catalog must exist locally.**
> The server does not auto-discover or auto-register new Backlog projects.

```bash
# 1. Add the project key to config/backlog.json "projects" list.
#    Edit config/backlog.json and add the key to the "projects" array.

# 2. Fetch and cache the project catalog (required for mutation tools).
uv run backlog-cli project inspect XYZ
```

Once registered, the agent can call any tool by passing `project_key="XYZ"`
explicitly. Read-only tools (`get_issue`, `get_issues`) work without a catalog;
mutation tools and bug workflow tools require it.

**Limitations of Mode 2:**
- A new project cannot be used until steps 1–2 above are completed manually.
- The catalog can become stale; re-run `uv run backlog-cli project inspect XYZ`
  to sync it.

---

The active project is also resolved from the `BACKLOG_WORKSPACE_PATH` or
`CLAUDE_PROJECT_DIR` environment variable passed by the client when no explicit
`project_key` is given.

## Tools

### Issues

| Tool | Description |
|---|---|
| `get_issue` | Get current details of one issue by key or numeric ID. |
| `get_issues` | List issues assigned to the configured user, with filters and pagination. |
| `create_issue` | Create a Backlog issue (`mode="preview"` by default, `"apply"` to submit). |
| `update_issue` | Update fields on an existing issue (`mode="preview"` / `"apply"`). |

Every tool names the issue it acts on `issue_key` (`get_issue` also accepts a numeric ID) and the parent `parent_key`; keys look like `OOP-12748` and are upper-cased and checked against the configured projects before any Backlog call. Arguments are snake_case; a wrong argument name returns an error that suggests the right one and lists the valid parameters. Successful results carry the full structured result as compact JSON text too (lists include `count`), so clients that only show text get the same data.

### Bugs

| Tool | Description |
|---|---|
| `get_my_open_bugs` | List open bugs assigned to the configured user (with `count`; no description — `get_bug_context` gives it for one bug). |
| `get_bug_context` | Get AI-ready context for a specific bug, including its attachments (`id`, `name`, `size`, `isImage`). |
| `resolve_bug` | Resolve a bug with workflow defaults in one `mode="apply"` call. `fix_description`/`commit` are optional (Corrective Action falls back to `fixed <summary>`); guided fields and hours only fill empty values; warnings (e.g. Detected Role is not Tester) never block and are returned with the changes. `mode="preview"` only when asked. |
| `create_ut_bug` | Create a Unit Test sub-task bug under a parent issue (`mode="preview"` / `"apply"`). |
| `get_bug_rules` | Get the resolve-bug workflow rules for a project (or the project of `issue_key`). |
| `get_bug_fields` | Get allowed values and guidance for bug workflow fields (e.g. `qc_activity`, `cause_category`). |

### Personal Work

| Tool | Description |
|---|---|
| `get_my_project_status` | One-call personal Backlog status: assigned Stories/Tasks, deadlines, and open Bugs. |
| `get_my_work_overview` | List assigned Stories and Tasks with deadline and status context when that narrower view is explicitly needed. |

## Resources

| URI | Description |
|---|---|
| `backlog://issue/{issue_key}` | One Backlog issue as full JSON by issue key. |

## Evals

`evals/run.py` runs real agents (`claude -p`, `agy -p`) against a local fake Backlog and grades the MCP call flow of each scenario in `evals/scenarios.json` (see `docs/telemetry.md`):

```bash
uv run python -m evals.run --agent claude --model opus --scenario all --runs 10 --label p6 --timeout 300
```

Latest result (2026-09-24, Claude opus): 69/70 runs pass, every scenario ≥ 9/10, 0 argument errors, up from 12/35 at baseline — see `evals/results/2026-09-24-p6-final/SUMMARY.md`.

## Safety

- Mutation tools (`create_issue`, `update_issue`, `create_ut_bug`, `resolve_bug`)
  default to `mode="preview"` — a dry run that returns the planned change without
  writing. `create_issue`, `update_issue` and `create_ut_bug` apply only after the
  user confirms the preview; `resolve_bug` applies directly when the user asks to
  resolve (the user accepts the Backlog notification to the new assignee).
- Project key is resolved from workspace context only when unambiguous; the server
  returns an error instead of guessing.
- API keys and full request URLs containing query strings are never logged.

## Local State

```
hieund-backlog-mcp/
├── .env          # credentials, git-ignored
├── config/       # shared workstation config and project catalogs
└── logs/
    ├── calls.jsonl       # one line per tool call (index)
    ├── errors.jsonl      # one line per error
    ├── sessions.jsonl    # one line per process (MCP server or CLI command)
    └── details/          # full per-call detail, one file per day
```

See `docs/telemetry.md` for the field reference and reading recipes.

### Telemetry

Telemetry schema, reading guide and recipes: `docs/telemetry.md`. Set
`BACKLOG_MCP_LOG_DIR` to write logs elsewhere.

## Running CLI from Other Directories

Use `--project` (not `--directory`) to preserve the calling directory as the
workspace path for project resolution:

```bash
# Correct — preserves CWD:
uv --project /path/to/hieund-backlog-mcp run backlog-cli bug list

# Incorrect — loses CWD context:
uv --directory /path/to/hieund-backlog-mcp run backlog-cli bug list
```

## Development

```bash
uv run --extra dev pytest
uv run backlog-cli config audit-workflows
uv run backlog-mcp-server   # speaks MCP over stdio; use an MCP client or Inspector
```
