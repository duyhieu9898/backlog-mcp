# Eval summary — 2026-09-28-mcp-after-skill

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 3/3 | 0 | 0 | 1017 | 19790 |
| fix_context_attachment | 3/3 | 0 | 0 | 1370 | 15874 |
| open_bugs | 3/3 | 0 | 0 | 1379 | 12122 |
| open_bugs_empty | 3/3 | 0 | 0 | 136 | 7591 |
| resolve_fixed | 3/3 | 0 | 0 | 208 | 10026 |
| resolve_multi | 3/3 | 0 | 0 | 586 | 10510 |
| resolve_warning | 3/3 | 0 | 0 | 254 | 10343 |

## Ghi chú

Chạy sau khi thêm chế độ sửa code vào harness (`ccd99cd`): 21/21, bằng đợt `quick-0928`; kịch bản code không nằm trong `all`.
