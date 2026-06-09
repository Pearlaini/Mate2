# QA 화주별 재고 조회 — 로그인 후 새 탭에서 재고 목록 열기

from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
    needs_login,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)

CONFIG = {
    **_SITE_CONFIG,
}

STATE_FILE = STATE_FILE_DOMESTIC


def resolve_stock_list_url(config: Dict) -> str:
    """로그인 URL과 같은 호스트의 화주별 재고 목록 URL을 반환합니다."""
    url = (config.get("sach_stock_list_url") or "").strip()
    if not url:
        raise ValueError("sach_stock_list_url이 설정되지 않았습니다.")
    return url


def resolve_transfer_list_url(config: Dict) -> str:
    """로그인 URL과 같은 호스트의 재고이동내역 URL을 반환합니다."""
    url = (config.get("item_trnsf_list_url") or "").strip()
    if not url:
        raise ValueError("item_trnsf_list_url이 설정되지 않았습니다.")
    return url


def _assert_logged_in_page(page, config: Dict, *, label: str) -> None:
    """세션 만료(error.do) 화면이면 안내 메시지와 함께 예외를 발생시킵니다."""
    if needs_login(page, config["login_url"]):
        raise ValueError(
            f"{label} 접속 시 로그인 세션이 유효하지 않습니다. "
            f"현재 URL: {page.url}. "
            "메뉴 런처를 다시 실행해 로그인한 뒤 41번을 선택해 주세요."
        )


def open_stock_list_in_new_tab(context, config: Dict):
    """로그인 세션을 유지한 채 새 탭에서 화주별 재고 목록을 엽니다."""
    stock_url = resolve_stock_list_url(config)
    stock_page = context.new_page()
    stock_page.goto(stock_url, wait_until="domcontentloaded")
    stock_page.wait_for_timeout(1000)
    _assert_logged_in_page(stock_page, config, label="화주별 재고")

    try:
        stock_page.locator("#searchColumn2").wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError:
        print(
            "[경고] 검색 영역(#searchColumn2) 대기 시간이 초과되었습니다. "
            "화면을 직접 확인해 주세요."
        )

    return stock_page


def open_transfer_list_in_new_tab(context, config: Dict):
    """새 탭에서 재고이동내역 페이지를 엽니다."""
    transfer_url = resolve_transfer_list_url(config)
    transfer_page = context.new_page()
    transfer_page.goto(transfer_url, wait_until="domcontentloaded")
    transfer_page.wait_for_timeout(1000)
    _assert_logged_in_page(transfer_page, config, label="재고이동내역")

    try:
        transfer_page.locator("#searchColumn2").wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError:
        print(
            "[경고] 재고이동내역 검색 영역(#searchColumn2) 대기 시간이 초과되었습니다. "
            "화면을 직접 확인해 주세요."
        )

    return transfer_page


def ask_stock_search_keyword() -> str:
    """터미널에서 재고 검색어를 입력받습니다. 빈 값이면 검색을 건너뜁니다."""
    print(
        "\n재고 검색어를 입력해 주세요.\n"
        "  Enter만  → 검색조건·검색어 변경 없음(현행 유지)\n"
        "  P로 시작 → 상품코드(prod_cd)로 검색\n"
        "  그 외    → 업체 품목코드(item_cd)로 검색"
    )
    try:
        return input("검색어 입력: ").strip()
    except EOFError:
        return ""


def resolve_stock_search_column(keyword: str) -> str | None:
    """검색어에 따라 searchColumn2 option value를 결정합니다."""
    text = (keyword or "").strip()
    if not text:
        return None
    if text.upper().startswith("P"):
        return "prod_cd"
    return "item_cd"


def run_stock_search(stock_page, keyword: str) -> None:
    """화주별 재고 화면에서 검색조건·검색어를 설정하고 검색 버튼을 클릭합니다."""
    column = resolve_stock_search_column(keyword)
    if column is None:
        return

    stock_page.select_option("#searchColumn2", value=column)
    stock_page.wait_for_timeout(300)

    txt_loc = stock_page.locator('#search_txt, input[name="search_txt"]').first
    txt_loc.wait_for(state="visible", timeout=10_000)
    txt_loc.fill(keyword)

    search_btn_candidates = [
        "#searchBtn",
        'button#searchBtn',
        'button[name="searchBtn"]',
        'button:has-text("검색")',
    ]
    btn, _ = first_visible_locator(stock_page, search_btn_candidates)
    if not btn:
        raise ValueError("화주별 재고 화면에서 '검색' 버튼을 찾지 못했습니다.")

    btn.click()
    stock_page.wait_for_load_state("domcontentloaded")
    stock_page.wait_for_timeout(1000)


def run():
    """로그인 후 재고/재고이동내역 탭을 열고 같은 검색어로 조회합니다."""
    print_site_url_banner()
    config = refresh_config_from_env(CONFIG)
    creds = load_env_credentials(config["login_url"])

    with sync_playwright() as p:
        browser, context = create_context(p, config, state_file=STATE_FILE)
        page = context.new_page()

        try:
            config = ensure_login_only(
                page, context, config, creds, state_file=STATE_FILE
            )
            stock_page = open_stock_list_in_new_tab(context, config)
            keyword = ask_stock_search_keyword()
            run_stock_search(stock_page, keyword)
            transfer_page = open_transfer_list_in_new_tab(context, config)
            run_stock_search(transfer_page, keyword)

            try:
                input("재고/재고이동내역 화면 확인 후 종료하려면 Enter를 누르세요...")
            except EOFError:
                pass
        except PlaywrightTimeoutError:
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
