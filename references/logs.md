# Log Reference for AI Agents

This document guides AI Agents on how to read, locate, and analyze the internal logs of the `backlog` skill for troubleshooting, context recall, and performance/token optimization.

Since CLI command wrappers for logs have been deprecated, you must read the log files directly from the filesystem under the `.agents/skills/backlog/logs/` directory.

---

## 1. Log Layout & Location

All logs are written inside the local workspace under:
`.agents/skills/backlog/logs/`

| Log Category | File Pattern | Format | Purpose |
| :--- | :--- | :--- | :--- |
| **Operational Log** | `backlog.log` | Spaced Text | Tracks startup, api calls, and error stack traces. |
| **Performance Metrics** | `metrics.log` | JSON Lines | Tracks command status, latency, and estimated token consumption. |
| **Session Traces** | `sessions/<PROJECT_KEY>/<YYYY-MM-DD>_<command>.jsonl` | JSON Lines | Partitioned record of raw CLI inputs and outputs per project. |

---

## 2. Reading Operational Logs (`backlog.log`)

This file records general operations and error events.
*   **Format**: `[Timestamp] [LEVEL] event=[event_name] [key]=[value] ...`
*   **Char Truncation**: High-volume outputs are automatically truncated to 500 characters to keep file sizes and reading costs minimal.

### How to use:
- When a command fails, use the `grep_search` or `view_file` tools to read the tail of `backlog.log`.
- Search for `LEVEL=ERROR` or `event=command_error` to identify exact HTTP response codes and stack traces.

---

## 3. Reading Metrics and Token Usage (`metrics.log`)

Each backlog CLI run appends a JSON record to `metrics.log`.

### Record Fields:
```json
{
  "ts": "2026-06-22T09:30:15+07:00",
  "command": "issue:list",
  "status": "ok",
  "outputBytes": 5420,
  "estimatedTokens": 1355,
  "durationMs": 750,
  "dryRun": null,
  "project": "AQM"
}
```

### How to use:
- **Token Optimization**: Inspect the `estimatedTokens` (based on `outputBytes / 4`) to see if a command is consuming too much of your prompt context. If yes, prefer compact views or narrower queries in subsequent calls.
- **Latency Check**: Track `durationMs` to diagnose network latency or API timeouts.

---

## 4. Reading Session Traces (`sessions/`)

Session traces provide a historical timeline of inputs, outputs, and status changes partitioned by **Project Key** (e.g. `AQM`, `OOP`) and date.

### Path structure:
`sessions/<PROJECT_KEY>/<YYYY-MM-DD>_<command>.jsonl`

### Record Fields:
```json
{
  "ts": "2026-06-22T09:30:15+07:00",
  "step": "cli",
  "command": "bug:resolve",
  "project": "AQM",
  "issueKey": "AQM-102",
  "cliOutput": "{...}"
}
```

### How to use:
- **Recall Context**: If you need to recall what issues you mutated or queried earlier in the session, search the sub-directory `sessions/<PROJECT_KEY>/` for today's date.
- **Audit Dry-Runs**: Compare changes before/after applying a mutation by inspecting the output of the dry-run steps recorded in these files.

---

## 5. Log Rotation and Backups

To keep the workspace lightweight, the logging engine rotates files when they reach **5MB**.
- Active files: `backlog.log` and `metrics.log`
- Rolled backups: `.log.1`, `.log.2`, `.log.3` (up to 3 rotation files).
- **Important**: If you are looking for an event that happened slightly earlier and cannot find it in `backlog.log` or `metrics.log`, check the `.1` backup files (e.g., `backlog.log.1`).
