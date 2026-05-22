# QA 출고준비 목록 — 선택 주문 이동·WMS 출고 등록 자동화

from typing import Any, Dict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import first_visible_locator
from Mate2QA_order_search import run_saved_search_on_page
from Mate2QA_order_step import (
    click_next_step_with_menu,
    dismiss_popup_ok,
    get_row_selection_counts,
)
from Mate2QA_site_config import LOGIN_URL, get_out_ready_list_url

WMS_OUT_DROPDOWN = "#wms_out_rgst"
WMS_OUT_MENU_CONSOLIDATION = 'a.sel-wms-out[data-out-reg-type="02"]'
WMS_OUT_CONFIRM_BTN = "#wmsOutRgstBtn"
MODAL_SCOPE = ".modal.show, .modal.in, [role='dialog']"

# 주문서처리 → 출고준비: 「다음 단계」 → #select_od_confirmed (선택 주문서확정)
OUT_READY_STEP_MENU = [
    "#select_od_confirmed",
    'a.dropdown-item:has-text("선택 주문서확정")',
    'a:has-text("선택 주문서확정")',
]


def goto_out_ready_list(page: Page, login_url: str | None = None) -> None:
    """출고준비 목록 화면으로 이동합니다."""
    target = get_out_ready_list_url(login_url or LOGIN_URL)
    page.goto(target, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 출고준비 목록으로 이동했습니다. 현재 URL: {page.url}")


def move_selected_orders_to_out_ready(page: Page) -> None:
    """
    주문서처리 목록에서 선택된 주문을
    「다음 단계」→ 「선택 주문서확정」(#select_od_confirmed)으로 이동합니다.
    (호출 전에 행이 선택되어 있어야 합니다.)
    """
    checked, _ = get_row_selection_counts(page)
    if checked == 0:
        raise ValueError(
            "출고준비로 이동할 선택 주문이 없습니다. 전체 선택 상태를 확인해 주세요."
        )

    print(f"[안내] 선택 {checked}건을 주문서확정(출고준비 단계)으로 이동합니다.")
    click_next_step_with_menu(
        page,
        OUT_READY_STEP_MENU,
        step_label="선택 주문서확정",
    )


def _get_wms_popup_scope(page: Page):
    """WMS 출고 등록 확인 팝업(모달) 범위를 반환합니다."""
    modal = page.locator(MODAL_SCOPE).filter(has=page.locator(WMS_OUT_CONFIRM_BTN))
    for i in range(modal.count()):
        m = modal.nth(i)
        if m.is_visible():
            return m
    return page


def _click_wms_out_dropdown_menu(page: Page) -> None:
    """WMS 출고 등록 → 선택 합포 기준 출고 메뉴를 클릭합니다."""
    btn = page.locator(WMS_OUT_DROPDOWN).first
    try:
        btn.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as e:
        raise ValueError(
            "「WMS 출고 등록」(#wms_out_rgst) 버튼을 찾지 못했습니다."
        ) from e
    btn.click()
    page.wait_for_timeout(400)

    menu = page.locator(WMS_OUT_MENU_CONSOLIDATION).first
    try:
        menu.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError as e:
        raise ValueError(
            "「선택 합포 기준 출고」 메뉴를 찾지 못했습니다. "
            "드롭다운이 열렸는지 확인해 주세요."
        ) from e
    menu.click()
    page.wait_for_timeout(800)
    print("[안내] 「선택 합포 기준 출고」 메뉴를 클릭했습니다.")


def _click_wms_out_register_in_popup(page: Page) -> None:
    """팝업에서 「WMS 출고 등록」(#wmsOutRgstBtn) 버튼을 클릭합니다."""
    scope = _get_wms_popup_scope(page)
    confirm = scope.locator(WMS_OUT_CONFIRM_BTN).first
    try:
        confirm.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as e:
        raise ValueError(
            "팝업의 「WMS 출고 등록」(#wmsOutRgstBtn) 버튼을 찾지 못했습니다."
        ) from e
    confirm.click()
    page.wait_for_timeout(800)
    print("[안내] 팝업에서 「WMS 출고 등록」 버튼을 클릭했습니다.")


def run_out_ready_wms_flow(page: Page, filter_data: Dict[str, Any]) -> None:
    """
    선택 주문 출고준비 이동 → 출고준비 목록 이동 → 저장 조건 검색
    → 전체 선택 → WMS 합포 기준 출고 등록까지 수행합니다.
    """
    print("[안내] 출고준비 이동·WMS 출고 등록 자동화를 시작합니다.")

    move_selected_orders_to_out_ready(page)
    goto_out_ready_list(page)

    run_saved_search_on_page(page, filter_data)
    _click_wms_out_dropdown_menu(page)
    _click_wms_out_register_in_popup(page)
    dismiss_popup_ok(page)

    print("[안내] 출고준비 WMS 출고 등록 자동화를 완료했습니다.")
