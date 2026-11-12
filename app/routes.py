from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse

from app.dictionary import SupabaseDictionary
from app.schemas import DictionaryResult, ErrorResponse, HealthResponse, ILLUSTRATIVE_RESULT
from app.validation import normalize_word

router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_dictionary(request: Request) -> SupabaseDictionary:
    return request.app.state.dictionary


@router.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health(dictionary: SupabaseDictionary = Depends(get_dictionary)):
    """Chỉ báo cấu hình; không gọi Supabase hoặc đếm dữ liệu."""
    return HealthResponse(configured=dictionary.settings.configured)


@router.get(
    "/api/dictionary", response_model=DictionaryResult, tags=["Dictionary"],
    responses={
        200: {"description": "Các mục khớp lookup_key trong public.dictionary; giữ riêng từng loại từ và ví dụ theo nghĩa.",
              "content": {"application/json": {"examples": {"illustrative_only": {
                  "summary": "Ví dụ rút gọn cấu trúc kết quả, không phải toàn bộ mục từ",
                  "value": ILLUSTRATIVE_RESULT}}}}},
        **{status: {"model": ErrorResponse, "description": description} for status, description in {
            400: "Đầu vào không hợp lệ", 404: "Không có trong từ điển", 422: "Thiếu/sai query parameter",
            429: "Supabase giới hạn lưu lượng", 500: "Lỗi ứng dụng",
            502: "Lỗi dịch vụ hoặc dữ liệu Supabase", 503: "Thiếu cấu hình hoặc quyền truy cập Supabase",
            504: "Hết thời gian chờ Supabase"}.items()},
    },
)
async def dictionary(
    response: Response,
    word: str = Query(..., max_length=512, description="Từ/cụm từ tiếng Anh; ví dụ beautiful, bank, mother-in-law.", examples=["beautiful"]),
    source: SupabaseDictionary = Depends(get_dictionary),
):
    response.headers["Cache-Control"] = "no-store"
    return await source.lookup(normalize_word(word))
