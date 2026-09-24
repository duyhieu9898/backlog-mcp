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
         [ backlog_mcp.server ]  ◄─── FastMCP Server
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
hieund-backlog-mcp/
├── backlog_mcp/                  # MCP Server Interface
│   ├── __init__.py
│   └── server.py                 # FastMCP router — tools, instructions, issue resource
├── backlog_tool/                 # Core Domain Runtime
│   ├── client.py                 # Backlog REST API HTTP client
│   ├── settings.py               # Config, local paths, project resolution, metrics
│   ├── cli.py                    # Standalone CLI dispatcher (backlog-cli)
│   ├── issue_service.py          # Issue CRUD business logic (typed service)
│   ├── resolver.py               # Option/ID resolution (status, type, custom fields)
│   ├── presenter.py              # Output formatting (compact, table, markdown)
│   ├── journal.py                # Durable CLI output log for cross-session memory
│   └── inspect.py                # Project metadata inspect logic
├── workflows/                    # Workflow policies & transition rules
│   ├── config.py                 # Workflow config loader
│   ├── audit.py                  # Config validation against project schemas
│   ├── resolve_bug.py            # Bug resolution workflow & context builder
│   ├── resolve_policy.py         # Bug resolution field policies
│   ├── guidance.py               # Field guidance & allowed-value lookup
│   ├── ut_bug.py                 # Unit Test sub-task bug creation
│   ├── bug_template.py           # Bug field templates
│   └── story_task_overview.py    # Story/task deadline overview
├── config/                       # Workstation configuration & project catalogs
│   ├── backlog.json              # Space URL, project list, user mapping, defaults
│   └── projects/                 # Per-project cached catalogs (KEY.json)
├── logs/                         # Local session logs and metrics (Git-ignored)
└── tests/                        # Offline unit test suite with mock fixtures
    └── fixtures/                 # Mock data for HTTP-free testing
```

### 1. MCP Server Interface (`backlog_mcp`)
Defined in `backlog_mcp/server.py`, this module uses the FastMCP SDK to expose three kinds of MCP primitives:
* **Tools** — 12 callable actions (issue CRUD, bug workflow, personal status). Invokes domain service functions directly with typed arguments and returns structured MCP responses whose text content is the same result as compact JSON. Project/config administration is CLI-only.
* **Resources** — `backlog://issue/{issue_key}` (one issue as JSON).

### 2. Core Domain Runtime (`backlog_tool`)
The underlying engine that executes command actions:
* `client.py`: Sends HTTP requests to the Backlog API. Reads `BACKLOG_API_KEY` from `.env`; credentials and raw query-string URLs are never written to logs.
* `settings.py`: Resolves all local paths (`.env`, `config/backlog.json`, `logs/`), implements the project-key resolution chain (explicit arg → `.backlog-project.json` walk-up → directory-name match → error), and writes per-invocation metrics.
* `cli.py`: argparse dispatcher for subcommand groups `issue`, `bug`, `config`, `project`, `story`, `metrics`. Formats output as compact JSON or Markdown tables. Accepts `workspace_path` to pass workspace context from the MCP server.
* `issue_service.py`: CRUD logic for Backlog issues (create, get, list, update).
* `resolver.py`: Resolves human-readable names (status, issue type, category, custom fields) to Backlog API IDs using project catalog data.
* `presenter.py`: Converts raw API responses to compact dicts and Markdown table strings.
* `journal.py`: Appends structured CLI output to a local journal for durable cross-session memory.
* `inspect.py`: Fetches and serializes project metadata from the Backlog API.

### 3. Workflows
Defines transition policies, field rules, and guided sequences for managing bugs and issues:
* `config.py`: Loads workflow configuration from local JSON files.
* `audit.py`: Validates local project catalogs and workflow configs against expected schemas; detects drift.
* `resolve_bug.py`: Core bug resolution workflow — builds the resolution payload, applies field defaults, and enriches bug context for the agent.
* `resolve_policy.py`: Encodes the field policies (required fields, allowed values) that govern bug resolution.
* `guidance.py`: Returns allowed values and guidance text for individual bug workflow fields (`qc_activity`, `cause_category`, `bug_origin`, etc.).
* `ut_bug.py`: Creates Unit Test sub-task bugs with opinionated field defaults.
* `bug_template.py`: Shared field templates reused across bug creation and resolution.
* `story_task_overview.py`: Queries and formats assigned Story/Task items with deadline context.

---

## 🔒 Safety & Heuristics

Because this server operates locally on a developer's workstation with mutation capabilities, several guardrails are built-in:

> [!IMPORTANT]
> **Dry Run Heuristic**
> All tools modifying state (`create_issue`, `update_issue`, `resolve_bug`, `create_ut_bug`) run in **preview mode by default**. They build and return the payload that would be sent. Mutations are only submitted to the Backlog API if `mode="apply"` is explicitly passed. `resolve_bug` is the one tool the instructions tell the model to call with `mode="apply"` directly, once, when the user asks to resolve.

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
