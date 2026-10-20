# Eval summary — 2026-10-20-quick-handoff

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 3/3 | 0 | 0 | 1026 | 24776 |
| fix_context_attachment | 3/3 | 0 | 0 | 1379 | 20412 |
| fix_context_handoff | 0/3 | 0 | 0 | 2637 | 23140 |
| open_bugs | 3/3 | 0 | 0 | 1382 | 11439 |
| open_bugs_empty | 3/3 | 0 | 0 | 136 | 9747 |
| resolve_fixed | 3/3 | 0 | 0 | 344 | 8637 |
| resolve_follow_up | 3/3 | 0 | 0 | 240 | 14920 |
| resolve_multi | 3/3 | 0 | 0 | 586 | 11494 |
| resolve_warning | 3/3 | 0 | 0 | 400 | 9529 |

Lý do fail phổ biến: extra calls ×3
