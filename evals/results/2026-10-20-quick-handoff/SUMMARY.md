# Eval summary — 2026-10-20-quick-handoff

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 3/3 | 0 | 0 | 1026 | 30053 |
| fix_context_attachment | 3/3 | 0 | 0 | 1379 | 26289 |
| fix_context_handoff | 3/3 | 0 | 0 | 1202 | 25407 |
| open_bugs | 3/3 | 0 | 0 | 1382 | 12563 |
| open_bugs_empty | 3/3 | 0 | 0 | 136 | 9070 |
| resolve_fixed | 3/3 | 0 | 0 | 344 | 7592 |
| resolve_follow_up | 2/3 | 0 | 0 | 240 | 11057 |
| resolve_multi | 3/3 | 0 | 0 | 586 | 13468 |
| resolve_warning | 3/3 | 0 | 0 | 400 | 12322 |

Lý do fail phổ biến: missing expected call resolve_bug {'issue_key' ×1, extra calls ×1, forbidden calls ×1
