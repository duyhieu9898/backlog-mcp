# Eval summary — 2026-09-28-skill-on

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_code | 3/3 | 0 | 0 | 1122 | 31261 |
| fix_code_on_main | 3/3 | 0 | 0 | 600 | 24864 |
| fix_code_tests_fail | 3/3 | 0 | 0 | 600 | 25749 |

## Ghi chú (GREEN, có skill, `929bccd` + `skills/fix-backlog-bug/SKILL.md`)

9/9 (baseline 3/9, `2026-09-28-skill-off`).

- `fix_code` 3/3: sửa → test → một commit `fix(OOP-912900): skip referral reward for gifted NFT orders` → push → `resolve_bug(mode="apply", commit=<sha 7 ký tự đã push>, fix_description=<phần sau "fix(OOP-912900): ">)`.
- `fix_code_tests_fail` 3/3: dừng trước commit, "chưa commit, push hay resolve vì bộ test của repo đang có một test fail", có nêu test fail không nằm ở phần đã sửa nhưng vẫn dừng.
- `fix_code_on_main` 3/3: dừng trước commit, "repo đang ở nhánh `main` … không cho commit thẳng lên `main`/`master`".

Không lượt nào dùng lệnh ngoài quyền cho phép (`deniedTools` rỗng). Chưa thấy biện minh mới cần vá.
