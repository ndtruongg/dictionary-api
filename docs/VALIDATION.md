# Kiểm tra bản Supabase — 12/11/2026

## Phạm vi thay đổi

- Chuyển nguồn lookup từ file JSONL đã xóa sang Supabase Data API, bảng `public.dictionary`.
- Giữ endpoint `/api/dictionary?word=...`, chuẩn hóa đầu vào, mapper nghĩa/ví dụ/IPA/audio và toàn bộ giao diện hiện có. Không sửa các file `app/static/`.
- Backend đọc `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`; timeout tổng mặc định 10 giây. Key chỉ dùng trong header `apikey`, không dùng Bearer JWT, frontend hoặc log.
- Bỏ chỉ mục byte offset/file handle, các test phụ thuộc JSONL và `includeFiles` dataset trong Vercel. Chuyển HTTPX2 từ dependency dev sang runtime cho lời gọi async.

## Đã xác minh offline

- Python 3.12, `.venv/bin/python -m pytest -q`: **101 passed**.
- `.venv/bin/python -m pip check`: **No broken requirements found**.
- Compile Python thành công; `vercel.json` parse hợp lệ, không còn phụ thuộc file JSONL.
- Test thường chặn socket connect thật; dữ liệu tổng hợp và HTTPX2 MockTransport, không gọi tài khoản Supabase.
- Truy vấn đúng `/rest/v1/dictionary`, `Accept-Profile: public`, `lookup_key=eq.<khóa chuẩn hóa>`, cột chọn cố định và thứ tự `id.asc`; key nằm trong header, không nằm trong query/response/log.
- Đủ nhiều loại từ, đúng quan hệ nghĩa/ví dụ, giữ gloss hierarchy, nhãn/IPA và các clip audio hợp lệ. Cột metadata của bảng ưu tiên hơn dữ liệu cùng tên trong JSONB.
- Phân trang vẫn lấy đủ dòng khi server chỉ trả một dòng/trang; dùng exact count và kiểm tra `Content-Range`, không trả thành công với kết quả bị cắt/ID trùng/khóa không khớp.
- Không tìm thấy, JSON sai, JSONB không đúng cấu trúc, thiếu nghĩa, vượt giới hạn dòng/bytes đều trả mã lỗi riêng.
- Mock HTTP 401/403/400/404/406/416/429/500/503/redirect và lỗi kết nối/read timeout/connect timeout/deadline được ánh xạ, không retry, không theo redirect. Body/exception giả có chứa key không bị đưa vào lỗi trả client hoặc log ứng dụng.
- Test API xác nhận chuẩn hóa chữ hoa, khoảng trắng, dấu nháy; từ/cụm từ; chặn query không hợp lệ trước khi truy vấn; schema OpenAPI, CORS, lỗi upstream và `Cache-Control: no-store`.
- Startup, health, UI/static/docs không gọi Supabase. Client HTTP đóng khi kết thúc lifespan; các lookup async đồng thời không lẫn dữ liệu từ.
- Smoke ASGI với **HTTP client production thật**, cấu hình trống và socket network bị chặn: `/` trả **200**, `/api/health` trả **200** với `configured=false`, lookup trả **503 SUPABASE_NOT_CONFIGURED**. Không có request mạng.

## Chưa xác minh

- Khi kiểm tra chỉ in boolean hiện diện của biến môi trường: cả `SUPABASE_URL` và `SUPABASE_PUBLISHABLE_KEY` đều chưa được cấu hình. Không sửa `.env`, không yêu cầu gửi key, không thực hiện lookup Supabase thật.
- Chưa kiểm chứng shape thực tế của cột JSONB `data`; mapper kỳ vọng object Wiktionary gốc (`sounds[]`, `senses[]`) từ dataset trước đây. Fixture mô phỏng cấu trúc đó, không thay thế xác minh một dòng trong bảng thật.
- Chưa xác minh Data API, grants/RLS, index execution plan, latency hoặc quyền đọc của project. Publishable key không có phiên đăng nhập dùng role `anon`; RLS có thể ẩn toàn bộ dòng và trả `[]` như từ không tồn tại.
- Chưa phát lại âm thanh trong browser với dữ liệu Supabase thật; logic audio/UI được giữ nguyên, mapper được kiểm tra offline.
- Chưa deploy Vercel hoặc thay tài nguyên, grant/policy trong tài khoản. Cần thêm hai biến Supabase trong đúng Vercel Environment Variables rồi redeploy, tra một từ đã biết có trong bảng. `health.configured=true` chỉ báo đủ cấu hình, không xác minh kết nối/quyền.

## Tài liệu đã đối chiếu

- [Supabase Data API quickstart](https://supabase.com/docs/guides/api/quickstart): route REST và header `apikey`.
- [API key migration](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys): không dùng publishable key như Bearer JWT.
- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security): quyền đọc bằng publishable key phụ thuộc grant/policy.
- [PostgREST pagination/count](https://docs.postgrest.org/en/stable/references/api/pagination_count.html): `limit`, `offset`, `count=exact`, `Content-Range`.
