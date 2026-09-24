# Backlog MCP: Telemetry nền tảng + Eval đa model — Design Spec

- Ngày: 2026-09-24
- Trạng thái: Đã duyệt; P0–P6 xong (2026-09-24) — P6 Claude opus 70/70, 0 `arg_error`. P6 chỉ eval Claude opus — Gemini bị loại theo quyết định người dùng ngày 2026-09-24 (API Gemini không ổn định).
- Thay thế: `docs/superpowers/plans/2026-09-23-telemetry-and-payload.md` (xem §11)

## 1. Bối cảnh

Backlog MCP được dùng hằng ngày qua Claude Code và Antigravity (Gemini). Log ngày 2026-09-23 cho thấy:

- Model gọi thừa tool: Gemini luôn `get_bug_context → get_issue` trước khi resolve, có lúc gọi `get_config` giữa preview và apply; 4/10 lần `get_issue` ngay sau `get_bug_context` cùng issue.
- Model đoán schema và truyền sai tham số; tên tham số chưa đồng bộ (`issue_ref` ở `get_issue`/`update_issue`, `issue_key` ở tool bug).
- Text content của `resolve_bug` preview chỉ có `(structured data)` cho `changes`/`warnings`/`assignment`.
- Cơ chế log hiện tại có 3 sink chồng lấn (`backlog.log`, `metrics.log`, `telemetry.jsonl`) + journal `logs/sessions/`, tên field lệch nhau (`command` vs `tool`), log thật từng bị lẫn record pytest, không có session/phiên bản server, CLI không được trace.
- Probe `agy -p "backlog kiểm tra bugs open của project OOP"` (2026-09-24, backend thật, chỉ đọc): agy không đưa tool MCP thành tool riêng mà qua meta-tool `call_mcp_tool {ServerName, ToolName, Arguments}`; model phải `view_file` từng schema trong `~/.gemini/antigravity-cli/mcp/backlog/<tool>.json` trước khi gọi (4 lần đọc schema trước call đầu tiên); model chỉ nhận **text content**. `get_my_open_bugs` trả text `No data.` (người dùng thật sự có 0 bug open) → model không tin, gọi thêm `inspect_project`, `get_issues` ×3, `get_my_project_status`, rồi đọc transcript, source code và chạy Python gọi thẳng Backlog API; timeout sau 240 s.
- Không có cách lặp lại để kiểm chứng một thay đổi mô tả tool/response có giúp model đi đúng workflow hay không.

## 2. Mục tiêu

1. Kiểm thử Backlog MCP với nhiều model một cách **tự động và lặp lại được**: Claude Code (`claude -p`) và Antigravity CLI (`agy -p`), trên Backlog giả.
2. Ba loại prompt quen thuộc phải đi **đúng workflow, không call thừa, không lỗi tham số** (§6).
3. Giảm đoán sai schema: tên tham số chuẩn hoá, lỗi tham số có gợi ý tên đúng, lỗi tham số được ghi log.
4. Refactor mạnh tay log/metric thành **một bộ log chuẩn**, dễ đọc cho agent, chia file theo mức chi tiết, kế thừa phần tốt của cơ chế cũ.
5. Dùng log (thật và eval) để: tìm lỗi lặp lại, call tốn token/chậm, lý do gọi thêm tool, **field thiếu** khiến phải gọi thêm.

## 3. Phạm vi

**Trong phạm vi**
- Telemetry mới (ghi), tài liệu schema, phân tích (flow, rule chung, chấm theo kịch bản, field thiếu), CLI `telemetry report` và `telemetry import-claude`.
- Harness eval: Backlog giả, adapter `claude` và `agy`, bộ kịch bản, kết quả lưu trong repo.
- Thay đổi MCP: 4 tool quản trị sang CLI; chuẩn hoá tên tham số; gợi ý khi sai tham số; text content đủ nội dung; `resolve_bug` fast path; `get_bug_context` liệt kê ảnh/tệp đính kèm; bỏ MCP prompts và 2 resource phân tích cũ.
- Baseline trước khi sửa MCP, eval lại sau khi sửa, báo cáo so sánh.

**Ngoài phạm vi**
- Skill/workflow sửa bug đầy đủ (context → sửa code → commit → push → resolve): dự án tiếp theo trong `hieund-ai-kit-cli` (§12).
- Phân tích field thừa: người dùng tự review response.
- Ngưỡng thời gian/token cứng: thời gian và token chỉ được báo cáo để review.
- Codex CLI; Gemini CLI (legacy).
- Import transcript agy (`~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl`) cho dùng thật: để sau; eval agy lấy dữ liệu từ stream-json.
- Tải/gửi nội dung ảnh đính kèm cho model: người dùng tự xem ảnh và nhắc trong prompt khi cần; model chỉ cần biết tệp tồn tại.
- Làm gọn `get_bug_context` / `get_my_open_bugs` (bỏ `rawDescription`, bỏ description trong list): để người dùng tự review sau khi có log field.

## 4. Quyết định đã chốt

| # | Quyết định |
|---|---|
| D1 | Kiến trúc 3 tầng: log chuẩn (nền tảng) → rule chung (mọi flow) → chấm theo kịch bản (flow khớp kịch bản). Tầng dưới không phụ thuộc tầng trên. |
| D2 | Log chia file theo mức chi tiết: `calls.jsonl` (chỉ mục), `errors.jsonl`, `sessions.jsonl`, `details/<ngày>.jsonl`. |
| D3 | Agent tự đọc log theo `docs/telemetry.md`; chỉ code hoá phần tính toán khó: nhóm flow, rule, chấm, field thiếu, ghép transcript. CLI chỉ có `telemetry report` và `telemetry import-claude`. |
| D4 | Eval chạy trên Backlog giả local; chế độ giả bật bằng file đánh dấu `.backlog-eval.json` trong workspace eval, không sửa cấu hình MCP global của client. |
| D5 | `resolve_bug`: khi người dùng yêu cầu resolve, gọi **một lần** `mode="apply"`; không preview; không chặn khi có warning; model báo warnings trong câu trả lời. Người dùng chấp nhận rủi ro thông báo Backlog gửi tới người được gán. Chỉ áp dụng cho `resolve_bug`; `create_issue`, `update_issue`, `create_ut_bug` giữ preview → hỏi → apply. |
| D6 | `fix_description` và `commit` không bắt buộc ở mọi mode; thiếu `fix_description` thì Corrective Action = `fixed <summary>`. Model không đọc git/source để tìm nội dung fix. |
| D7 | `get_config`, `audit_config_workflows`, `inspect_project`, `list_configured_projects` chỉ còn ở CLI. MCP còn 12 tool. |
| D8 | Prompt người dùng luôn chứa `backlog`/`backlog mcp` và mã issue đầy đủ (`OOP-12465`). |
| D9 | Hook/skill global (superpowers) được giữ nguyên khi eval — đo đúng trải nghiệm thật. |
| D10 | Điều kiện đóng dự án là **tính đúng** (§10), không phải thời gian. |
| D11 | Commit thẳng lên `main`, push `main`; không branch/PR. |

## 5. Tầng 1 — Log chuẩn

### 5.1 Bố cục

```
<LOG_DIR>/                      # mặc định <repo>/logs, override bằng BACKLOG_MCP_LOG_DIR
├── calls.jsonl                 # chỉ mục: 1 dòng / tool call
├── errors.jsonl                # 1 dòng / lỗi
├── sessions.jsonl              # 1 dòng / process (MCP server hoặc lệnh CLI)
└── details/
    └── YYYY-MM-DD.jsonl        # chi tiết: 1 dòng / tool call, theo traceId
```

- `calls.jsonl`, `errors.jsonl`, `sessions.jsonl` rotate theo dung lượng (20 MB, giữ 5 bản).
- `details/`: giữ 30 ngày; file cũ hơn bị xoá khi server khởi động.
- Log cũ (`backlog.log`, `metrics.log`, `telemetry.jsonl*`, `sessions/`) được người dùng chuyển tay vào `logs/legacy/` (lệnh `mv` ghi trong `docs/telemetry.md`); công cụ mới không đọc thư mục này.
- Ghi log không bao giờ làm hỏng tool call; lỗi ghi → cảnh báo stderr một lần mỗi file (giữ cơ chế `report_log_failure` hiện có).
- Không bao giờ ghi API key hoặc URL có query string.

### 5.2 Field chung (mọi dòng mọi file)

| Field | Kiểu | Ghi chú |
|---|---|---|
| `v` | int | Phiên bản schema, bắt đầu `3` |
| `ts` | string | ISO-8601 có mili-giây và timezone |
| `sessionId` | string | UUID mỗi process |
| `surface` | `"mcp"` \| `"cli"` | |
| `client` | `{name, version}` | Từ MCP `clientInfo`; override bằng `BACKLOG_MCP_CLIENT` / `BACKLOG_MCP_CLIENT_VERSION` |
| `runId` | string? | Chỉ có khi chạy eval (từ `.backlog-eval.json`) |
| `scenario` | string? | Chỉ có khi chạy eval |

### 5.3 `sessions.jsonl`

`{…chung, event: "session_start", pid, gitSha, dirty, toolCount, backend: "real"|"fake", workspace}`

### 5.4 `calls.jsonl` (chỉ mục, mục tiêu ≤ ~400 byte/dòng)

`{…chung, traceId, tool, argKeys: [..], issueKey?, projectKey?, mode?, status: "ok"|"error"|"invalid_arguments"|"rejected"|"partial_write", durationMs, apiCalls, apiMs, responseBytes, estTokens, flags: [..]}`

- `argKeys`: tên tham số client thực sự gửi (không gồm tham số lấy mặc định).
- `flags`: nhãn rẻ tính ngay lúc ghi, ví dụ `"large_response"` (> 8 KB). Rule cần nhiều call được tính ở tầng 2, không ghi vào đây.

### 5.5 `errors.jsonl`

`{…chung, traceId, kind: "tool_error"|"arg_error"|"api_error"|"partial_write", tool, message, …}`

- `arg_error`: `sent` (tên tham số client gửi), `unknown` (tên không tồn tại), `missingRequired`, `suggested` (map tên sai → tên đúng gần nhất), `invalid` (tên + lý do sai kiểu/giá trị).
- `api_error`: `method`, `path` (không query), `status`, `body` (cắt 2 KB).

### 5.6 `details/YYYY-MM-DD.jsonl`

`{…chung, traceId, tool, arguments, result, text, api: [{method, path, status, durationMs, requestBytes, responseBytes, body?}], mutation?}`

- `arguments`: đúng như client gửi.
- `result`: `structuredContent` của response; `text`: text content.
- `api[].body`: chỉ khi status lỗi hoặc method ≠ GET; đặt `BACKLOG_MCP_LOG_BODIES=full` để giữ mọi body.
- `mutation` (chỉ tool ghi): `{mode, planHash, statusBefore, statusAfter?, changedFields, warnings}`. `planHash` = sha256 16 hex của `{issue, payload}` đã sort key.

### 5.7 CLI

Mọi lệnh `backlog-cli` ghi `sessions`/`calls`/`details`/`errors` như MCP với `surface: "cli"`; `tool` = tên tool MCP tương đương nếu có (`bug:resolve` → `resolve_bug`), ngược lại là tên lệnh (`config:show`).

### 5.8 Kế thừa từ cơ chế cũ

Giữ: `traceId` nối mọi event của một call; đo bytes text/structured/tổng; ghi tham số đúng như client gửi (commit `784ab21`); ghi cả call bị FastMCP từ chối; cảnh báo stderr khi ghi lỗi (commit `789bca5`); cô lập log khi chạy pytest (`tests/conftest.py`); rotate theo dung lượng.

Bỏ: `metrics.log`, `backlog.log`, `telemetry.jsonl`, journal `logs/sessions/`, `settings.log_metric`/`log_event`/`read_metrics`/`summarize_metrics`, `journal.py`, `workflow_efficiency.py` (logic nhóm flow và rule tốt được chuyển sang §7), resource `backlog://metrics` và `backlog://workflow-efficiency`.

### 5.9 `docs/telemetry.md`

Tài liệu agent đọc đầu tiên: bố cục file, từng field, quy trình đọc chuẩn (quét `calls`/`errors` → tra `details` bằng `traceId`), 6–8 công thức `jq`/Python mẫu (top tool theo `estTokens`, lỗi `arg_error` lặp lại theo tool+tham số, xem một call đầy đủ, lọc theo `runId`), và lệnh chuyển log cũ vào `logs/legacy/`.

## 6. Kịch bản (`evals/scenarios.json`)

### 6.1 Định dạng

```json
{
  "id": "resolve_fixed",
  "prompt": "backlog resolve {issue}, bug này tôi fix rồi",
  "fixtures": {"issue": "OOP-912762"},
  "match": {"keywords": ["resolve"], "issueKeys": "one"},
  "expect": {
    "calls": [{"tool": "resolve_bug", "args": {"issue_key": "{issue}", "mode": "apply"}}],
    "order": "exact",
    "forbidden": ["get_bug_context", "get_issue", "get_bug_rules", "get_bug_fields"],
    "finalAnswer": null
  },
  "nonMcp": null
}
```

- `calls`: danh sách call MCP mong đợi; `args` so khớp tập con (field có trong kỳ vọng phải bằng, field khác không xét). `{issue}` được thay bằng fixture.
- `order`: `"exact"` (đúng thứ tự, đúng số lượng) hoặc `"any"` (đúng tập, số lượng bằng nhau).
- `forbidden`: gọi tool trong danh sách là fail.
- `finalAnswer`: `null` hoặc `{"mustMention": [..]}` — chuỗi phải xuất hiện (không phân biệt hoa thường) trong câu trả lời cuối.
- `match`: quy tắc nhận diện prompt thật (§6.3).
- `nonMcp`: chỗ mở rộng cho dự án skill (§12); bộ chấm hiện tại bỏ qua.

### 6.2 Bộ kịch bản

| id | Prompt | Fixture | Kỳ vọng MCP | Ghi chú |
|---|---|---|---|---|
| `open_bugs` | `backlog kiểm tra bugs open` | danh sách 3 bug open của OOP | `[get_my_open_bugs]` | forbidden: `get_issues`, `get_issue`, `get_bug_context`, `get_my_project_status` |
| `open_bugs_empty` | `backlog kiểm tra bugs open` | không có bug open | `[get_my_open_bugs]` | forbidden như `open_bugs`; `finalAnswer.mustMention: ["0"]` |
| `resolve_fixed` | `backlog resolve {issue}, bug này tôi fix rồi` | `OOP-912762` | `[resolve_bug{mode:apply}]` | forbidden như §6.1 |
| `resolve_multi` | `backlog resolve {a}, {b}, các bug này tôi fix rồi` | `OOP-912774`, `OOP-912773` | 2 × `resolve_bug{mode:apply}`, `order: any` | |
| `resolve_warning` | `backlog resolve {issue}, bug này tôi fix rồi` | `OOP-912749` (Detected Role đổi thành Developer) | `[resolve_bug{mode:apply}]` | `finalAnswer.mustMention: ["Tester"]` |
| `fix_context` | `backlog fix {issue}` | `OOP-912779` | `[get_bug_context]` | forbidden: `get_issue`; tool ngoài MCP không chấm |
| `fix_context_attachment` | `backlog fix {issue}` | `OOP-912744` (evidence là ảnh đính kèm `login-error.png`) | `[get_bug_context]` | forbidden: `get_issue`; `finalAnswer.mustMention: ["login-error.png"]` (model biết và báo có tệp đính kèm) |

### 6.3 Nhận diện prompt thật (cho `import-claude`)

Prompt phải chứa `backlog` (không phân biệt hoa thường). Mã issue = mọi chuỗi khớp `\b[A-Z][A-Z0-9_]*-\d+\b`. Thứ tự xét: `resolve` + ≥2 mã → `resolve_multi` (kỳ vọng N apply); `resolve` + 1 mã → `resolve_fixed`; `fix` + 1 mã → `fix_context`; `bug` + (`open` | `mở`) + 0 mã → `open_bugs`. Không khớp → chỉ áp tầng 2. Với prompt thật, `open_bugs_empty`/`resolve_warning`/`fix_context_attachment` không được gán (chỉ dùng trong eval).

## 7. Tầng 2 và 3 — Phân tích

### 7.1 Module

| Module | Trách nhiệm |
|---|---|
| `backlog_tool/telemetry.py` | Ghi log (§5). |
| `backlog_tool/telemetry_store.py` | Đọc các file log (kể cả bản rotate), lọc theo thời gian/`runId`, join `calls`+`details`+`errors` theo `traceId`, nhóm call thành flow. |
| `backlog_tool/telemetry_rules.py` | Tầng 2: rule chung trên một flow. |
| `backlog_tool/telemetry_grader.py` | Tầng 3: chấm flow theo kịch bản. |
| `backlog_tool/telemetry_missing.py` | Phát hiện field thiếu. |
| `backlog_tool/claude_transcripts.py` | Đọc transcript Claude Code, trích prompt, model, tool call (MCP và ngoài MCP), câu trả lời cuối, thời gian. |
| `backlog_tool/telemetry_report.py` | Dựng báo cáo cho `telemetry report`. |

### 7.2 Nhóm flow

- Eval: một flow = một `runId`.
- Claude dùng thật (`import-claude`): ranh giới là prompt người dùng trong transcript; call MCP được gán vào flow qua `tool_use` input (tool name + arguments) khớp `details.arguments` và thời gian trong ±5 s.
- Dùng thật không có transcript (Antigravity): heuristic cũ của `workflow_efficiency` — cùng `sessionId` (fallback client), cùng issue/project, khoảng cách giữa hai call ≤ 180 s.

### 7.3 Rule chung (tầng 2)

| Code | Điều kiện |
|---|---|
| `duplicate_call` | Cùng tool + cùng arguments ≥ 2 lần trong flow |
| `generic_after_specialized` | `get_issue` sau `get_bug_context` cùng issue |
| `generic_before_specialized` | `get_issue` trước `get_bug_context` cùng issue; `get_issues` trước `get_my_open_bugs` |
| `arg_error` | Flow có `arg_error` |
| `retry_after_error` | Cùng tool được gọi lại ngay sau một call lỗi |
| `missing_field` | Kết quả của §7.5 |
| `large_response` | `responseBytes` > 8 KB |

### 7.4 Chấm theo kịch bản (tầng 3)

Kết quả mỗi flow: `{scenario, pass, reasons[], mcpCalls[], extraCalls[], forbiddenHits[], argErrors[], finalAnswerCheck, nonMcpCalls, schemaReads, deniedTools, wallClockMs?, startupMs?, estTokens}`.

`pass` khi đồng thời: `calls` khớp theo `order`; không `forbiddenHits`; không `argErrors`; `finalAnswer` (nếu có) đạt. Chỉ call tới server backlog được tính là MCP call.

### 7.5 Field thiếu

Khi trong một flow, sau call A (tool chuyên dụng) có call B khác tool cùng issue:
1. Ứng viên = đường dẫn field (dạng `a.b.c`) có trong `B.result` mà không có trong `A.result`.
2. Xác nhận: giá trị lá (chuỗi ≥ 4 ký tự hoặc số) của ứng viên xuất hiện trong arguments của call sau B hoặc trong câu trả lời cuối (nếu có transcript) → `missing_field` với danh sách field xác nhận.
3. Có B nhưng không field nào được xác nhận → gắn `routing` (nguyên nhân do wording/routing, không phải thiếu dữ liệu).

### 7.6 CLI

- `backlog-cli telemetry report [--since 1d|2026-09-24] [--run <runId>] [--json]`: danh sách flow (chuỗi tool, flags, kết quả chấm nếu khớp kịch bản) + tổng hợp (top tool theo `estTokens` và `durationMs`, lỗi lặp lại gom theo `kind`+`tool`+tham số, tách theo client/model, tỉ lệ pass theo kịch bản).
- `backlog-cli telemetry import-claude [--since …] [--root …]`: đọc transcript trong `~/.claude/projects/*`, ghép và in báo cáo như `report` cho các prompt chứa `backlog` **hoặc** đã gọi tool `mcp__backlog__*` (trong một phiên, prompt tiếp theo thường không nhắc lại "backlog", ví dụ "OOP-12777 tôi fix rồi"); chỉ prompt khớp §6.3 mới được chấm tầng 3. Tin nhắn chèn tự động (nội dung skill "Base directory for this skill:", `<local-command-caveat>`, `<command-name>`, `<system-reminder>`, `isMeta`, tool_result) không phải prompt.

## 8. Harness eval

### 8.1 Backlog giả (record/replay)

- **Cassette** (`evals/cassettes/oop.json`, chỉ trên máy — repo public): trích từ response thật trong log cũ bằng `python -m evals.cassettes extract --from logs/legacy/telemetry.jsonl`: snapshot mới nhất lúc Open của mỗi bug (21 bug OOP), 8 lần gọi danh sách thật (tham số + kết quả), 22 cặp PATCH (snapshot trước, payload, response sau). Mọi mã issue được đổi `OOP-12762` → `OOP-912762` để eval cấu hình sai không thể chạm bug thật.
- **Độ khớp** được kiểm chứng bằng test trên cassette: mọi issue trong 8 danh sách thật thoả bộ lọc của Backlog giả; áp 22 payload PATCH thật lên snapshot trước cho ra status, assignee, giờ, ngày và custom field giống response thật.
- **Trạng thái**: `default` = danh sách open thật lúc 2026-09-23 16:22 (`912779, 912777, 912774, 912773, 912762, 912749`), các bug khác Resolved và gán về reporter; `no_open_bugs` = mọi bug Resolved, gán về reporter. Hai chỉnh sửa tổng hợp: `912749` Detected Role = Developer (dữ liệu thật đều là Tester), tệp đính kèm của `912744` đổi tên `login-error.png`.
- Máy không có cassette: bộ synthetic cùng mã (dựng từ `tests/fixtures/OOP_issue_bug.json`) để pytest vẫn chạy; eval thật bắt buộc cassette (trừ `--allow-synthetic`).
- HTTP server `127.0.0.1:<port>`: `GET/PATCH /api/v2/issues/{key}`, `GET /api/v2/issues` (lọc `projectId[]`, `assigneeId[]`, `statusId[]`, `issueTypeId[]`, `keyword`, `count`, `offset`), `GET /api/v2/projects/{key}`. Endpoint khác → 404 + ghi `unhandled`.

### 8.2 File đánh dấu `.backlog-eval.json`

Đặt ở root workspace eval: `{"baseUrl": "http://127.0.0.1:<port>", "logDir": "<run log dir>", "runId": "<id>", "scenario": "<id>"}`.

- Khi khởi động, server tìm file này ở workspace (`BACKLOG_WORKSPACE_PATH` → `CLAUDE_PROJECT_DIR` → `cwd`). Có file → `backend=fake`: dùng `baseUrl` thay cho `base_url` trong config (client tự thêm `/api/v2`), API key giả, `logDir`, gắn `runId`/`scenario` vào mọi dòng log.
- Server **từ chối khởi động** nếu `baseUrl` không phải `127.0.0.1`/`localhost`.
- Workspace eval cũng có `.backlog-project.json` = `{"project_key": "OOP"}`.
- Cơ chế này không đụng cấu hình MCP global của Claude Code hay agy: client vẫn chạy MCP server backlog thật như hằng ngày.
- **Đã kiểm chứng (2026-09-24):** `agy -p` chạy trong một thư mục tạm khởi động `backlog-mcp-server` với `cwd` và `PWD` = thư mục đó; `claude` đặt `CLAUDE_PROJECT_DIR`. Cả hai client đều tìm được file đánh dấu mà không cần sửa cấu hình MCP global.

### 8.3 Adapter

`evals/run.py --agent claude|agy --model <m> --scenario <id|all> --runs N [--workspace <path>] [--timeout 300]`

| Agent | Lệnh | Ghi chú |
|---|---|---|
| `claude` | `claude -p "<prompt>" --model <m> --output-format stream-json --verbose --strict-mcp-config --mcp-config <tmp>/mcp.json --disallowedTools Bash Edit Write NotebookEdit WebFetch WebSearch Task Agent` | Chạy trong workspace eval. Ở permission mode `auto` `--allowedTools` không chặn tool (đã probe) nên cô lập bằng MCP: `mcp.json` (trong thư mục tạm của run, không trong workspace) chỉ khai báo server `backlog` = `uv --project <repo> run backlog-mcp-server`; env của agent bỏ mọi biến `BACKLOG_*` trừ `BACKLOG_WORKSPACE_PATH`. Hook/skill global giữ nguyên (D9). |
| `agy` | `agy -p "<prompt>" --model <m> --output-format stream-json --dangerously-skip-permissions --print-timeout <t>` | Chạy trong workspace eval. Không `--sandbox` (làm hỏng mọi lệnh terminal). agy không có `--strict-mcp-config`: runner tạm `agy mcp disable` các MCP server global khác trong batch và bật lại sau. Server `backlog` của agy là cấu hình global chạy từ thư mục repo, nên không sửa code repo trong lúc eval agy. |

Cách lấy call từ stream-json:
- `claude`: `assistant.message.content[].type == "tool_use"`; tool MCP có tên `mcp__backlog__<tool>`; tool khác là call ngoài MCP.
- `agy`: event `step_update` với `state == "DONE"` và `step_type == "tool"`; `tool_name == "call_mcp_tool"` và `tool_info.parameters.ServerName == "backlog"` là MCP call (`ToolName`, `Arguments`); `view_file` trên `~/.gemini/antigravity-cli/mcp/backlog/*` được đếm là `schemaReads` (không phải extra call); tool khác là call ngoài MCP. Câu trả lời cuối = `result.response`.

An toàn khi eval (model có thể tự tìm tới repo và gọi Backlog thật như trong probe): `claude` chạy với `--strict-mcp-config` + MCP config chỉ có server `backlog` + `--disallowedTools Bash Edit Write NotebookEdit WebFetch WebSearch Task Agent` (ở permission mode `auto`, `--allowedTools` không chặn tool); env của mọi agent bỏ `BACKLOG_*` trừ `BACKLOG_WORKSPACE_PATH`; backend là Backlog giả bật bằng `.backlog-eval.json`; `agy` không `--sandbox`. Các lần tool bị từ chối được ghi vào kết quả run. Fixture dùng mã `OOP-9xxxxx` không tồn tại trên Backlog thật.

Mỗi run: tạo workspace tạm (hoặc `--workspace`) → ghi `.backlog-eval.json` + `.backlog-project.json` → start Backlog giả → chạy agent → parse stream-json (prompt, model, tool call MCP và ngoài MCP, câu trả lời cuối, `startupMs` = spawn→event init, `wallClockMs` = event init→event result) → đọc log run → chấm → lưu. Model dừng để hỏi người dùng = run kết thúc; harness không trả lời.

### 8.4 Kết quả

- `evals/results/<YYYY-MM-DD>-<label>/<agent>-<model>.jsonl`: một dòng/run, kết quả §7.4 + `configFingerprint` (phiên bản agent, `gitSha`, hash mô tả tool). **Chỉ trên máy** (gitignore) vì chứa câu trả lời có nội dung bug thật.
- `evals/results/<YYYY-MM-DD>-<label>/SUMMARY.md`: bảng pass-rate theo kịch bản × agent/model, lý do fail phổ biến, token/thời gian trung vị (chỉ để review).
- Chỉ `SUMMARY.md` được commit.

### 8.5 Model mặc định

Claude: `opus`. agy: `gemini-3.8-flash-medium`, `gemini-3.1-pro-high`. Đổi qua `--model`.

## 9. Thay đổi MCP

### 9.1 Tool (12)

`get_issue`, `get_issues`, `create_issue`, `update_issue`, `get_my_open_bugs`, `get_bug_context`, `resolve_bug`, `create_ut_bug`, `get_bug_rules`, `get_bug_fields`, `get_my_work_overview`, `get_my_project_status`.

Chuyển sang CLI (xoá khỏi MCP): `get_config`, `audit_config_workflows`, `inspect_project`, `list_configured_projects`. Xoá 3 MCP prompt (`resolve_bug_prompt`, `create_ut_bug_prompt`, `project_status_prompt`) và resource `backlog://config`, `backlog://metrics`, `backlog://workflow-efficiency`. Giữ `backlog://issue/{issue_key}`.

### 9.2 Chuẩn tên tham số

| Khái niệm | Tên chuẩn | Thay đổi |
|---|---|---|
| Mã issue đang thao tác | `issue_key` | `get_issue.issue_ref` → `issue_key`; `update_issue.issue_ref` → `issue_key`. `get_issue` vẫn nhận ID số, ghi trong description. |
| Mã issue cha | `parent_key` | giữ |
| Project | `project_key` | giữ |
| Chế độ ghi | `mode: "preview"\|"apply"` | Chỉ còn ở tool ghi (tool quản trị có `mode` khác đã sang CLI) |

Test hợp đồng (`tests/test_tool_contract.py`): mọi tham số snake_case; cùng khái niệm dùng cùng tên theo bảng trên; tham số có tập giá trị cố định dùng `Literal`; `additionalProperties: false`; số tool = 12; mọi mô tả tool có câu "Use when"; mô tả tham số mã issue có ví dụ `OOP-123`.

Mã issue được kiểm tra theo `^[A-Z][A-Z0-9_]*-\d+$` (trừ `get_issue` nhận thêm số); tiền tố chưa cấu hình → lỗi nêu danh sách project đã cấu hình.

### 9.3 Lỗi tham số có gợi ý

Wrapper `call_tool` hiện có bắt `ValidationError` và dựng lại thông điệp lỗi trả cho model:
`Invalid arguments for resolve_bug: unknown 'issueKey' (did you mean 'issue_key'?); missing required 'issue_key'. Valid parameters: issue_key, status, …`
Gợi ý dùng `difflib.get_close_matches` trên tên sau khi chuẩn hoá (bỏ `_`, chữ thường). Đồng thời ghi `arg_error` (§5.5).

### 9.4 Text content đủ nội dung

Bổ sung sau baseline: kết quả dạng danh sách có thêm `count` (`{"bugs": [], "count": 0}`) để model không phải gọi lại khi danh sách rỗng.

Theo spec MCP (Tools, 2025-06-18): tool trả `structuredContent` **SHOULD** trả kèm bản JSON serialize của nó trong một `TextContent`. Quyết định: text content = JSON compact (`separators=(",", ":")`, `ensure_ascii=False`) của `structuredContent`; bỏ `_to_markdown` và các dòng `(structured data)`. Client đọc text hay structured đều nhận đủ dữ liệu. Nếu eval cho thấy một client đưa cả hai vào context (token gấp đôi), ghi nhận trong `SUMMARY.md` để xem xét riêng; không đổi quyết định trong dự án này.

Test hợp đồng: với mọi tool, `json.loads(text) == structuredContent`.

### 9.5 `resolve_bug`

- Docstring (thay nguyên văn):
  ```
  Resolve a Backlog bug the user says is fixed, using the configured workflow defaults.

  Call this directly and only once, with mode="apply", when the user asks to resolve/close a Backlog bug
  or says it is already fixed. It loads the issue, rules, field mappings, defaults and validation itself.
  Do not call get_bug_context, get_issue, get_bug_rules or get_bug_fields first.
  fix_description and commit are optional: pass them only if the user gave them; otherwise the
  Corrective Action uses the bug summary. Do not read git history or source code to fill them.
  After applying, report the changes and every warning to the user.
  Use mode="preview" only when the user explicitly asks to preview.
  ```
- `fix_description` không bắt buộc ở apply (bỏ ràng buộc của commit `37cc051`); thiếu → Corrective Action `fixed <summary>` + warning thông tin.
- Apply không bị chặn bởi warning.
- Response apply: `{issue, status, assignee, url, changes: [{field, from, to}], warnings}`; text liệt kê từng change và từng warning.
- Response preview: `{dryRun: true, issue, changes: [{field, from, to}], warnings}`; bỏ `assignment` (trùng change Assignee), bỏ `key` và `id` người dùng.
- Ghi `mutation` (§5.6).

### 9.6 `SERVER_INSTRUCTIONS`

Thay khối routing và mutation safety:
```
Preferred tools:
- My open bugs -> get_my_open_bugs
- Resolve/close a bug, or the user says it is already fixed -> resolve_bug directly with mode="apply" (one call)
- Fix/investigate a bug that is not fixed yet -> get_bug_context (it lists attachments; tell the user when an attachment matters instead of fetching it)
- Personal status -> get_my_project_status
- Generic get/search/update tools are escape hatches only.

Mutation safety:
- resolve_bug: apply directly when the user asks to resolve; report warnings afterwards.
- create_issue, update_issue, create_ut_bug: preview first, apply only after the user confirms.
```
Giữ nguyên khối Activation, Project resolution, Security.

### 9.7 Tệp đính kèm

- `get_bug_context` thêm `attachments: [{id, name, size, isImage}]` (chỉ khi issue có tệp), lấy từ field `attachments` của response `GET /issues/{key}` — không thêm API call.
- Không có tool tải nội dung tệp. Tham khảo khi cần sau này: endpoint *Get Issue Attachment* `GET /api/v2/issues/:issueIdOrKey/attachments/:attachmentId` và MCP image content `{type: "image", data, mimeType}`.

## 10. Phase và điều kiện đóng

Một spec, hai plan: **Plan A** = P0–P3; **Plan B** = P4–P6 (viết sau khi Plan A xong).

| Phase | Nội dung | Điều kiện đóng |
|---|---|---|
| P0 Dọn dẹp | Xoá 8 import thừa và code chết (`IssueView`, `SKILL_DIR`, 6 getter `BacklogClient`, `journal.log_ai/list_sessions`); sửa docstring CLI; đánh dấu plan 2026-09-23 là superseded. | `pytest` pass; `ruff check --select F` sạch. |
| P1 Log nền tảng | §5 toàn bộ (ghi + CLI + xoá sink cũ + `docs/telemetry.md`). | Test mỗi file/event; một ngày dùng thật: đủ 4 loại file, mọi `calls.traceId` có dòng `details`, không `api` mồ côi. |
| P2 Phân tích | §7 toàn bộ. Script một lần chuyển log legacy 2026-09-23 thành fixture định dạng mới trong `tests/fixtures/telemetry-2026-09-23/`. | Test với log tổng hợp; trên fixture 2026-09-23: phát hiện đủ 4 `generic_after_specialized` và các `duplicate_call` đã biết; `import-claude` trên transcript thật gán đúng prompt cho các call `resolve_bug` ngày 23/09. |
| P3 Harness | §8 toàn bộ; replay test; ghi lại trong `docs/telemetry.md` cách đọc stream-json của từng agent. | Replay test pass cả 6 kịch bản; các kịch bản phụ thuộc thay đổi ở P5 (`resolve_*` apply không có `fix_description`, `fix_context_attachment`) được đánh dấu `xfail` và bỏ đánh dấu ở P5; 1 run thật mỗi agent ra file kết quả hợp lệ. |
| P4 Baseline | Chạy MCP hiện tại: mỗi agent/model 5 run × 6 kịch bản. | Commit `evals/results/<ngày>-baseline/` + `SUMMARY.md`. |
| P5 Sửa MCP | §9 toàn bộ. Replay test cập nhật theo hành vi mới. | Test đơn vị, test hợp đồng, replay test pass. |
| P6 Eval lại | Mỗi agent/model 10 run × 6 kịch bản. Chưa đạt → phân tích bằng `telemetry report`, sửa, chạy lại. Kết quả + so sánh baseline vào `SUMMARY.md`; cập nhật README. | Mỗi kịch bản × mỗi agent/model: ≥ 9/10 pass và 0 `arg_error`; **hoặc** người dùng chấp nhận bằng văn bản ngoại lệ cụ thể (kịch bản, model, lý do). |

## 11. Liên hệ plan 2026-09-23

Được giữ (nằm trong spec này): session + gitSha, `planHash`, trạng thái trước/sau, trace CLI, chỉ lưu body khi lỗi/ghi, metrics dẫn xuất từ một nguồn, text content preview đọc được, rule `get_issue` sau `get_bug_context`.
Bỏ: bỏ `rawDescription` và nén `customFields` trong `get_bug_context`, bỏ description trong `get_my_open_bugs` (người dùng tự review field thừa); script purge log test (log cũ chuyển vào `logs/legacy/`).
File plan cũ được thêm dòng đầu `> Superseded by docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md` ở P0.

## 12. Dự án tiếp theo: skill sửa bug đầy đủ

Nằm trong `hieund-ai-kit-cli`, session riêng, sau khi P6 đóng. Spec này chuẩn bị sẵn: `--workspace` cho harness (chạy trong repo mẫu có code), trường `nonMcp` trong kịch bản (bộ chấm hiện bỏ qua), và log/transcript đã ghi tool ngoài MCP.

## 13. Chiến lược test

- TDD cho mọi module mới.
- Test hợp đồng: schema tool (§9.2), text content (§9.4), schema log (mỗi dòng log hợp lệ theo field §5).
- Replay test (`tests/test_replay.py`): client MCP Python nối server thật qua stdio + Backlog giả, gọi đúng chuỗi call kỳ vọng của từng kịch bản, kiểm response và payload PATCH. Chạy trong `pytest`, không dùng model.
- Eval model thật: chạy tay ở P3 (smoke), P4, P6 và mỗi khi đổi mô tả tool/response; không đưa vào CI.

## 14. Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| Client đưa cả text lẫn structured vào context | Theo chuẩn MCP (§9.4); đo token trong eval, ghi nhận nếu có. |
| Backlog giả khác Backlog thật | Cassette ghi từ response thật + test độ khớp (8 danh sách, 22 PATCH); request lạ → 404 + `unhandled`; replay test. |
| Repo public làm lộ dữ liệu thật | Cassette, fixture từ log thật, kết quả eval chi tiết đều gitignore; chỉ commit `SUMMARY.md`. |
| Model không tất định | 10 run/kịch bản, ngưỡng 9/10. |
| Hook global làm tăng lượt/thời gian | Chấp nhận (D9); lượt ngoài MCP được báo cáo riêng. |
| Thời gian chạy ma trận P6 (6 kịch bản × 10 run × 3 model) | Chạy nền, tuần tự; kết quả ghi dần theo run để có thể tiếp tục khi bị ngắt. |
