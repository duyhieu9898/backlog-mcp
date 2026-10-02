# Eval summary — 2026-10-02-quick-default-apply

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_context | 1/3 | 0 | 0 | 0 | 13063 |
| fix_context_attachment | 0/3 | 0 | 0 | 0 | 12963 |
| open_bugs | 3/3 | 0 | 0 | 1379 | 12055 |
| open_bugs_empty | 3/3 | 0 | 0 | 136 | 7015 |
| resolve_fixed | 3/3 | 0 | 0 | 344 | 7747 |
| resolve_multi | 3/3 | 0 | 0 | 586 | 10683 |
| resolve_warning | 3/3 | 0 | 0 | 400 | 11065 |

Lý do fail phổ biến: missing expected call get_issue {'issue_key' ×5, final answer does not mention ['login-error.png'] ×3
