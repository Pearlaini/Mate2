# =============================================================================

# ★ 사이트 주소( QA / 다른 OMS ) 바꿀 때는 이 파일을 수정하세요 ★

#   파일 이름: Mate2QA_site_config.py  (또는 Mate2QA_URL설정안내.md 참고)

#   로그인 URL 기준으로 경로를 이어 붙여 주문·주문서처리 URL을 만듭니다.

# =============================================================================



import os

from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import urlparse
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / "Mate2QA_login.env"


# =========================
# 로그인 페이지 URL만 바꾸면, 아래 경로가 같은 서버에 붙습니다.
# (또는 Mate2QA_login.env에 LOGIN_URL=... 설정)
# =========================

_DEFAULT_LOGIN_URL = "https://qa-oms.ourbox.co.kr/om/login/login.do"


# 로그인 URL의 호스트(scheme://host) 뒤에 붙이는 경로

ORDER_LIST_PATH = "/om/order/order/orderList.do"
PUT_ORDER_LIST_PATH = "/om/order/putOrder/putOrderList.do"
OUT_READY_LIST_PATH = "/om/order/outReady/outReadyList.do"
ORDER_REGISTER_PATH = "/om/order/order/orderRgst.do"
STATE_FILE_DOMESTIC = Path("storage_state_domestic.json")


def join_origin_path(login_url: str, path: str) -> str:

    """로그인 URL과 같은 호스트에 path를 이어 붙입니다. path는 / 로 시작."""

    parsed = urlparse(login_url)

    if not parsed.scheme or not parsed.netloc:

        raise ValueError(f"유효하지 않은 login_url: {login_url}")

    if not path.startswith("/"):

        path = "/" + path

    return f"{parsed.scheme}://{parsed.netloc}{path}"





def _resolve_login_url() -> str:

    load_dotenv(_ENV_PATH)

    load_dotenv("Mate2QA_login.env")

    login = os.getenv("LOGIN_URL", "").strip()

    if login:

        return login

    # 하위 호환: 예전 ORDER_LIST_URL 전체 주소만 있으면 호스트만 추출

    order_full = os.getenv("ORDER_LIST_URL", "").strip()

    if order_full:

        parsed = urlparse(order_full)

        if parsed.scheme and parsed.netloc:

            return f"{parsed.scheme}://{parsed.netloc}/om/login/login.do"

    return _DEFAULT_LOGIN_URL





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





def build_playwright_config() -> Dict:

    """Playwright·로그인 모듈에 넘길 CONFIG dict."""

    return {

        "login_url": LOGIN_URL,

        "order_list_url": ORDER_LIST_URL,

        "put_order_list_url": get_put_order_list_url(),

        "out_ready_list_url": get_out_ready_list_url(),

        "order_register_url": get_order_register_url(),

        "headless": False,

        "slow_mo": 150,

        "viewport_width": 1920,

        "viewport_height": 1080,

        "selectors": {

            "login_id_input": 'input[name="loginId"]',

            "login_pw_input": 'input[name="password"]',

            "login_button": 'button:has-text("로그인")',

        },

    }





CONFIG = build_playwright_config()



CONFIG_FILE = Path(__file__).resolve()


def print_site_url_banner() -> None:
    """스크립트 시작 시 URL 설정 위치를 터미널에 안내합니다."""
    cfg = CONFIG
    print("=" * 62)
    print("[사이트 URL] 다른 사이트로 바꿀 때 수정하는 곳:")
    print(f"  ① {CONFIG_FILE.name}  →  _DEFAULT_LOGIN_URL (로그인, 약 21행)")
    print(f"  ② {CONFIG_FILE.name}  →  ORDER_LIST_PATH 등 경로 (약 24행~)")
    print("  ③ Mate2QA_login.env  →  LOGIN_URL=... (있으면 ①보다 우선)")
    print("  ④ 안내 문서: Mate2QA_URL설정안내.md")
    print(f"[현재] 로그인:     {cfg['login_url']}")
    print(f"[현재] 주문목록:   {cfg['order_list_url']}")
    print(f"[현재] 주문서처리: {cfg['put_order_list_url']}")
    print(f"[현재] 출고준비:   {cfg['out_ready_list_url']}")
    print("=" * 62)


if __name__ == "__main__":
    print_site_url_banner()
