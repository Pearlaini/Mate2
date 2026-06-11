# QA WMS 출고보류 — 로그인 후 출고예정 목록에서 출고보류 조회·해제

from datetime import datetime
from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
)
from Mate2QA_order_search import click_select_all_orders, wait_search_grid
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)

# 출고예정 목록 URL
DEFAULT_OUT_EXPECT_LIST_URL = (
    "https://qa-style.ourbox.co.kr/wm/out/reg/outExpectList.do"
)
# 출고상태: 출고보류
OUT_STATE_HOLD = "99"
# 검색조건: 쇼핑몰 주문번호 / 검색어
SEARCH_COLUMN_MALL_OD_NO = "mall_od_no"
DEFAULT_SEARCH_TEXT = "J"

CONFIG = {
    **_SITE_CONFIG,
    "out_expect_list_url": DEFAULT_OUT_EXPECT_LIST_URL,
}

STATE_FILE = STATE_FILE_DOMESTIC

# 출고예정 검색 폼 — #out_state는 select·hidden input 중복 id 주의
OUT_STATE_SELECT = 'select#out_state, select[name="out_state"]'
SEARCH_BTN_CANDIDATES = [
    "#searchForm button#searchBtn.btn-info.btn-sm:has-text('검색')",
    "#searchForm button#searchBtn.btn-info:has-text('검색')",
    "#searchForm button#searchBtn:has-text('검색')",
    "button#searchBtn.btn-info.btn-sm:has-text('검색')",
    "button#searchBtn.btn-info:has-text('검색')",
    "button#searchBtn:has-text('검색')",
    "#searchForm #searchBtn",
    "#searchBtn",
]


def resolve_out_expect_list_url(config: Dict) -> str:
    """출고예정 목록 URL을 반환합니다."""
    return (
        (config.get("out_expect_list_url") or "").strip()
        or DEFAULT_OUT_EXPECT_LIST_URL
    )


def goto_out_expect_list(page, config: Dict) -> None:
    """WMS 출고예정 목록 화면으로 이동합니다."""
    target_url = resolve_out_expect_list_url(config)
    page.goto(target_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    page.locator(OUT_STATE_SELECT).first.wait_for(state="visible", timeout=15_000)
    page.locator("#searchForm").first.wait_for(state="visible", timeout=15_000)


def fill_search_column_and_text(page, *, column_value: str, search_text: str) -> None:
    """검색조건(searchColumn)과 검색어(srch_txt)를 입력합니다."""
    col_sel = page.locator('select#searchColumn, select[name="searchColumn"]').first
    col_sel.wait_for(state="visible", timeout=10_000)
    col_sel.select_option(value=column_value)
    col_sel.evaluate(
        "(el) => el.dispatchEvent(new Event('change', { bubbles: true }))"
    )
    page.wait_for_timeout(200)

    txt_sel = page.locator('#srch_txt, input[name="srch_txt"]').first
    txt_sel.wait_for(state="visible", timeout=10_000)
    txt_sel.fill(search_text)
    page.wait_for_timeout(200)


def select_out_state_hold(page) -> None:
    """출고상태(out_state)를 출고보류(99)로 선택합니다."""
    state_sel = page.locator(OUT_STATE_SELECT).first
    state_sel.wait_for(state="visible", timeout=10_000)
    state_sel.select_option(value=OUT_STATE_HOLD)
    state_sel.evaluate(
        """(el) => {
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    page.wait_for_timeout(300)


def click_search_button(page) -> None:
    """출고예정 목록 「검색」 버튼을 클릭합니다."""
    btn, btn_sel = first_visible_locator(page, SEARCH_BTN_CANDIDATES)
    if not btn:
        raise ValueError("출고예정 목록에서 '검색' 버튼을 찾지 못했습니다.")

    btn.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    try:
        btn.click(timeout=10_000)
    except PlaywrightTimeoutError:
        # 줌 80% 등으로 일반 click이 막히면 JS 클릭으로 재시도
        btn.evaluate("(el) => el.click()")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)


def click_select_all_hold_rows(page) -> None:
    """검색 결과 그리드 헤더 체크박스로 전체 선택합니다."""
    wait_search_grid(page)
    click_select_all_orders(page)


def click_hold_release_dropdown(page) -> None:
    """「선택 삭제 / 보류해제」 드롭다운 버튼을 클릭합니다."""
    toggle_candidates = [
        'button.dropdown-toggle:has-text("선택 삭제")',
        'button.dropdown-toggle:has-text("보류해제")',
        "button.bg-danger.dropdown-toggle",
        'button.dropdown-toggle.bg-danger',
    ]
    toggle, toggle_sel = first_visible_locator(page, toggle_candidates)
    if not toggle:
        raise ValueError(
            "「선택 삭제 / 보류해제」 드롭다운 버튼을 찾지 못했습니다."
        )

    toggle.scroll_into_view_if_needed()
    toggle.click()
    page.wait_for_timeout(400)


def click_hold_release_menu_item(page) -> None:
    """서브메뉴 「출고보류 해제」(#selHoldCancelBtn)를 클릭합니다."""
    menu_candidates = [
        "#selHoldCancelBtn",
        'button#selHoldCancelBtn',
        'button.dropdown-item:has-text("출고보류 해제")',
        '.dropdown-item:has-text("출고보류 해제")',
    ]
    menu, menu_sel = first_visible_locator(page, menu_candidates)
    if not menu:
        raise ValueError("서브메뉴 「출고보류 해제」 버튼을 찾지 못했습니다.")

    menu.click()
    page.wait_for_timeout(800)


def make_hold_release_reason() -> str:
    """보류해제 사유 문자열을 생성합니다. (YYYYMMDD HHMM 보류해제)"""
    return f"{datetime.now().strftime('%Y%m%d %H%M')} 보류해제"


def fill_hold_release_reason(page, reason: str | None = None) -> str:
    """보류해제 팝업의 사유 입력란(out_unhold_resn)에 텍스트를 넣습니다."""
    text = (reason or make_hold_release_reason()).strip()
    reason_loc = page.locator(
        '#out_unhold_resn, textarea[name="out_unhold_resn"]'
    ).first
    reason_loc.wait_for(state="visible", timeout=15_000)
    reason_loc.fill(text)
    page.wait_for_timeout(300)
    return text


def run_hold_release_after_search(page) -> None:
    """검색 후 전체 선택 → 보류해제 메뉴 → 사유 입력까지 수행합니다."""
    click_select_all_hold_rows(page)
    click_hold_release_dropdown(page)
    click_hold_release_menu_item(page)
    fill_hold_release_reason(page)


def run():
    """로그인 → 출고예정 검색 → 전체 선택 → 출고보류 해제 사유 입력."""
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
            goto_out_expect_list(page, config)
            fill_search_column_and_text(
                page,
                column_value=SEARCH_COLUMN_MALL_OD_NO,
                search_text=DEFAULT_SEARCH_TEXT,
            )
            select_out_state_hold(page)
            click_search_button(page)
            run_hold_release_after_search(page)

            try:
                input(
                    "저장 후 Enter를 누르시면 팝업창이 닫힙니다."
                )
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
