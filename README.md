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
hatches for generic/custom operations. Diagnostic/config tools such as
`get_bug_rules`, `get_bug_fields`, `inspect_project`, and
`audit_config_workflows` are not normal pre-steps for the personal workflows.

For read intents, the design target is usually one MCP call. Mutations normally
use two calls because preview then apply is intentional.

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
- The catalog can become stale; re-run `inspect_project` with
  `mode="refresh_catalog"` to sync it.

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

Generic issue tools use `issue_ref` for a key or numeric ID. Bug-domain tools use `issue_key` for Backlog keys such as `OOP-12748`; MCP tool arguments use snake_case rather than Backlog API camelCase names.

### Bugs

| Tool | Description |
|---|---|
| `get_my_open_bugs` | List open bugs assigned to the configured user. |
| `get_bug_context` | Get AI-ready context for a specific bug (fields needed to understand or resolve it). |
| `resolve_bug` | Resolve a bug with workflow defaults (`mode="preview"` / `"apply"`). Apply requires `fix_description`; guided fields and hours only fill empty values and warn when a passed value is not applied. |
| `create_ut_bug` | Create a Unit Test sub-task bug under a parent issue (`mode="preview"` / `"apply"`). |
| `get_bug_rules` | Get the resolve-bug workflow rules for a project (or the project of `issue_key`). |
| `get_bug_fields` | Get allowed values and guidance for bug workflow fields (e.g. `qc_activity`, `cause_category`). |

### Personal Work

| Tool | Description |
|---|---|
| `get_my_project_status` | One-call personal Backlog status: assigned Stories/Tasks, deadlines, and open Bugs. |
| `get_my_work_overview` | List assigned Stories and Tasks with deadline and status context when that narrower view is explicitly needed. |

### Project & Config

| Tool | Description |
|---|---|
| `list_configured_projects` | List all locally configured Backlog projects. |
| `inspect_project` | Fetch metadata for one project (`mode="read"`) or refresh its local catalog (`mode="refresh_catalog"`). |
| `get_config` | Show local configuration with credentials excluded. |
| `audit_config_workflows` | Validate workflow config and project catalogs for drift. |

## Prompts

| Prompt | Description |
|---|---|
| `resolve_bug_prompt` | Guided step-by-step workflow to resolve a bug following project policies. |
| `create_ut_bug_prompt` | Guided workflow to create a Unit Test sub-task bug under a parent issue. |
| `project_status_prompt` | One-call personal Backlog status workflow using `get_my_project_status`. |

## Resources

| URI | Description |
|---|---|
| `backlog://config` | Workstation-wide Backlog configuration as JSON (credentials excluded). |
| `backlog://metrics` | Aggregated local MCP usage metrics as JSON. |
| `backlog://workflow-efficiency` | Rule-based analysis of candidate task sequences, redundant calls, and workflow-path deviations. |
| `backlog://issue/{issue_key}` | One Backlog issue as full JSON by issue key. |

## Safety

- Mutation tools (`create_issue`, `update_issue`, `create_ut_bug`, `resolve_bug`)
  default to `mode="preview"` — a dry run that returns the planned change without
  writing. Pass `mode="apply"` only after reviewing the preview.
- `inspect_project` defaults to `mode="read"` (no writes). Use
  `mode="refresh_catalog"` to update the local catalog.
- Project key is resolved from workspace context only when unambiguous; the server
  returns an error instead of guessing.
- API keys and full request URLs containing query strings are never logged.

## Local State

```
hieund-backlog-mcp/
├── .env          # credentials, git-ignored
├── config/       # shared workstation config and project catalogs
└── logs/
    ├── backlog.log       # human-oriented operational events
    ├── metrics.log       # compact per-tool metrics / token-cost proxy
    ├── telemetry.jsonl   # canonical vendor-neutral trace events
    └── sessions/         # CLI session journal
```

### Workflow Efficiency Analysis

`backlog://workflow-efficiency` analyzes the local telemetry with conservative,
rule-based heuristics. Candidate tasks are grouped by observable client,
issue/project, and time proximity; this is not a claim about the model's hidden
reasoning or the exact user intent.

Current findings include:

- repeated same tool + same arguments
- generic `get_issue` before `get_bug_context`
- `get_bug_rules` / `get_bug_fields` before `resolve_bug`
- generic issue search before the personal bug queue
- mutation apply without a matching preview
- separate Story/Task + Bug status calls where the one-call personal status tool
  may have been sufficient

Findings that depend on the unknown user intent are marked `candidate`; stronger
observable violations are marked `warning`. The analyzer also summarizes MCP
calls, Backlog API calls, response bytes, estimated token proxy, and per-client
behavior.

### Telemetry

`telemetry.jsonl` is the source of truth for MCP observability. Each MCP tool
invocation receives a `traceId` that correlates tool arguments, Backlog API
calls, latency, response sizes, errors, and the final MCP result.

Token counts are intentionally estimates. The server records text,
`structuredContent`, and total serialized response bytes so the same metric is
comparable across Claude, Codex, Gemini/Antigravity, and other MCP clients even
though their actual tokenizers and caching differ.

Client name/version default to the `clientInfo` the MCP client sends during
`initialize`. Set these per client process to override it:

```bash
BACKLOG_MCP_CLIENT=codex
BACKLOG_MCP_CLIENT_VERSION=<optional>
BACKLOG_MCP_TRANSPORT=stdio
```

Calls that FastMCP rejects before the tool body runs (unknown or invalid
arguments) are still recorded, with status `invalid_arguments` or `rejected`.
For MCP calls, `tool_start.arguments` holds the arguments exactly as the client
sent them; parameters the client omitted (and that took their defaults) are not
listed. If a log file cannot be written, the server warns once per file on
stderr instead of failing the tool call.
The test suite redirects all log paths to a temporary directory, so running
`pytest` never adds records to the workstation `logs/`.

The API key itself is never written to telemetry. Request parameters/payloads
and Backlog response bodies are retained locally for debugging.

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
