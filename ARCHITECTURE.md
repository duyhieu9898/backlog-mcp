# Backlog MCP Architecture

This document describes the design, components, and data flow of the Workstation-local Backlog MCP server.

---

## 📋 Overview

The **Backlog MCP Server** is a workstation-local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that communicates using the `stdio` transport. It exposes the Backlog project management workflows and issue-tracking actions to MCP clients such as Claude Code, Codex, and Gemini as structured **Tools** and **Resources**.

The server acts as a wrapper around the `backlog_tool` core CLI/domain runtime, ensuring that credentials, configurations, metrics, and logs are centralized under a single repository-root project directory instead of being duplicated in client runtimes.

```
       [ AI Agent / MCP Client ]
                  │
                  │ (Stdio Transport)
                  ▼
         [ backlog_mcp.server ]  ◄─── FastMCP Router
                  │
                  ▼
         [ backlog_tool.cli ]    ◄─── CLI Execution Bridge
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
[ Domain Services ]   [ Config & State ]
  (Issue, Bug, UT)      (.env, backlog.json)
        │
        ▼
  [ Backlog API ]
```

---

## 🏗️ Components

The directory layout separates the MCP protocol interface from the core domain logic:

```plaintext
backlog-mcp/
├── backlog_mcp/             # MCP Server Interface
│   ├── __init__.py
│   └── server.py            # FastMCP router defining tools and resources
├── backlog_tool/            # Core Domain Runtime
│   ├── client.py            # Backlog REST API HTTP client
│   ├── settings.py          # Centralized configuration, local paths, and metrics
│   ├── cli.py               # Main CLI command dispatcher
│   └── *_service.py         # Business logic for issue & bug workflows
├── workflows/               # Pre-defined Workflow Audits & Transition Policies
│   ├── audit.py             # Config validation against project schemas
│   └── *.py                 # Templates for bug resolution and field rules
├── config/                  # Workstation configuration & project catalogs
│   └── backlog.json         # Space URL, project listings, and defaults
├── logs/                    # Local session logs and metrics (Git-ignored)
└── tests/                   # Offline unit test suite with mock fixtures
```

### 1. MCP Server Interface (`backlog_mcp`)
Defined in [server.py](file:///home/hieund/Documents/MY_PROJECT/DEVELOP_MAINTAIN/hieund-ai-kit-cli/backlog-mcp/backlog_mcp/server.py), this module uses the FastMCP SDK to bind Python functions to MCP tools. It handles:
* Translating structured arguments from JSON payloads into CLI command arguments.
* Routing tool execution back to the `backlog_tool.cli.execute` runner.
* Serving resources like `backlog://config` and `backlog://metrics`.

### 2. Core Domain Runtime (`backlog_tool`)
The underlying engine that executes command actions:
* [client.py](file:///home/hieund/Documents/MY_PROJECT/DEVELOP_MAINTAIN/hieund-ai-kit-cli/backlog-mcp/backlog_tool/client.py): Sends HTTP requests to the Backlog API. It reads the `BACKLOG_API_KEY` from the local `.env` and intercepts requests to logs so that credentials and raw URLs are never leaked.
* [settings.py](file:///home/hieund/Documents/MY_PROJECT/DEVELOP_MAINTAIN/hieund-ai-kit-cli/backlog-mcp/backlog_tool/settings.py): Resolves path configs (e.g., locating `.env`, `config/backlog.json`, and `logs/` relative to the MCP project root) and writes local execution metrics.
* [cli.py](file:///home/hieund/Documents/MY_PROJECT/DEVELOP_MAINTAIN/hieund-ai-kit-cli/backlog-mcp/backlog_tool/cli.py): Leverages argparse to parse actions (`issue`, `bug`, `config`, `project`, `story`) and formats the outputs to JSON or Markdown tables.

### 3. Workflows
Defines the transition policies, rules, and field requirements for managing bugs and parent-child issues. It includes `config.py` and `audit.py` to check that the local project configuration catalogs remain consistent with the actual schemas configured in the Backlog space.

---

## 🔒 Safety & Heuristics

Because this server operates locally on a developer's workstation with mutation capabilities, several guardrails are built-in:

> [!IMPORTANT]
> **Dry Run Heuristic**
> All tools modifying state (`create_issue`, `update_issue`, `resolve_bug`, `create_ut_bug`) run in **preview mode by default**. They build and return the payload that would be sent. Mutations are only submitted to the Backlog API if `mode="apply"` is explicitly passed.

> [!WARNING]
> **Credential Protection**
> The Backlog API key is never written to log files. Request URLs containing query parameters are automatically stripped before being output to standard logs.

* **Targeted Operations**: An explicit project key wins. Otherwise the runtime uses `.backlog-project.json` or a recognized workspace path segment. Claude Code supplies that workspace through `CLAUDE_PROJECT_DIR`; `BACKLOG_WORKSPACE_PATH` remains the explicit client override. Resolution fails instead of querying every configured project.

---

## 🔄 Local State & Storage

All local workstation state lives under the `backlog-mcp/` root:
* **Credentials**: Store in `.env` (ignored by Git).
* **Configuration**: Backlog space, configured projects, and user mapping reside in `config/backlog.json`.
* **Catalogs**: Cached project configuration maps reside under `config/projects/`.
* **Logs & Metrics**: Detailed session files, log history, and aggregated statistics reside under `logs/`.

---

## 🧪 Testing

The logic is validated by a pytest-based offline suite under `tests/`:
* Runs regression checks on CLI arg parsing, presenter table formatting, and settings loading.
* Employs mock fixtures located under `tests/fixtures/` to test client behaviors without making actual HTTP requests to the Backlog endpoints.
