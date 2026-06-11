# QA 국내 주문목록 — 로그인·검색·선택·단계 이동(선택 주문서처리)
# QA 주문발주관리 → 주문서처리 → 출고준비 → 발송준비까지 선택 주문서 이동
# 주문서처리: 발송인 등록 → 출고준비 이동 → WMS 합포 기준 출고 등록
#
# 사이트 URL 변경: Mate2QA_site_config.py 의 _DEFAULT_LOGIN_URL (또는 .env LOGIN_URL)

from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_order_search import (
    run_saved_search_on_page,
    save_search_criteria_from_page,
)
from Mate2QA_order_step import click_next_step_by_selection, goto_put_order_list
from Mate2QA_out_ready import run_out_ready_wms_flow
from Mate2QA_sender import register_sender_for_selected_orders
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner, refresh_config_from_env

STATE_FILE = STATE_FILE_DOMESTIC


def goto_order_list(page, config: Dict):
    """국내 주문목록 화면으로 이동합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


def run_task(page, context, config, *, keep_browser: bool = False):
    """주문 이동·발송인 등록 → 출고준비 WMS 출고 등록까지 자동화."""
    from Mate2QA_browser_session import wait_enter_after_task

    goto_order_list(page, config)

    try:
        input("준비되면 Enter...")
    except EOFError:
        pass

    filter_data = save_search_criteria_from_page(page)
    click_next_step_by_selection(page)
    goto_put_order_list(page)

    # 2) 주문서처리 목록: 저장 검색 조건 조회 → 선택 발송인 등록 → 재검색·전체 선택
    run_saved_search_on_page(page, filter_data)
    register_sender_for_selected_orders(page, filter_data)
    run_out_ready_wms_flow(page, filter_data)

    wait_enter_after_task(
        keep_browser=keep_browser,
        message=(
            "OK 확인 후 Enter를 누르세요."
            if keep_browser
            else "OK 확인 후 Enter를 누르시면 팝업창이 닫힙니다."
        ),
    )


def run():
    """로그인 → 주문 이동·발송인 등록 → 출고준비 WMS 출고 등록까지 자동화 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
