# Eval summary — 2026-09-24-p6-final

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 10/10 | 0 | 0 | 1865 | 23870 |
| fix_context_attachment | 10/10 | 0 | 0 | 2488 | 16841 |
| open_bugs | 10/10 | 0 | 0 | 2583 | 13816 |
| open_bugs_empty | 9/10 | 0 | 0 | 105 | 8374 |
| resolve_fixed | 10/10 | 0 | 0 | 288 | 10171 |
| resolve_multi | 10/10 | 0 | 0 | 524 | 12006 |
| resolve_warning | 10/10 | 0 | 0 | 344 | 11018 |

Lý do fail phổ biến: final answer does not mention [['0', 'không có']] ×1

## Ghi chú

Chạy trên `fcb58aa`: sau P5, sửa review (giữ Corrective Action cũ, chặn resolve lại) và bỏ `description` khỏi `get_my_open_bugs`, sửa các lỗi minor. Tất cả 70 lượt cùng một commit.

`open_bugs_empty` lúc chạy được chấm với `mustMention: ["0"]` → 7/10: ba câu trả lời đúng ý nhưng viết "không có bug nào" thay vì "0". Người dùng quyết định nới bộ chấm thành `[["0", "không có"]]`; các lượt `open_bugs_empty` được chấm lại trên câu trả lời đã lưu (`regraded` trong jsonl) → 9/10. Lượt còn fail viết "không trả về bug nào". Các kịch bản khác không bị chấm lại.

| Kịch bản | Baseline | P6 (`2026-09-24-p6`) | P6 cuối | estTokens trung vị baseline → P6 → P6 cuối |
|---|---|---|---|---|
| open_bugs | 5/5 | 10/10 | 10/10 | 4094 → 7858 → 2583 |
| open_bugs_empty | 2/5 | 10/10 | 9/10 | 76 → 105 → 105 |
| resolve_fixed | 0/5 | 10/10 | 10/10 | 337 → 320 → 288 |
| resolve_multi | 0/5 | 10/10 | 10/10 | 625 → 542 → 524 |
| resolve_warning | 0/5 | 10/10 | 10/10 | 699 → 376 → 344 |
| fix_context | 5/5 | 10/10 | 10/10 | 974 → 1865 → 1865 |
| fix_context_attachment | 0/5 | 10/10 | 10/10 | 1261 → 2488 → 2488 |

Điều kiện đóng P6 (§10): mọi kịch bản ≥ 9/10, 0 `arg_error` → **đạt**.
