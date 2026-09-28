# Prompt ngắn cho Backlog MCP và skill `fix-backlog-bug`

Prompt tốt là prompt khớp với thứ MCP và skill đã được thiết kế để nhận: mỗi thành phần xoá một chỗ model phải đoán.

## Công thức

```
backlog <động từ> <KEY> [, dữ liệu tuỳ chọn]
```

| Thành phần | Làm gì | Thiếu thì |
|---|---|---|
| `backlog` | Tín hiệu kích hoạt MCP (mục Activation trong instructions) | Model có thể trả lời chung, không gọi Backlog |
| Động từ: `fix`, `resolve`, `bug open`… | Chọn tool / skill | Model đoán ý định: đọc, sửa hay resolve? |
| Key `OOP-12345` | Chỉ đúng issue; tiền tố = project | Model hỏi lại, hoặc server không xác định được project |
| Dữ liệu tuỳ chọn | Đi thẳng vào tham số | MCP dùng mặc định (vẫn đúng, ít chi tiết hơn) |

## Mẫu

Cột "Kiểm chứng": **eval** = có kịch bản eval đạt; **thiết kế** = đúng theo instructions/mô tả tool, chưa có eval riêng.

| Ý định | Prompt | Kết quả | Kiểm chứng |
|---|---|---|---|
| Bug của tôi | `backlog kiểm tra bugs open` | `list_my_issues(issue_types=["Bug"])` | eval |
| Story/task, deadline | `backlog task của tôi` | `list_my_issues(issue_types=["Story", "Task"])` | thiết kế |
| Việc cần làm | `backlog tôi cần làm gì` | `list_my_issues()` | thiết kế |
| Ngoài repo, chỉ project | `backlog bug open NLN` | không lỗi "Cannot determine project" | thiết kế |
| Đọc / tìm hiểu một bug | `backlog xem OOP-12345` | `get_issue` | thiết kế (eval `fix_context` dùng `backlog fix` khi không có skill) |
| **Sửa bug trọn quy trình** | `backlog fix OOP-12345` (đứng trong repo) | skill: đọc → sửa → test → commit `fix(OOP-12345): …` → push → resolve | eval (skill, 9/9) |
| Chỉ sửa, chưa commit | `backlog fix OOP-12345, chưa commit` | skill dừng sau khi sửa và test | thiết kế |
| Resolve bug tự sửa | `backlog resolve OOP-12345, bug này tôi fix rồi` | một `resolve_bug(mode="apply")` | eval |
| Resolve kèm thông tin | `backlog resolve OOP-12345, commit abc1234, fix: OTP báo thời gian chờ` | điền `commit`, `fix_description` (Corrective Action `fixed OTP báo thời gian chờ`) | thiết kế |
| Resolve nhiều bug | `backlog resolve OOP-1, OOP-2` | mỗi bug một `resolve_bug` | eval |
| Xem trước, chưa ghi | thêm `xem trước` | `mode="preview"` | thiết kế |
| Tạo UT bug | `backlog tạo UT bug dưới OOP-123, module payment: tổng tiền bỏ qua giảm giá` | `create_ut_bug(parent_key, module, summary)` | thiết kế |

## Tránh

- **Diễn giải dài.** `fix` / `resolve` đã quyết định luồng; thêm giải thích chỉ thêm chỗ hiểu sai.
- **Dặn điều tool/skill tự làm** ("đọc rule trước", "check field rồi resolve"). Tool đã tự làm; lời dặn sinh lượt gọi thừa (`get_issue`, `get_bug_rules` trước `resolve_bug` — đã thấy trong log cũ).
- **Động từ mơ hồ** ("xử lý bug này"): sửa code hay resolve? Dùng đúng `fix` hoặc `resolve`.
- **Thiếu key** ("bug vừa rồi") khi hội thoại có nhiều bug.

## Thêm ràng buộc

Một mệnh đề ngắn nói **kết quả**, không nói cách làm: `chưa commit`, `xem trước`, `project NLN`, `fix: <mô tả>`, `commit <sha>`. Mỗi mệnh đề ứng với đúng một tham số hoặc điểm dừng có sẵn trong MCP/skill, nên model không phải suy diễn.
