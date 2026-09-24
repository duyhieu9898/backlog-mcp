# Backlog MCP telemetry

Đọc file này trước khi phân tích log. Log nằm trong `logs/` (hoặc `$BACKLOG_MCP_LOG_DIR`).

## File

| File | Một dòng là | Dùng để |
|---|---|---|
| `calls.jsonl` | một tool call (MCP hoặc CLI) | quét nhanh: tool nào, bao lâu, bao nhiêu token, lỗi gì |
| `errors.jsonl` | một lỗi (`tool_error`, `arg_error`, `api_error`, `partial_write`) | tìm lỗi lặp lại |
| `sessions.jsonl` | một process (MCP server hoặc lệnh CLI) | phiên bản code (`version`, `gitSha`, `dirty`), client, backend real/fake |
| `details/YYYY-MM-DD.jsonl` | chi tiết một tool call | xem `arguments`, `result`, `text`, API call, `mutation` |

Mọi dòng nối với nhau bằng `traceId` (call) và `sessionId` (process). Quy trình đọc chuẩn: quét `calls.jsonl` và `errors.jsonl` trước; chỉ mở `details/` bằng `traceId` khi cần nội dung đầy đủ.

## Field chung
`v` (3), `ts`, `sessionId`, `surface` (`mcp`|`cli`), `client {name, version}`, `runId`/`scenario` (chỉ khi eval).

## calls.jsonl
`traceId, tool, argKeys, issueKey, projectKey, mode, status (ok|error|invalid_arguments|rejected|partial_write), durationMs, apiCalls, apiMs, responseBytes, estTokens (= responseBytes/4, ước lượng), flags`.

## errors.jsonl
`traceId, kind, tool, message` và theo `kind`:
- `arg_error`: `sent`, `unknown`, `missingRequired`, `invalid [{name, reason}]`, `suggested {sai: đúng}`.
- `api_error`: `method, path, status, body` (≤ 2 KB).

## sessions.jsonl
`event (session_start), pid, version` (package version), `gitSha`, `dirty`, `toolCount`, `backend` (real/fake), `workspace`.

## details/
`traceId, tool, arguments (đúng như client gửi), result (structuredContent), text (text content), api [{method, path, status, durationMs, requestBytes, responseBytes, body?}], mutation {mode, planHash, statusBefore, statusAfter, changedFields, warnings}`.
`api[].body` chỉ có khi lỗi hoặc method ≠ GET; `BACKLOG_MCP_LOG_BODIES=full` để giữ mọi body. File `details/` giữ 30 ngày.

## Công thức mẫu
```bash
# Top tool theo token trong ngày
jq -s 'map(select(.ts >= "2026-09-24")) | group_by(.tool) | map({tool: .[0].tool, calls: length, tokens: (map(.estTokens) | add)}) | sort_by(-.tokens)' logs/calls.jsonl
# Lỗi tham số lặp lại
jq -s 'map(select(.kind == "arg_error")) | group_by([.tool, (.unknown | join(","))]) | map({tool: .[0].tool, unknown: .[0].unknown, suggested: .[0].suggested, count: length}) | sort_by(-.count)' logs/errors.jsonl
# Xem đầy đủ một call
grep -h '"traceId": "<id>"' logs/details/*.jsonl | jq .
# Chuỗi tool của một session
jq -c 'select(.sessionId == "<id>") | [.ts, .tool, .status, .estTokens]' logs/calls.jsonl
# Call chậm nhất
jq -s 'sort_by(-.durationMs) | .[:10] | map({ts, tool, durationMs, apiMs})' logs/calls.jsonl
```

## Báo cáo có sẵn
`uv run backlog-cli telemetry report --since 1d [--run <runId>] [--json]` — flow, rule, chấm kịch bản, field thiếu (xem Plan A Task 12).
`uv run backlog-cli telemetry import-claude --since 1d` — ghép transcript Claude Code.

## Log cũ
Log trước 2026-09-24 (`backlog.log`, `metrics.log`, `telemetry.jsonl*`, `sessions/`) không được công cụ mới đọc. Chuyển một lần:
```bash
mkdir -p logs/legacy && mv logs/backlog.log* logs/metrics.log* logs/telemetry.jsonl* logs/sessions logs/legacy/ 2>/dev/null
```
