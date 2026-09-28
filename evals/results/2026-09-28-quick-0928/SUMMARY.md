# Eval summary — 2026-09-28-quick-0928

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 3/3 | 0 | 0 | 1017 | 18177 |
| fix_context_attachment | 3/3 | 0 | 0 | 1370 | 17015 |
| open_bugs | 3/3 | 0 | 0 | 1379 | 12455 |
| open_bugs_empty | 3/3 | 0 | 0 | 136 | 7218 |
| resolve_fixed | 3/3 | 0 | 0 | 208 | 9430 |
| resolve_multi | 3/3 | 0 | 0 | 586 | 11149 |
| resolve_warning | 3/3 | 0 | 0 | 254 | 9962 |

## Ghi chú

Chạy nhanh (3 lượt/kịch bản) trên `38566fc`, sau đợt review MCP 2026-09-28: gộp 4 tool danh sách thành `list_my_issues`, gộp `get_bug_context` vào `get_issue` (8 tool), "me" suy ra từ API key, instructions viết lại, output luồng chính gọn lại, tool ghi trả `changes`, annotations. Kịch bản `open_bugs*` kỳ vọng `list_my_issues(issue_types=["Bug"])`, `fix_context*` kỳ vọng `get_issue`.

So với P6 (`2026-09-24-p6-final`, 69/70): 21/21, `ArgErr` 0. Token trung vị giảm ở luồng đọc: fix_context 1865 → 1017, fix_context_attachment 2488 → 1370, open_bugs 2583 → 1379, resolve_fixed 288 → 208, resolve_warning 344 → 254; tăng nhẹ ở open_bugs_empty 105 → 136 (thêm `summary`) và resolve_multi 524 → 586. Thời gian tương đương hoặc nhanh hơn. 3 lượt chỉ bắt được hồi quy lớn, chưa thay được mốc 10 lượt.
