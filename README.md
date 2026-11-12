# dictionary-scraper-api · Từ điển Supabase

FastAPI tra từ trong bảng **`public.dictionary` trên Supabase**, rồi trả dữ liệu cho giao diện tra từ hiện có. Endpoint vẫn là `/api/dictionary?word=...`. Không còn đọc file JSONL, tạo chỉ mục RAM lúc khởi động hoặc gọi Gemini/scraping làm fallback.

## Cấu hình và chạy local

Dùng Python **3.12**:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Tạo `.env` từ `.env.example` **nếu chưa có `.env`**; nếu đã có, chỉ thêm các biến dưới đây. Điền thông tin project của bạn trực tiếp trong file local, không gửi key vào cuộc trò chuyện hoặc commit `.env`:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-publishable-key
SUPABASE_TIMEOUT_SECONDS=10
# Chỉ cần khi frontend khác origin; không có dấu / cuối origin.
CORS_ORIGINS=http://localhost:3000
```

`SUPABASE_URL` là HTTPS origin của project, không kèm `/rest/v1`, path hay query. Lấy URL và publishable key trong Dashboard Supabase. Backend gửi key bằng header `apikey`, không gửi publishable key như một Bearer JWT. Key chỉ được đọc trên server, không nhúng vào frontend, response hay log ứng dụng. Xem [hướng dẫn Data API](https://supabase.com/docs/guides/api/quickstart) và [header của API key mới](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys).

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell: tạo venv bằng `py -3.12 -m venv .venv`, dùng `.\.venv\Scripts\python.exe` với các lệnh `-m pip`/`-m uvicorn` ở trên. Production chỉ cần `requirements.txt`; HTTPX2 nay là dependency runtime để gọi Supabase async.

Mở [trang thử](http://127.0.0.1:8000/), [Swagger](http://127.0.0.1:8000/docs) hoặc [health](http://127.0.0.1:8000/api/health). Restart server sau khi đổi biến môi trường. Các biến `GEMINI_*` cũ không được sử dụng.

## Bảng và quyền truy cập

Ứng dụng dùng đúng bảng/cột đã có:

```text
public.dictionary
  id text primary key
  word text not null
  lookup_key text not null       -- đã có index dictionary_lookup_key_idx
  pos text not null
  pos_title text not null
  data jsonb not null
  source text not null
```

Data API cần được bật và expose schema `public`. Với publishable key và không có phiên đăng nhập, truy vấn dùng role `anon`: role này cần quyền **SELECT** và, nếu bật RLS, một policy SELECT cho phép đọc các dòng từ điển. Không cần cấp quyền ghi. App không dùng service-role/secret key, không tự tạo bảng, import dữ liệu, thay grant hoặc policy. Tham khảo [quyền truy cập và RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

**RLS có thể trả `[]` với HTTP 200 khi các dòng bị ẩn.** App không thể phân biệt trường hợp đó với từ không tồn tại và sẽ trả `WORD_NOT_FOUND`. Nếu từ chắc chắn có trong bảng nhưng API không thấy, kiểm tra grant/policy SELECT cho `anon` và giá trị `lookup_key`. Health không xác minh các quyền này.

## Cách tra và ánh xạ dữ liệu

1. Chuẩn hóa chữ hoa/thường, khoảng trắng, dấu nháy cong và Unicode như trước. Ví dụ ` LOOK   UP ` → `look up`, `IT’S` → `it's`.
2. Gọi async `GET {SUPABASE_URL}/rest/v1/dictionary`, chọn `id,word,lookup_key,pos,pos_title,data,source`, lọc **`lookup_key=eq.<từ chuẩn hóa>`**, sắp xếp `id.asc`. Không tìm substring hoặc tự sửa chính tả.
3. Đọc nhiều dòng theo loại từ. Mỗi trang tối đa 100 dòng; `Prefer: count=exact` và `Content-Range` xác định cần lấy trang tiếp theo, kể cả khi server đặt giới hạn thấp hơn. Không tải toàn bộ bảng; count chỉ áp dụng cho từ đang lọc. Xem [phân trang PostgREST](https://docs.postgrest.org/en/stable/references/api/pagination_count.html).
4. Validate các cột và `data` trước khi ánh xạ sang response Pydantic. Cột `word`, `pos`, `pos_title` của bảng là thông tin đầu mục chính, ưu tiên hơn trường cùng tên trong JSONB. Dòng sai khóa/ngôn ngữ, bị lặp ID hoặc thiếu toàn bộ nghĩa trả lỗi thay vì thành công rỗng.

**`data` được kỳ vọng chứa object Wiktionary gốc đã lưu từ JSONL trước đây**, với `sounds[]`, `senses[]`; không phải chuỗi JSON hoặc một response `entries[]` đã render. Ví dụ rút gọn cấu trúc của cột này:

```json
{
  "lang_code": "en",
  "sounds": [{"ipa": "/ˈbjuːtɪ.fəl/", "tags": ["UK"]}],
  "senses": [{
    "glosses": ["Đẹp; hay."],
    "examples": [{"text": "A beautiful garden.", "translation": "Một khu vườn đẹp."}]
  }]
}
```

`lookup_key` trong bảng cần được chuẩn hóa cùng quy tắc với app. Bảng chỉ chứa dữ liệu tiếng Anh cho luồng tra này; nếu JSONB có `lang_code` thì giá trị phải là `en`.

| Dữ liệu nguồn | API/UI |
| --- | --- |
| Cột `word`, `pos`, `pos_title` | Từ đầu mục và nhóm loại từ |
| Cột `source` | `entries[].source`, giữ tên nguồn mỗi dòng |
| `data.sounds[].ipa`, `tags`, `raw_tags` | Phiên âm và nhãn có sẵn, không đoán UK/US |
| `data.sounds[].mp3_url`, `ogg_url`, `wav_url` | Nút nghe; ưu tiên MP3, sau đó OGG/WAV |
| `data.senses[].glosses` | Các cấp giải nghĩa theo thứ tự nguồn |
| `data.senses[].examples[].text`, `translation`, `ref` | Ví dụ, bản dịch, tham chiếu thuộc đúng nghĩa |
| `data.senses[].tags`, `raw_tags`, `topics` | Nhãn cách dùng và chủ đề |

Giữ giao diện, bộ lọc loại từ và các ví dụ hiện có. Không tạo thêm nghĩa, bản dịch, IPA, CEFR hay URL âm thanh. Chỉ URL HTTPS hợp lệ trên `upload.wikimedia.org`/`commons.wikimedia.org` được đưa vào nút nghe; trình duyệt chỉ tải âm thanh khi bấm. Một số mục có thể thiếu ví dụ/IPA/audio. Không cắt số nghĩa hoặc ví dụ ở backend.

Mỗi lookup có deadline tổng mặc định **10 giây**, cấu hình `SUPABASE_TIMEOUT_SECONDS` từ 1–30 giây. Có connection pool theo process, không retry hoặc đi theo redirect. Chặn tải quá 1.000 dòng hoặc 8 MiB cho một từ bằng lỗi rõ ràng, không trả kết quả bị cắt. Không có cache lâu dài hoặc giới hạn request toàn cục trong RAM. Thay dữ liệu Supabase không cần đóng gói file/redeploy; thay cấu hình/code cần restart/redeploy.

## API và lỗi

```bash
curl -i http://127.0.0.1:8000/api/health
curl -i --get http://127.0.0.1:8000/api/dictionary --data-urlencode 'word=beautiful'
```

Health chỉ kiểm tra sự hiện diện của cấu hình, **không gọi Supabase**, không đếm bảng, không khẳng định kết nối/key/quyền đã hợp lệ:

```json
{"status":"ok","provider":"supabase","configured":true}
```

Thiếu cấu hình vẫn mở được UI/docs/health (`configured=false`); lookup trả 503. HTTP 200 của lookup gồm `word`, `normalized_word`, `headword`, `status="found"`, `provider="supabase"`, `source="public.dictionary"` và `entries[]` theo schema UI cũ, thêm `entries[].source`. Không còn metadata file cục bộ. Lookup dùng `Cache-Control: no-store`.

Lỗi trả `{code, message, retryable}`. `retryable=true` chỉ cho biết người dùng có thể thử lại; app và frontend **không tự retry**.

| HTTP | Code | Ý nghĩa |
| --- | --- | --- |
| 400/422 | `INVALID_INPUT` | Query sai/thiếu, quá giới hạn 120 ký tự hoặc 12 từ sau chuẩn hóa |
| 404 | `WORD_NOT_FOUND` | Không có dòng đọc được khớp khóa; cũng có thể do RLS ẩn dữ liệu |
| 503 | `SUPABASE_NOT_CONFIGURED` | Thiếu URL hoặc publishable key |
| 503 | `SUPABASE_AUTH_ERROR` | Supabase trả 401, kiểm tra key |
| 503 | `SUPABASE_PERMISSION_DENIED` | Supabase trả 403, kiểm tra grant/RLS |
| 503 | `SUPABASE_REQUEST_REJECTED` | Truy vấn/schema/bảng/cột hoặc Data API không phù hợp; upstream 404 không bị hiểu là từ không tồn tại |
| 429 | `SUPABASE_RATE_LIMIT` | Supabase giới hạn lưu lượng |
| 504 | `SUPABASE_TIMEOUT` | Hết deadline hoặc timeout kết nối/đọc |
| 502 | `SUPABASE_UNAVAILABLE` | Lỗi kết nối hoặc dịch vụ upstream |
| 502 | `SUPABASE_INVALID_RESPONSE` | Phản hồi không phải mảng JSON/phân trang không nhất quán |
| 502 | `DICTIONARY_INVALID` | Dòng/JSONB không đúng cấu trúc hoặc không có nghĩa |
| 502 | `DICTIONARY_TOO_LARGE` | Vượt giới hạn tải một mục từ |
| 500 | `INTERNAL_ERROR` | Lỗi ứng dụng |

Server chỉ log mã lỗi và HTTP status upstream, không log key, headers, raw body hoặc chuỗi exception upstream. Frontend tiếp tục chỉ gọi endpoint nội bộ khi submit, chặn submit trùng khi tải và render bằng `textContent`.

## Vercel

Giữ `main.py:app`, Python 3.12 và `maxDuration: 40`. Đã bỏ `includeFiles` của JSONL khỏi `vercel.json`; không cần bundle/upload dataset nữa. Kết nối HTTP tạo trong lifespan và đóng khi kết thúc, không truy cập database lúc import/startup/health.

Trong **Vercel → Project Settings → Environment Variables**, thêm:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_TIMEOUT_SECONDS` (tùy chọn, mặc định 10)
- `CORS_ORIGINS` nếu frontend khác origin.

Chọn đúng environment Production/Preview/Development cần dùng, rồi **redeploy**. Kiểm tra `/api/health` và tra một từ đã biết có trong bảng. `configured=true` chưa chứng minh quyền đọc; cần lookup thành công. Không cần các biến Gemini cũ. Chưa publish/deploy hay thay tài nguyên trong tài khoản của bạn.

## Kiểm thử

```bash
python -m pytest -q
python -m pip check
```

Test thường cấm socket connect thật và dùng HTTPX2 MockTransport mô phỏng Supabase: truy vấn/headers, nhiều loại từ, phân trang dưới giới hạn server, schema, nghĩa/ví dụ/audio, timeout, lỗi quyền/key/rate limit/dịch vụ, key redaction, health không gọi DB và đóng HTTP client. Không phụ thuộc file JSONL đã xóa hoặc gọi Supabase thật. Kết quả và phần chưa xác minh: [docs/VALIDATION.md](docs/VALIDATION.md).
