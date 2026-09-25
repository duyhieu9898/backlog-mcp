# Eval summary — 2026-09-25-codex

## codex-gpt-5.6-terra

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 5/5 | 0 | 0 | 1865 | 37257 |
| fix_context_attachment | 4/5 | 0 | 0 | 2488 | 39188 |
| open_bugs | 5/5 | 0 | 0 | 2583 | 41651 |
| open_bugs_empty | 4/5 | 0 | 0 | 106 | 27713 |
| resolve_fixed | 4/5 | 0 | 0 | 288 | 58298 |
| resolve_multi | 3/5 | 0 | 0 | 676 | 51593 |
| resolve_warning | 2/5 | 0 | 0 | 344 | 46379 |

Lý do fail phổ biến: missing expected call resolve_bug {'issue_key' ×5, final answer does not mention ['Tester'] ×3, missing expected call get_my_open_bugs {} ×1, final answer does not mention ['login-error.png'] ×1

## Ghi chú (Codex CLI 0.155.1, `gpt-5.6-terra`, reasoning medium)

Cấu hình adapter: `codex exec --json --sandbox read-only -c approval_policy="on-request"`, server `backlog` global (chỉ đặt `env`), các MCP server khác tắt bằng `-c`. Commit `3be1b28`.

- 27/35 pass, `ArgErr` 0, không lượt nào gọi MCP thừa hay sai tool. Mọi lượt có MCP call đều gọi đúng tool, đúng tham số.
- Chậm hơn Claude 2–4 lần (trung vị 28–58 s): trước khi dùng MCP, Codex chạy 2–16 lệnh shell dò workspace, và tool MCP phải tự tìm qua `ALL_TOOLS` (code mode).
- 4 lượt không dùng MCP (open_bugs_empty ×1, resolve_fixed ×1, resolve_multi ×2): model đi đường shell. Codex xin nâng quyền (`require_escalated`) và `approvals_reviewer = "auto_review"` duyệt, nên model thoát `read-only`:
  - dùng `backlog-cli` trên PATH (đọc `.env` thật → Backlog thật): `issue get`, `issue list --project OOP`, `config list-projects`, `bug resolve` **không** `--apply` (dry-run). Không có lệnh ghi thật; mã fixture `OOP-9xxxxx` không tồn tại nên trả 404.
  - một lượt đọc `.backlog-eval.json`, dò `/openapi.json` rồi `curl -X PATCH` thẳng vào Backlog giả.
- 4 lượt fail vì câu trả lời: resolve_warning ×3 diễn đạt warning ("bạn đang ở vai trò Developer… xác nhận người QC") mà không có chữ "Tester"; fix_context_attachment ×1 không nhắc tệp đính kèm.
