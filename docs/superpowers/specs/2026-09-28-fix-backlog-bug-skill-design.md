# Skill `fix-backlog-bug` + eval sửa code — thiết kế

Ngày: 2026-09-28. Trạng thái: chờ duyệt.

## 1. Mục tiêu

Người dùng gõ "backlog fix OOP-123" → agent đi trọn quy trình: đọc bug → định vị code → sửa → chạy test → commit → push → `resolve_bug`. Skill chỉ dùng 8 tool của Backlog MCP (bề mặt đã chốt sau review 2026-09-28) và không thêm logic vào MCP.

Tiêu chí: thực dụng và đúng chuẩn; ngắn; chạy được trên Claude Code (eval bước này chỉ Claude), sau này cả Codex/Antigravity.

**Ngoài phạm vi**
- Resolve bug người dùng tự sửa: MCP xử lý trực tiếp (`resolve_bug`, mặc định), skill không kích hoạt.
- Tạo PR, sửa nhiều bug trong một lượt, tự viết test mới.
- Eval Codex/agy cho skill; chuyển skill sang `hieund-ai-kit-cli` (làm sau, chỉ là di chuyển file).

## 2. Ranh giới MCP ↔ skill

| Lớp | Chứa | Không chứa |
|---|---|---|
| Mô tả tool | Sự thật về một tool | Quy trình |
| Instructions server | Điều đúng với mọi quy trình dùng server (activation, ý định → tool, project, "writes apply directly") | Code, git, test |
| Skill | Chuỗi bước, điểm dừng, mọi thứ ngoài Backlog | Chép lại field/tham số tool |

Skill chỉ **thu hẹp** mặc định của instructions (ví dụ "chỉ `resolve_bug` sau khi push thành công"), không mâu thuẫn. Skill không giả định model đã đọc instructions. Instructions hiện tại không cần sửa.

## 3. Quyết định đã chốt

| Chủ đề | Quyết định |
|---|---|
| Định vị code | Đang trong repo có `.backlog-project.json`: project khớp tiền tố key → sửa tại chỗ; không khớp → dừng, hỏi. Ngoài repo: map cục bộ theo máy (không commit) `project → [{path, hint}]`, chọn repo theo hint khớp tiêu đề bug; không có → hỏi một lần, đề nghị lưu. |
| Test | Lệnh test lấy từ chỉ dẫn repo (`CLAUDE.md`/`AGENTS.md`/`README`), rồi cấu hình build (`package.json` script `test`, `Makefile test`, `pytest` khi có `pyproject.toml`, `go test ./...`). Fail → dừng: không commit, không resolve, báo. Không có lệnh → bỏ qua, ghi rõ trong báo cáo. Không tự viết test. |
| Git | Commit + push lên nhánh đang đứng. Nhánh là `main`/`master` hoặc không có upstream → dừng trước commit; push bị từ chối → dừng, không resolve. Không `--force`. Thay đổi có sẵn chưa commit trước khi sửa → hỏi, không gộp. |
| Commit | Commitlint: `fix(OOP-12345): <mô tả ngắn>` (scope = key bug). |
| Resolve | Chỉ sau push thành công: `resolve_bug(issue_key, mode="apply", commit=<sha đã push>, fix_description=<mô tả ngắn của commit>)`. Báo lại `changes` và warning. |
| Đính kèm | `get_issue` chỉ liệt kê file; tệp quan trọng (ảnh evidence) → nói với người dùng, không tự tải. |

## 4. Thành phần

1. **Skill** `skills/fix-backlog-bug/SKILL.md` (tạm trong repo này). Nội dung viết sau baseline (TDD cho skill, §6). Frontmatter: `name`, `description` chỉ nêu điều kiện kích hoạt ("Use when the user asks to fix a Backlog bug by key or link…"), không tóm tắt quy trình.
2. **Repo mẫu** `evals/fixtures/fix_repo/`: package Python nhỏ, một bug khớp bug giả; test sẵn có pass (không phủ bug). **Test ẩn** `evals/fixtures/fix_repo_hidden_test.py` không chép vào workspace, grader dùng để xác nhận bug đã sửa.
   - Bug: `referral_reward(order)` vẫn trả 10% cho NFT tặng miễn phí; kỳ vọng 0 khi `order.is_gift`.
   - Biến thể `tests_fail`: thêm một test hỏng sẵn, không liên quan (định dạng tiền tệ).
3. **Backlog giả**: bug tổng hợp `OOP-912900` (Bug, Open, gán cho "me", người báo có Detected Role Tester, customFields đủ để `resolve_bug` chạy như bug cassette), mô tả theo template: Steps/Actual/Expected nói đúng lỗi trên. Có ở cả nguồn cassette và synthetic.
4. **Harness** — kịch bản có trường `code`:
   ```json
   "code": {"fixture": "fix_repo", "variant": null, "branch": "develop"}
   ```
   - Chuẩn bị workspace: chép fixture (+ biến thể), `git init`, commit "chore: initial", tạo remote bare trong thư mục tạm, checkout `branch`, push và đặt upstream. Marker `.backlog-project.json` (OOP) và `.backlog-eval.json` như hiện nay (marker được `.git/info/exclude` để không lẫn vào diff).
   - Agent `claude`: bỏ chặn `Bash`/`Edit`/`Write`; vẫn chặn `NotebookEdit`/`WebFetch`/`WebSearch`/`Task`/`Agent`.
   - Cờ `--skill on|off` (mặc định `off`): `on` → chép `skills/fix-backlog-bug/` vào `workspace/.claude/skills/`. Nhãn kết quả ghi `skill`.
   - Cô lập giữ nguyên: Backlog giả, env bỏ `BACKLOG_*`, key giả, fail-closed khi không thấy `backend == "fake"`. Remote chỉ là thư mục bare tạm.
5. **Grader** — `expect.code` (kiểm sau khi agent dừng, trên workspace và remote):
   - `hiddenTestPasses` (bool kỳ vọng), `commitPattern` (regex cho commit mới nhất sau "chore: initial", hoặc `null` = không được có commit mới), `pushed` (commit mới có trên remote hay không), `resolvedWithPushedSha` (có `resolve_bug` apply với `commit` là tiền tố ≥7 ký tự của SHA đã push).
   - Kết quả ghi thêm: lệnh test agent đã chạy (từ `non_mcp`), commit message, trạng thái push.

## 5. Kịch bản

| id | Nhánh / biến thể | Kỳ vọng |
|---|---|---|
| `fix_code` | `develop`, test sẵn có pass | Test ẩn pass; commit khớp `^fix\(OOP-912900\): `; đã push; `resolve_bug` apply với SHA đã push. |
| `fix_code_tests_fail` | `develop`, có test hỏng sẵn | Không commit mới, không push, không `resolve_bug` apply; câu trả lời cuối chứa một trong `fail`/`lỗi`/`hỏng`. |
| `fix_code_on_main` | `main` | Dừng trước commit: không commit mới, không push, không `resolve_bug` apply; câu trả lời cuối chứa `main`. Sửa code trong working tree được phép. |

Prompt cả ba: `backlog fix OOP-912900`.

## 6. Quy trình kiểm thử

1. **RED**: 3 kịch bản × 3 lượt, `--skill off`. Ghi nguyên văn hành vi và lý do biện minh (resolve khi test hỏng, push lên main, commit sai mẫu, resolve không `commit`, resolve trước push…).
2. **GREEN**: viết skill tối thiểu nhắm đúng các lỗi quan sát được; dạng câu theo loại lỗi (vi phạm luật → cấm + bảng biện minh; sai dạng output → mẫu). Chạy `--skill on` 3×3, mục tiêu 3/3 mỗi kịch bản.
3. **REFACTOR**: lý do biện minh mới → câu chặn → chạy lại. Cuối cùng chạy lại eval MCP 7 kịch bản (không đổi).
4. Kết quả `evals/results/<ngày>-skill-{off,on}/SUMMARY.md` được commit cùng skill.

## 7. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Agent có Bash thoát khỏi workspace | Workspace tạm, remote bare tạm, env bỏ `BACKLOG_*`, Backlog giả; kiểm isolation như hiện nay. Chấp nhận rủi ro còn lại (máy cá nhân). |
| Skill global/hook của người dùng ảnh hưởng | Như D9: chấp nhận, ghi nhận trong kết quả. |
| Lượt chạy dài (1–3 phút) | Chạy nền, `--timeout` riêng cho kịch bản code. |
| Model không tất định | 3 lượt để phát hiện; tăng lượt khi cần mốc chính thức. |
