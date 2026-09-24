# Backlog MCP telemetry

Đọc file này trước khi phân tích log. Log nằm trong `logs/` (hoặc `$BACKLOG_MCP_LOG_DIR`).

## File

| File | Một dòng là | Dùng để |
|---|---|---|
| `calls.jsonl` | một tool call (MCP hoặc CLI) | quét nhanh: tool nào, bao lâu, bao nhiêu token, lỗi gì |
| `errors.jsonl` | một lỗi (`tool_error`, `arg_error`, `api_error`, `partial_write`, `unknown_tool` — gọi tool không tồn tại, ứng với call `status: rejected`) | tìm lỗi lặp lại |
| `sessions.jsonl` | một process (MCP server hoặc lệnh CLI) | phiên bản code (`version`, `gitSha`, `dirty`), client, backend real/fake |
| `details/YYYY-MM-DD.jsonl` | chi tiết một tool call | xem `arguments`, `result`, `text`, API call, `mutation` |

Lưu ý: dòng `sessions.jsonl` của MCP server luôn có `client.name == "unknown"` vì được ghi lúc khởi động, trước khi client gửi `clientInfo` trong `initialize`. Muốn chia theo client/model thì dùng `client` trên dòng `calls.jsonl`.

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

## Eval
- Kịch bản: `evals/scenarios.json`. Backlog giả: `uv run python -m evals.fake_backlog [--state no_open_bugs]`.
- Chạy: `uv run python -m evals.run --agent claude|agy --model <m> --scenario <id|all> --runs N --label <nhãn>`.
- Server bật chế độ giả khi workspace có `.backlog-eval.json` (`baseUrl` phải là localhost); log run ghi vào `logDir` của file đó, gắn `runId`/`scenario`.
- `claude` chạy với `--strict-mcp-config --mcp-config <tmp>/mcp.json` (file tạo cho từng run trong thư mục tạm, không ghi vào workspace; chỉ có server `backlog` = `uv --project <repo> run backlog-mcp-server`) và `--disallowedTools Bash Edit Write NotebookEdit WebFetch WebSearch Task Agent`. Ở permission mode `auto` `--allowedTools` không chặn tool nên phải cô lập bằng MCP config; hook/skill global vẫn giữ (D9). `agy` chạy với `--sandbox`. Tool bị từ chối nằm ở `deniedTools`.
- Env của agent bỏ mọi biến `BACKLOG_*` (API key thật do bootstrap nạp từ `.env`), chỉ đặt `BACKLOG_WORKSPACE_PATH=<workspace>`.
- Cô lập fail-closed: sau mỗi run phải có dòng `sessions.jsonl` với `backend == "fake"` và đúng `runId`; nếu không, run bị đánh `isolationFailed: true`, `pass: false` và cả batch dừng (exit 2).
- `--workspace <dir>`: marker `.backlog-project.json`/`.backlog-eval.json` có sẵn được lưu lại và khôi phục nguyên byte sau run (kể cả khi lỗi).
- agy gọi MCP qua `call_mcp_tool` và đọc schema bằng `view_file` trong `~/.gemini/antigravity-cli/mcp/backlog/` → đếm ở `schemaReads`.
- Kết quả: `evals/results/<ngày>-<nhãn>/<agent>-<model>.jsonl` (một dòng/run, chỉ trên máy vì chứa câu trả lời có nội dung bug) và `SUMMARY.md` (được commit).
- Cassette dữ liệu thật: `uv run python -m evals.cassettes extract --from logs/legacy/telemetry.jsonl` → `evals/cassettes/oop.json` (gitignore). Eval mặc định bắt buộc cassette; `--allow-synthetic` để chạy bằng dữ liệu tổng hợp. Làm mới cassette: chạy một phiên với `BACKLOG_MCP_LOG_BODIES=full`, sau đó trích lại (bộ trích hiện đọc định dạng log cũ — khi cần, thêm đọc `details/`).
- Replay không dùng model: `uv run --extra dev pytest tests/test_replay.py`.
- Smoke 2026-09-24: `claude opus` và `agy gemini-3.8-flash-medium` cả hai khởi động MCP server thật (không cần bỏ `--sandbox`, agy chạy bình thường với nó) và thấy marker `.backlog-eval.json` (`backendSource: "cassette"`, `unhandledEndpoints: []`, `agentOk: true`). `claude` PASS kịch bản `open_bugs`; `agy` FAIL vì gọi thêm `list_configured_projects`/`get_my_open_bugs` (lặp)/`get_bug_context` ngoài kỳ vọng — không chặn đóng P3 (pass/fail chưa quan trọng ở bước này).
