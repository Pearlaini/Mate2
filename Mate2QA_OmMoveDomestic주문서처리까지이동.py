# QA 국내 주문목록 — 로그인·검색·선택·단계 이동(선택 주문서처리)
# QA 주문발주관리 → 주문서처리 → 출고준비 → 발송준비까지 선택 주문서 이동
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
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner

STATE_FILE = STATE_FILE_DOMESTIC


def goto_order_list(page, config: Dict):
    """국내 주문목록 화면으로 이동합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 국내 주문목록으로 이동했습니다. 현재 URL: {page.url}")


def run():
    """로그인 → 주문목록 검색·선택·이동 → putOrderList에서 저장 조건으로 재검색합니다."""
    print_site_url_banner()
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_order_list(page, CONFIG)

            print(
                "[안내] 주문목록: 검색 6개 설정 → 「검색」 → "
                "이동할 주문 체크까지 모두 끝낸 뒤 Enter..."
            )
            try:
                input("준비되면 Enter...")
            except EOFError:
                print("[안내] 표준 입력 없음 — 현재 화면 기준으로 진행합니다.")

            filter_data = save_search_criteria_from_page(page)
            click_next_step_by_selection(page)
            goto_put_order_list(page)

            # 2) 주문서처리 목록: 1단계와 동일 검색 조건 입력 후 검색 버튼 자동 클릭
            run_saved_search_on_page(page, filter_data)

            try:
                input(
                    "이동한 주문이 목록에 보이는지 확인한 뒤, 종료하려면 Enter..."
                )
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
