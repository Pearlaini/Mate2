# QA 재고 조회 — 로그인 후 새 탭에서 로케이션조회·품목이동·재고조정요청 열기

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


def resolve_item_transfer_url(config: Dict) -> str:
    """로그인 URL과 같은 호스트의 품목 이동 URL을 반환합니다."""
    url = (config.get("item_trnsf_list_url") or "").strip()
    if not url:
        raise ValueError("item_trnsf_list_url이 설정되지 않았습니다.")
    return url


def resolve_stock_adjust_request_url(config: Dict) -> str:
    """로그인 URL과 같은 호스트의 재고조정요청 URL을 반환합니다."""
    url = (config.get("stock_adj_list_url") or "").strip()
    if not url:
        raise ValueError("stock_adj_list_url이 설정되지 않았습니다.")
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
        wait_stock_search_form_ready(stock_page)
    except PlaywrightTimeoutError:
        print(
            "[경고] 재고 검색 영역 대기 시간이 초과되었습니다. "
            "화면을 직접 확인해 주세요."
        )

    return stock_page


def open_item_transfer_in_new_tab(context, config: Dict):
    """새 탭에서 품목 이동 페이지를 엽니다."""
    trnsf_url = resolve_item_transfer_url(config)
    trnsf_page = context.new_page()
    trnsf_page.goto(trnsf_url, wait_until="domcontentloaded")
    trnsf_page.wait_for_timeout(1000)
    _assert_logged_in_page(trnsf_page, config, label="품목 이동")

    try:
        wait_stock_search_form_ready(trnsf_page)
    except PlaywrightTimeoutError:
        print(
            "[경고] 품목 이동 검색 영역 대기 시간이 초과되었습니다. "
            "화면을 직접 확인해 주세요."
        )

    return trnsf_page


def open_stock_adjust_request_in_new_tab(context, config: Dict):
    """새 탭에서 재고조정요청 페이지를 엽니다."""
    adjust_url = resolve_stock_adjust_request_url(config)
    adjust_page = context.new_page()
    adjust_page.goto(adjust_url, wait_until="domcontentloaded")
    adjust_page.wait_for_timeout(1000)
    _assert_logged_in_page(adjust_page, config, label="재고조정요청")

    try:
        wait_stock_search_form_ready(adjust_page)
    except PlaywrightTimeoutError:
        print(
            "[경고] 재고조정요청 검색 영역 대기 시간이 초과되었습니다. "
            "화면을 직접 확인해 주세요."
        )

    return adjust_page


def ask_stock_search_keyword() -> str:
    """터미널에서 재고 검색어를 입력받습니다. 빈 값이면 검색을 건너뜁니다."""
    print(
        "\n재고 검색어를 입력해 주세요. (로케이션조회·품목이동·재고조정요청 공통)\n"
        "  Enter만  → 검색조건·검색어 변경 없음(현행 유지)\n"
        "  P로 시작 → 상품코드(prod_cd)로 검색\n"
        "  그 외    → 업체 품목코드(item_cd)로 검색"
    )
    try:
        return input("검색어 입력: ").strip()
    except EOFError:
        return ""


def resolve_stock_search_column(keyword: str) -> str | None:
    """검색어에 따라 검색조건 option value를 결정합니다."""
    text = (keyword or "").strip()
    if not text:
        return None
    if text.upper().startswith("P"):
        return "prod_cd"
    return "item_cd"


def wait_stock_search_form_ready(page, timeout_ms: int = 15_000) -> None:
    """재고·품목이동·재고조정요청 화면의 검색조건 영역을 기다립니다."""
    page.locator(
        "#searchColumn2, #searchColumn, "
        'select[name="searchColumn2"], select[name="searchColumn"]'
    ).first.wait_for(state="visible", timeout=timeout_ms)


def run_stock_search(page, keyword: str) -> None:
    """재고 화면에서 검색조건·검색어를 설정하고 검색 버튼을 클릭합니다."""
    column = resolve_stock_search_column(keyword)
    if column is None:
        return

    col_loc, _ = first_visible_locator(
        page,
        [
            "#searchColumn2",
            "#searchColumn",
            'select[name="searchColumn2"]',
            'select[name="searchColumn"]',
        ],
    )
    if not col_loc:
        raise ValueError("재고 화면에서 검색조건 select를 찾지 못했습니다.")
    col_loc.select_option(value=column)
    page.wait_for_timeout(300)

    txt_loc, _ = first_visible_locator(
        page,
        [
            "#search_txt",
            'input[name="search_txt"]',
            "#srch_txt",
            'input[name="srch_txt"]',
        ],
    )
    if not txt_loc:
        raise ValueError("재고 화면에서 검색어 입력란을 찾지 못했습니다.")
    txt_loc.wait_for(state="visible", timeout=10_000)
    txt_loc.fill(keyword)

    search_btn_candidates = [
        "#searchBtn",
        'button#searchBtn',
        'button[name="searchBtn"]',
        'button:has-text("검색")',
    ]
    btn, _ = first_visible_locator(page, search_btn_candidates)
    if not btn:
        raise ValueError("재고 화면에서 '검색' 버튼을 찾지 못했습니다.")

    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)


def run_task(page, context, config, *, keep_browser: bool = False):
    """로케이션조회·품목이동·재고조정요청 탭을 열고 같은 검색어로 조회합니다."""
    from Mate2QA_browser_session import MSG_STOCK_KEEP_BROWSER, wait_enter_after_task

    stock_page = open_stock_list_in_new_tab(context, config)
    keyword = ask_stock_search_keyword()
    run_stock_search(stock_page, keyword)
    trnsf_page = open_item_transfer_in_new_tab(context, config)
    run_stock_search(trnsf_page, keyword)
    adjust_page = open_stock_adjust_request_in_new_tab(context, config)
    run_stock_search(adjust_page, keyword)

    stock_tabs = (stock_page, trnsf_page, adjust_page)
    for tab in stock_tabs:
        try:
            tab.bring_to_front()
        except Exception:
            pass
    try:
        adjust_page.bring_to_front()
    except Exception:
        pass

    wait_enter_after_task(
        keep_browser=keep_browser,
        message=MSG_STOCK_KEEP_BROWSER if keep_browser else None,
    )
    if keep_browser:
        return stock_tabs
    return None


def run():
    """로그인 후 재고 조회 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
