# Eval summary — 2026-09-24-baseline

## agy-gemini-3.8-flash-medium

| Scenario | Pass/Runs | Median estTokens | Median wallClockMs |
|---|---|---|---|
| open_bugs | 0/5 | 0 | 0 |
| open_bugs_empty | 0/4 | 914 | 172994 |

Lý do fail phổ biến: extra calls ×5, missing expected call get_my_open_bugs {} ×4, final answer missing ×4, forbidden calls ×3

## claude-opus

| Scenario | Pass/Runs | Median estTokens | Median wallClockMs |
|---|---|---|---|
| fix_context | 5/5 | 974 | 21592 |
| fix_context_attachment | 0/5 | 1261 | 16181 |
| open_bugs | 5/5 | 4094 | 15002 |
| open_bugs_empty | 2/5 | 76 | 8822 |
| resolve_fixed | 0/5 | 337 | 13360 |
| resolve_multi | 0/5 | 625 | 14329 |
| resolve_warning | 0/5 | 699 | 18313 |

Lý do fail phổ biến: missing expected call resolve_bug {'issue_key' ×19, extra calls ×15, final answer does not mention ['login-error.png'] ×5, final answer does not mention ['0'] ×3
