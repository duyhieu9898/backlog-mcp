# Eval summary — 2026-09-28-skill-on-2

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_code | 3/3 | 0 | 0 | 1122 | 32606 |
| fix_code_on_main | 3/3 | 0 | 0 | 600 | 24176 |
| fix_code_tests_fail | 3/3 | 0 | 0 | 600 | 27364 |

## Ghi chú (sau review, `4e7109e`)

9/9 sau các sửa từ review: test ẩn chạy trên bản clone của nhánh đã push; commit không được chứa bytecode/marker/`.claude/`; `.backlog-project.json` để untracked như repo thật; skill chỉ xét thay đổi file đã track và `git add <paths>`; agent chạy `--permission-mode dontAsk` với whitelist thật. Commit của 3 lượt `fix_code` chỉ gồm `rewards/referral.py` và `tests/test_referral.py`. 6/9 lượt có lệnh Bash ngoài whitelist bị từ chối (`deniedTools: ["Bash"]`), agent tự đổi cách và vẫn hoàn thành.
