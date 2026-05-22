# QA 국내 주문목록 이동 — 로그인 확인 후 orderList.do 접속

from pathlib import Path
from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)

# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    "login_url": "https://qa-oms.ourbox.co.kr/om/login/login.do",
    "order_list_url": "https://qa-oms.ourbox.co.kr/om/order/order/orderList.do",
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

# 국내 수기등록 스크립트와 동일 QA 사이트 세션 공유
STATE_FILE = Path("storage_state_domestic.json")


def goto_order_list(page, config: Dict):
    """국내 주문목록 화면으로 이동합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 국내 주문목록으로 이동했습니다. 현재 URL: {page.url}")


def run():
    """로그인 상태를 확인한 뒤 국내 주문목록으로 이동합니다."""
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_order_list(page, CONFIG)
            try:
                input("브라우저를 종료하려면 Enter를 누르세요...")
            except EOFError:
                print("[안내] 표준 입력이 없어 Enter 대기를 건너뜁니다.")
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
