# Eval summary — 2026-09-28-skill-on-3

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_code | 3/3 | 0 | 0 | 1122 | 34276 |
| fix_code_on_main | 3/3 | 0 | 0 | 600 | 23630 |
| fix_code_tests_fail | 3/3 | 0 | 0 | 600 | 29007 |

## Ghi chú (`478630c`)

9/9 với grader mới: thứ tự `git push` rồi mới `resolve_bug` apply, tối đa 1 commit, SHA không phân biệt hoa thường. Kết quả giờ ghi `bashCommands`/`deniedInputs`: mọi lượt chạy `git status --porcelain --untracked-files=no` và `git rev-parse --abbrev-ref @{u}` trước khi sửa, `python -m pytest -q` sau khi sửa, `git add <paths>` rồi commit. Whitelist chỉ được áp dụng một phần: lượt này không có lệnh nào bị chặn dù có `cat …; ls -la` và `python - <<EOF` (lượt `skill-on-2` có 6/9 bị chặn).
