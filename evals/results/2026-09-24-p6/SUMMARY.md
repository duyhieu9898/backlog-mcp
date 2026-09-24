# Eval summary — 2026-09-24-p6

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 10/10 | 0 | 0 | 1865 | 22985 |
| fix_context_attachment | 10/10 | 0 | 0 | 2488 | 16702 |
| open_bugs | 10/10 | 0 | 0 | 7858 | 14794 |
| open_bugs_empty | 10/10 | 0 | 0 | 105 | 8392 |
| resolve_fixed | 10/10 | 0 | 0 | 320 | 11300 |
| resolve_multi | 10/10 | 0 | 0 | 542 | 13614 |
| resolve_warning | 10/10 | 0 | 0 | 376 | 13430 |

## So sánh với baseline (claude opus)

Baseline: `2026-09-24-baseline` (5 lượt/kịch bản, MCP trước P5, gitSha `f239dc3`). P6: 10 lượt/kịch bản, MCP sau P5. `open_bugs`, `open_bugs_empty` chạy trên `3864da2`; 5 kịch bản còn lại chạy lại trên `8b41fab` (sau khi sửa theo review: giữ Corrective Action cũ khi thiếu `fix_description`, chặn resolve bug đã ở trạng thái đích). Hai kịch bản `open_bugs*` không đi qua code thay đổi giữa hai commit.

| Kịch bản | Pass baseline → P6 | MCP call trung vị | estTokens trung vị | wallClockMs trung vị |
|---|---|---|---|---|
| open_bugs | 5/5 → 10/10 | 1 → 1 | 4094 → 7858 | 15002 → 14794 |
| open_bugs_empty | 2/5 → 10/10 | 1 → 1 | 76 → 105 | 8822 → 8392 |
| resolve_fixed | 0/5 → 10/10 | 1 → 1 | 337 → 320 | 13360 → 11300 |
| resolve_multi | 0/5 → 10/10 | 2 → 2 | 625 → 542 | 14329 → 13614 |
| resolve_warning | 0/5 → 10/10 | 2 → 1 | 699 → 376 | 18313 → 13430 |
| fix_context | 5/5 → 10/10 | 1 → 1 | 974 → 1865 | 21592 → 22985 |
| fix_context_attachment | 0/5 → 10/10 | 1 → 1 | 1261 → 2488 | 16181 → 16702 |

Điều kiện đóng P6 (§10): mọi kịch bản ≥ 9/10 và 0 `arg_error` → **đạt** (70/70, `ArgErr` 0, `EnvErr` 0).

Ghi nhận:
- `estTokens` được tính từ `responseBytes` = kích thước response đã serialize (gồm cả text lẫn `structuredContent`). Từ P5 text là bản JSON đầy đủ của `structuredContent` (§9.4), nên với response lớn (`open_bugs`, `fix_context*`) con số này gần gấp đôi. Đây là rủi ro §14 "client đưa cả text lẫn structured vào context"; eval này không đo được client thực sự nạp gì vào context. Response resolve nhỏ đi vì bỏ `assignment` và id người dùng.
- Gemini (agy) bị loại khỏi P6 theo quyết định người dùng ngày 2026-09-24 (API Gemini không ổn định trong ngày); baseline Flash cũ (9 lượt, nhiễu) giữ nguyên ở trên chỉ để tham khảo.
- Payload `get_my_open_bugs` (phần lớn là `description` từng bug) chưa giảm — để người dùng quyết sau (ngoài phạm vi spec §3).
