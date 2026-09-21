# Backlog Local MCP

One local stdio MCP server serves every project on this workstation. Source,
configuration, credentials, project catalogs, logs, metrics, and session traces
all live under this directory; the AI kit templates do not contain a Backlog
skill.

## Setup

Prerequisites: Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
cd backlog-mcp
cp .env.example .env
# Set BACKLOG_API_KEY in .env, then install the locked project environment.
uv sync --extra dev
```

This checkout already preserves the local `.env` migrated from the former
skill. Never commit it.

## Register Once

Capture the absolute path once from this directory:

```bash
BACKLOG_MCP_DIR="$(pwd)"
```

### Claude Code

Register the server at user scope so it is available in every Claude Code
project on this workstation:

```bash
claude mcp add --transport stdio --scope user backlog -- \
  uv --project "$BACKLOG_MCP_DIR" run backlog-mcp-server
```

Verify it from the shell with `claude mcp get backlog` and `claude mcp list`.
Inside Claude Code, run `/mcp` and confirm that `backlog` is connected. Claude
Code passes the active project through `CLAUDE_PROJECT_DIR`; the server uses it
to resolve `.backlog-project.json` and workspace path conventions. An explicit
`project_key` tool argument still takes precedence.

To replace a stale path, remove and add the entry again:

```bash
claude mcp remove --scope user backlog
```

See the [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
for scope and troubleshooting details.

### Codex

Codex stores user-scoped MCP servers in `~/.codex/config.toml`, shared by its
CLI and IDE extension:

```bash
codex mcp add backlog -- uv --project "$BACKLOG_MCP_DIR" run backlog-mcp-server
```

Equivalent `config.toml`:

```toml
[mcp_servers.backlog]
command = "uv"
args = [
  "--project",
  "/absolute/path/to/hieund-ai-kit-cli/backlog-mcp",
  "run",
  "backlog-mcp-server",
]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

### Claude Desktop, Gemini, or Another MCP Client

Register the same stdio command in the client's user-level MCP configuration,
replacing the path with the value printed by `pwd`:

```json
{
  "command": "uv",
  "args": [
    "--project",
    "/absolute/path/to/hieund-ai-kit-cli/backlog-mcp",
    "run",
    "backlog-mcp-server"
  ]
}
```

Restart desktop clients after editing their configuration. The process is
started on demand; no daemon or remote server is required.

## Safety

- `create_issue`, `update_issue`, `create_ut_bug`, and `resolve_bug` are dry
  runs unless `mode="apply"`. Ask Claude to preview first and apply only after
  reviewing the returned change.
- `inspect_project` only prints fetched metadata unless `mode="refresh_catalog"`.
- Generic queries resolve the project key from the active workspace path or configuration; tools never loop over
  all projects implicitly.
- API keys and full request URLs containing query strings are never logged.

## Local State

```text
backlog-mcp/
├── .env                 # credential, ignored
├── config/              # shared workstation config and catalogs
└── logs/                # operational logs, metrics, sessions, ignored
```

Historical logs from removed skill copies are retained under `logs/legacy/`.

## Running from Other Directories

To run the CLI when standing in another workspace directory (to keep the path context for project resolution):
```bash
# Correct (preserves CWD):
uv --project /path/to/backlog-mcp run backlog-cli bug list

# Incorrect (loses CWD context):
uv --directory /path/to/backlog-mcp run backlog-cli bug list
```

## Development

```bash
uv run --extra dev pytest
uv run backlog-cli config audit-workflows
uv run backlog-mcp-server
```

The last command speaks MCP over stdio; use an MCP client or Inspector rather
than typing into it manually.
