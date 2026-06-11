# =============================================================================
# ★ 사이트 주소 바꿀 때는 _DEFAULT_OMS_HOST를 수정하세요 ★
# =============================================================================

import os

from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from dotenv import load_dotenv

# Mate2QA 스크립트·설정 파일이 있는 프로젝트 루트 (실행 cwd와 무관)
PROJECT_DIR = Path(__file__).resolve().parent
_ENV_PATH = PROJECT_DIR / "Mate2QA_login.env"


def project_path(*parts: str) -> Path:
    """프로젝트 루트 기준 상대 경로를 절대 Path로 만듭니다."""
    return PROJECT_DIR.joinpath(*parts)


# 로컬 파일 (프로젝트 폴더 기준, cwd와 무관)
STATE_FILE_DOMESTIC = project_path("storage_state_domestic.json")
STATE_FILE_DEFAULT = project_path("storage_state.json")
SEARCH_FILTER_DOMESTIC_FILE = project_path("search_filter_domestic.json")
SEARCH_FILTER_WM_WAVE_FILE = project_path("search_filter_wm_wave.json")
DEFAULT_EXCEL_UPLOAD_FILE = project_path("샘플_입고요청.xlsx")


# =========================
# 로그인 페이지 URL만 바꾸면, 아래 경로가 같은 서버에 붙습니다.
# (또는 Mate2QA_login.env에 LOGIN_URL=... 설정)
# =========================

# env 미설정 시 사용 (호스트·scheme은 Mate2QA_login.env의 OMS_HOST 등으로 변경 가능)
_DEFAULT_OMS_SCHEME = "https"
_DEFAULT_OMS_HOST = "qa-oms.ourbox.co.kr"
LOGIN_PATH = "/om/login/login.do"


# 로그인 URL의 호스트(scheme://host) 뒤에 붙이는 경로

ORDER_LIST_PATH = "/om/order/order/orderList.do"
PUT_ORDER_LIST_PATH = "/om/order/putOrder/putOrderList.do"
OUT_READY_LIST_PATH = "/om/order/outReady/outReadyList.do"
ORDER_REGISTER_PATH = "/om/order/order/orderRgst.do"
OUT_EXPECT_LIST_PATH = "/wm/out/reg/outExpectList.do"
OUT_WAVE_LIST_PATH = "/wm/out/wave/outWaveList.do"
OUT_ALLOC_RGST_PATH = "/wm/out/alloc/outAllocRgst.do"
OUT_WK_ORD_LIST_PATH = "/wm/out/wk/ord/outWkOrdList.do"
WM_PUT_REQ_LIST_PATH = "/wm/put/req/reqList.do"
SACH_STOCK_LIST_PATH = "/wm/stock/sach/sachList.do"
ITEM_TRNSF_LIST_PATH = "/wm/stock/trnsf/itemTrnsfList.do"


def join_origin_path(login_url: str, path: str) -> str:

    """로그인 URL과 같은 호스트에 path를 이어 붙입니다. path는 / 로 시작."""

    parsed = urlparse(login_url)

    if not parsed.scheme or not parsed.netloc:

        raise ValueError(f"유효하지 않은 login_url: {login_url}")

    if not path.startswith("/"):

        path = "/" + path

    return f"{parsed.scheme}://{parsed.netloc}{path}"





def _resolve_login_url() -> str:

    load_dotenv(_ENV_PATH, override=True)

    load_dotenv(PROJECT_DIR / "Mate2QA_login.env", override=True)

    login = os.getenv("LOGIN_URL", "").strip()

    if login:

        return login

    # 하위 호환: 예전 ORDER_LIST_URL 전체 주소만 있으면 호스트만 추출

    order_full = os.getenv("ORDER_LIST_URL", "").strip()

    if order_full:

        parsed = urlparse(order_full)

        if parsed.scheme and parsed.netloc:

            return f"{parsed.scheme}://{parsed.netloc}/om/login/login.do"

    scheme = os.getenv("OMS_SCHEME", _DEFAULT_OMS_SCHEME).strip() or _DEFAULT_OMS_SCHEME
    host = os.getenv("OMS_HOST", _DEFAULT_OMS_HOST).strip() or _DEFAULT_OMS_HOST
    return f"{scheme}://{host}{LOGIN_PATH}"





def _resolve_urls() -> Tuple[str, str]:

    """(login_url, order_list_url)"""

    login_url = _resolve_login_url()

    order_list_url = join_origin_path(login_url, ORDER_LIST_PATH)

    return login_url, order_list_url





LOGIN_URL, ORDER_LIST_URL = _resolve_urls()





def get_put_order_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, PUT_ORDER_LIST_PATH)


def get_out_ready_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, OUT_READY_LIST_PATH)


def get_order_register_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, ORDER_REGISTER_PATH)


def get_out_expect_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, OUT_EXPECT_LIST_PATH)


def get_out_wave_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, OUT_WAVE_LIST_PATH)


def get_out_alloc_rgst_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, OUT_ALLOC_RGST_PATH)


def get_out_wk_ord_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, OUT_WK_ORD_LIST_PATH)


def get_wm_put_req_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, WM_PUT_REQ_LIST_PATH)


def get_sach_stock_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, SACH_STOCK_LIST_PATH)


def get_item_trnsf_list_url(login_url: str = LOGIN_URL) -> str:

    return join_origin_path(login_url, ITEM_TRNSF_LIST_PATH)


def build_playwright_config(login_url: Optional[str] = None) -> Dict:

    """Playwright·로그인 모듈에 넘길 CONFIG dict."""

    resolved_login = (login_url or _resolve_login_url()).strip()

    return {

        "login_url": resolved_login,

        "order_list_url": join_origin_path(resolved_login, ORDER_LIST_PATH),

        "put_order_list_url": get_put_order_list_url(resolved_login),

        "out_ready_list_url": get_out_ready_list_url(resolved_login),

        "order_register_url": get_order_register_url(resolved_login),

        "out_expect_list_url": get_out_expect_list_url(resolved_login),

        "out_wave_list_url": get_out_wave_list_url(resolved_login),

        "out_alloc_rgst_url": get_out_alloc_rgst_url(resolved_login),

        "out_wk_ord_list_url": get_out_wk_ord_list_url(resolved_login),

        "wm_put_req_list_url": get_wm_put_req_list_url(resolved_login),

        "sach_stock_list_url": get_sach_stock_list_url(resolved_login),

        "item_trnsf_list_url": get_item_trnsf_list_url(resolved_login),

        "excel_upload_file_path": (
            os.getenv("EXCEL_UPLOAD_FILE", "").strip()
            or str(DEFAULT_EXCEL_UPLOAD_FILE)
        ),

        "headless": False,

        "slow_mo": 150,

        "viewport_width": 1920,

        "viewport_height": 1080,

        # 브라우저 창: 최대화 + 페이지 줌(0.8 = 80%, 화면 잘림 완화)
        "start_maximized": True,

        "page_zoom": 0.8,

        # 주소/모달 팝업 구간만 1.0 (팝업 클릭·backdrop 오류 방지)
        "page_zoom_popup": 1.0,

        "selectors": {

            "login_id_input": 'input[name="user_id"]',

            "login_pw_input": 'input[name="user_pwd"]',

            "login_button": 'button:has-text("로그인")',

        },

    }





CONFIG = build_playwright_config()


def refresh_config_from_env(base: Optional[Dict] = None) -> Dict:
    """env 파일을 다시 읽어 login_url·하위 URL을 최신으로 맞춥니다."""
    src = base or CONFIG
    fresh = build_playwright_config()
    return {**src, **fresh}


CONFIG_FILE = Path(__file__).resolve()


def print_site_url_banner() -> None:
    """스크립트 시작 시 URL 배너 출력 (현재 비활성)."""
    pass


if __name__ == "__main__":
    print_site_url_banner()
