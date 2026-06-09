# QA 주문서처리 목록 — 선택 발송인 등록 자동화

from typing import Any, Dict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import first_visible_locator
from Mate2QA_order_search import click_select_all_orders, run_saved_search_on_page
from Mate2QA_order_step import dismiss_popup_ok

SENDER_DROPDOWN_BTN = 'button:has-text("발송인 등록")'
MENU_CHK_SENDER = "#chk_sender_rgst"
POPUP_SELECT_BTN = [
    "button.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1:has-text('선택')",
    "button.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1",
    ".tabulator-row .btn-info:has-text('선택')",
    'button.btn-xs.btn-info:has-text("선택")',
    'button:has-text("선택")',
    'a:has-text("선택")',
]
MODAL_SCOPE = ".modal.show, .modal.in, [role='dialog']"


def _get_visible_modal_scope(page: Page):
    """발송인 선택 팝업(모달)이 보이면 그 범위를, 없으면 page 전체를 반환합니다."""
    modal = page.locator(MODAL_SCOPE).filter(
        has=page.locator('button:has-text("선택")')
    )
    for i in range(modal.count()):
        m = modal.nth(i)
        if m.is_visible():
            return m
    return page


def _click_sender_dropdown_menu(page: Page) -> None:
    """발송인 등록 → 선택 발송인 등록 메뉴를 클릭합니다."""
    btn, sel = first_visible_locator(page, [SENDER_DROPDOWN_BTN])
    if not btn:
        raise ValueError("「발송인 등록」 버튼을 찾지 못했습니다.")
    btn.click()
    page.wait_for_timeout(400)

    menu = page.locator(MENU_CHK_SENDER).first
    try:
        menu.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError as e:
        raise ValueError(
            "「선택 발송인 등록」(#chk_sender_rgst) 메뉴가 보이지 않습니다. "
            "드롭다운이 열렸는지 확인해 주세요."
        ) from e
    menu.click()
    page.wait_for_timeout(800)


def _click_first_sender_select_in_popup(page: Page) -> None:
    """발송인 선택 팝업에서 첫 번째 「선택」 버튼을 클릭합니다."""
    scope = _get_visible_modal_scope(page)
    btn, sel = first_visible_locator(scope, POPUP_SELECT_BTN)
    if not btn:
        raise ValueError(
            "발송인 선택 팝업의 「선택」 버튼을 찾지 못했습니다. "
            "팝업·모달 로딩을 확인해 주세요."
        )
    btn.click()
    page.wait_for_timeout(800)


def register_sender_for_selected_orders(
    page: Page, filter_data: Dict[str, Any]
) -> None:
    """
    전체 선택 → 선택 발송인 등록 → 팝업 첫 「선택」 → OK
    → 저장 검색조건 재검색 → 전체 선택까지 수행합니다.
    """

    click_select_all_orders(page)
    _click_sender_dropdown_menu(page)
    _click_first_sender_select_in_popup(page)
    dismiss_popup_ok(page)

    run_saved_search_on_page(page, filter_data)

