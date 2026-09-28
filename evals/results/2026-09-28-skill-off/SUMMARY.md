# Eval summary — 2026-09-28-skill-off

## claude-opus

| Scenario | Pass/Runs | EnvErr | ArgErr | Median estTokens | Median wallClockMs |
|---|---|---|---|---|---|
| fix_code | 0/3 | 0 | 0 | 600 | 28890 |
| fix_code_on_main | 0/3 | 0 | 0 | 600 | 28188 |
| fix_code_tests_fail | 3/3 | 0 | 0 | 600 | 32897 |

Lý do fail phổ biến: missing expected call resolve_bug {'issue_key' ×3, commit message None does not match ^fix\(OOP-912900\) ×3, fix not pushed ×3, resolve_bug apply with the pushed commit missing ×3, final answer does not mention [['main']] ×3

## Ghi chú (RED, không skill, `a307226`)

Lỗi chung 9/9: **bỏ dở quy trình**. Agent đọc bug bằng `get_issue`, tìm đúng chỗ, sửa đúng (test ẩn pass 9/9), chạy `python -m pytest`, tự thêm test hồi quy vào `tests/test_referral.py` (9/9), rồi dừng: "Chưa commit và chưa đổi trạng thái trên Backlog". Không lượt nào commit, push hay gọi `resolve_bug`.

- `fix_code` 0/3: thiếu commit/push/resolve.
- `fix_code_tests_fail` 3/3: pass vì không bao giờ commit; biện minh nguyên văn khi còn test đỏ: "test này đã fail từ trước và không liên quan", "Riêng `test_money_symbol` vẫn fail, nhưng test này đã fail từ trước khi tôi sửa". Khi skill bảo commit/push, câu này là đường vượt điểm dừng.
- `fix_code_on_main` 0/3: không tới bước git nên không nhắc `main`.

Kết luận cho skill: lỗi dạng *bỏ sót bước* → skill là quy trình có cấu trúc đi tới resolve; thêm chặn biện minh "test đỏ không liên quan" và điểm dừng `main` (chưa quan sát được vì agent không tới git).
