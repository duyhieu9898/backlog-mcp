# Handoff — trước khi làm Plan B (P4–P6)

Ngày: 2026-09-24. Đọc kèm: `docs/superpowers/specs/2026-09-24-mcp-telemetry-eval-design.md` (spec), `docs/telemetry.md` (log + eval), `docs/superpowers/plans/2026-09-24-plan-a-telemetry-analysis-harness.md` (Plan A, đã xong).

**Cách làm session sau (người dùng yêu cầu):** thực thi trực tiếp trong session (inline), **không dùng subagent-driven**. Commit thẳng `main`, push `main`.

## 1. Trạng thái

- Plan A (P0–P3) xong, đã push (`3e81394..f239dc3`). 243 test pass + 4 xfail (`tests/test_replay.py`, chờ P5).
- P1 đã kiểm chứng với Backlog thật (chỉ đọc) ngày 2026-09-24: MCP `get_my_open_bugs`, MCP gọi sai tham số, CLI `bug list` → mọi call có dòng `details`, `sessions` đúng `gitSha`, không có API key/`apiKey=` trong log, `arg_error` có gợi ý. Việc còn lại phía người dùng: restart Claude Code/Antigravity và dùng thật để có log MCP thật.
- Dữ liệu chỉ nằm trên máy (gitignore): `evals/cassettes/oop.json` (21 issue / 8 danh sách / 22 PATCH, rekey `OOP-9xxxxx`), `tests/fixtures/local/telemetry-2026-09-23/`, `evals/results/**/*.jsonl`.

## 2. Baseline P4 (MCP hiện tại, dữ liệu cassette)

Kết quả: `evals/results/2026-09-24-baseline/SUMMARY.md`.

### Claude (opus) — 35/35 lượt, dữ liệu sạch

| Kịch bản | Pass | MCP call (trung vị) | Thời gian (trung vị) | Nhận xét |
|---|---|---|---|---|
| open_bugs | 5/5 | 1 | 15 s | response nặng: ~4.1k token |
| fix_context | 5/5 | 1 | 22 s | |
| open_bugs_empty | 2/5 | 1 | 9 s | câu trả lời không nói rõ "0" bug (text trả về `No data.`) |
| resolve_fixed | 0/5 | 1 | 13 s | không có apply thành công (mặc định preview / apply đòi `fix_description`) |
| resolve_multi | 0/5 | 2 | 14 s | như trên |
| resolve_warning | 0/5 | 2 | 18 s | như trên |
| fix_context_attachment | 0/5 | 1 | 16 s | `get_bug_context` chưa liệt kê attachments |

→ Khớp các mục P5 trong spec: §9.5 (resolve một lần `mode="apply"`, `fix_description` không bắt buộc), §9.7 (attachments), §9.4 (text = JSON đầy đủ; cân nhắc thêm tổng số bug rõ ràng cho danh sách rỗng), và giảm payload `get_my_open_bugs`.

### Gemini 3.8 Flash medium (agy) — dừng ở 9/35 lượt, dữ liệu NHIỄU

`open_bugs` 0/5, `open_bugs_empty` 0/4. Hành vi thật quan sát được (hữu ích cho P5): đọc schema liên tục (tới 20 `view_file`), gọi `list_configured_projects`, `get_config`, `get_issues`, `inspect_project`, `audit_config_workflows`, gọi `get_my_open_bugs` tới 5 lần vì không tin text `No data.`.

Không dùng số liệu Flash hiện tại để kết luận — xem mục 3. Gemini 3.1 Pro chưa chạy.

## 3. Lỗi harness phát hiện khi chạy agy (sửa trước khi chạy lại Flash)

1. **agy không tự thoát sau khi xong**: lượt có `wallClockMs` 75 s nhưng process sống 303 s (tới `--print-timeout 300s`). → `evals/run.py` đọc stdout theo luồng (Popen) và dừng agy ngay khi nhận event `result`; giữ timeout làm chốt chặn.
2. **`agentOk` báo sai**: lượt không có bước nào (`turns=0`, `wallClockMs=0`) vẫn `agentOk=True`. → `parse_agy` chỉ `raw_ok=True` khi có event `result` với `status == "SUCCESS"` và có ít nhất một bước; thêm phân loại `envError` (503 dịch vụ Gemini, lỗi sandbox, timeout) tách khỏi "model làm sai" trong `SUMMARY.md`.
3. **`--sandbox` gây lỗi** `connecting to sandbox server: … connection reset` mỗi khi model thử lệnh terminal. → quyết định: bỏ `--sandbox` (an toàn đã có nhờ scrub env `BACKLOG_*` + fake backend + mã `OOP-9xxxxx`) hoặc giữ và coi lỗi này là môi trường.
4. **MCP call chậm bất thường** (`list_configured_projects` > 2 phút): nghi agy khởi động các MCP server global khác (`chrome-devtools-mcp --autoConnect`, `website-design-systems` qua npx). agy không có `--strict-mcp-config`. Phương án: tạm `agy mcp disable` các server đó trong lúc eval (**là thay đổi cấu hình global — hỏi người dùng trước**).
5. `inspect_project` gọi `/projects/OOP/issueTypes` → 404 trên Backlog giả (tool quản trị, sẽ bị bỏ ở P5).
6. Bẫy khi viết lệnh: shell là **zsh**, `set -- $var` không tách từ; viết lệnh eval tường minh từng dòng.

## 4. Các quyết định/việc còn treo

- Spec §8.3, đoạn "An toàn khi eval" còn nhắc `--allowedTools`; code dùng `--strict-mcp-config` + MCP config chỉ có backlog + denylist tool built-in. Sửa đoạn spec khi cập nhật spec cho Plan B.
- `telemetry_store.load_calls(since=)` so timestamp dạng chuỗi (cùng offset trên một máy nên tạm ổn).
- Chưa có `startupMs`; chưa trace đọc resource `backlog://issue/{issue_key}`.
- Minor để sau: `log_session_start` gọi git 2 lần cho mỗi lệnh CLI; agy gọi MCP server khác được ghi dưới tên `call_mcp_tool` trong `nonMcpCalls`.

## 5. Thứ tự việc session sau

1. Sửa harness agy (mục 3.1–3.3; 3.4 hỏi người dùng) + test.
2. Chạy lại baseline Gemini Flash (7 kịch bản × 5 lượt) bằng lệnh tường minh; Gemini Pro tuỳ thời gian.
   ```bash
   uv run python -m evals.run --agent agy --model gemini-3.8-flash-medium --scenario all --runs 5 --label baseline-flash --timeout 300
   ```
3. Viết Plan B (P5 sửa MCP theo spec §9 + các điểm baseline chỉ ra; P6 eval lại 10 lượt/kịch bản/model, đóng khi ≥ 9/10 và 0 `arg_error`), cập nhật spec nếu cần; người dùng duyệt.
4. Thực thi Plan B inline.
