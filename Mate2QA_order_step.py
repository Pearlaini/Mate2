# #Mate2QA 공통 모듈 :  주문목록 — 다음 단계 → 선택 주문서처리로

from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import first_visible_locator
from Mate2QA_site_config import ORDER_LIST_URL, get_put_order_list_url

ROW_CHECKBOX = (
    '.tabulator-row input[type="checkbox"][aria-label="Select Row"], '
    '.tabulator-row input[type="checkbox"]'
)
NEXT_STEP_BTN = 'button:has-text("다음 단계")'
MENU_SELECT = "#select_od_confirm"

# 출고작업(outWkOrdList) 「전체 다음단계」 처리 실패 시 표시되는 alert 문구
OUT_WK_ORD_PROCESSING_ERROR = "처리중 오류가 발생하였습니다."

_abort_on_messages: tuple[str, ...] = ()


@contextmanager
def abort_popup_on_messages(*messages: str) -> Iterator[None]:
    """지정 문구가 포함된 SweetAlert가 뜨면 OK 클릭 후 예외를 발생시킵니다."""
    global _abort_on_messages
    old = _abort_on_messages
    _abort_on_messages = tuple(m for m in messages if m)
    try:
        yield
    finally:
        _abort_on_messages = old


def _read_swal_message(page: Page) -> str:
    """표시 중인 SweetAlert 본문 텍스트를 읽습니다."""
    popup = page.locator(".swal2-popup.swal2-show").first
    if popup.count() == 0:
        return ""
    for sel in ("#swal2-content", ".swal2-html-container", ".swal2-title"):
        loc = popup.locator(sel).first
        if loc.count() > 0:
            text = (loc.inner_text() or "").strip()
            if text:
                return text
    return (popup.inner_text() or "").strip()


def goto_put_order_list(page: Page, order_list_url: str | None = None) -> None:
    """단계 이동·팝업 처리가 끝난 뒤 주문서처리 목록 화면으로 이동합니다."""
    target = get_put_order_list_url(order_list_url or ORDER_LIST_URL)
    page.goto(target, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


def click_popup_ok_if_visible(
    page: Page,
    timeout_ms: int = 5000,
    *,
    abort_on_messages: tuple[str, ...] | None = None,
) -> bool:
    """SweetAlert 등 팝업이 보이면 OK(확인) 버튼을 클릭합니다."""
    popup = page.locator(".swal2-popup.swal2-show")
    try:
        popup.first.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return False

    message = _read_swal_message(page)
    tokens = abort_on_messages if abort_on_messages is not None else _abort_on_messages
    is_abort = bool(tokens and message and any(token in message for token in tokens))

    confirm_candidates = [
        "button.swal2-confirm.swal2-styled",
        'button.swal2-confirm:has-text("OK")',
        'button.swal2-confirm:has-text("확인")',
        'button:has-text("OK")',
        'button:has-text("확인")',
    ]
    clicked = False
    for sel in confirm_candidates:
        btn = popup.locator(sel).first
        if btn.count() > 0 and btn.is_visible():
            btn.click()
            page.wait_for_timeout(800)
            clicked = True
            break

    if is_abort:
        raise ValueError(
            "오류 alert가 표시되어 작업을 중단합니다. "
            f"메시지: {message}"
        )

    if not clicked:
        pass
    return clicked


def dismiss_popup_ok(page: Page, max_attempts: int = 3) -> None:
    """연속으로 뜨는 확인 팝업을 최대 max_attempts번까지 OK 처리합니다."""
    for attempt in range(1, max_attempts + 1):
        if not click_popup_ok_if_visible(page, 5000 if attempt == 1 else 3000):
            break


def get_row_selection_counts(page: Page) -> tuple[int, int]:
    """(선택 행 수, 전체 행 수)를 반환합니다."""
    rows = page.locator(ROW_CHECKBOX)
    total = rows.count()
    checked = 0
    for i in range(total):
        if rows.nth(i).is_checked():
            checked += 1
    return checked, total


def click_next_step_with_menu(
    page: Page,
    menu_candidates: list[str],
    *,
    step_label: str = "다음 단계 메뉴",
) -> None:
    """
    체크된 행이 1건 이상이면 「다음 단계」 드롭다운에서 지정 메뉴를 클릭합니다.
    """
    checked, total = get_row_selection_counts(page)

    if checked == 0:
        raise ValueError(
            "선택된 주문이 없습니다. 목록에서 행을 체크한 뒤 다시 시도해 주세요."
        )

    if total == 0:
        raise ValueError(
            "목록에 선택 가능한 행이 없습니다. 검색 조건·그리드 로딩을 확인해 주세요."
        )

    btn, sel = first_visible_locator(page, [NEXT_STEP_BTN])
    if not btn:
        raise ValueError("「다음 단계」 버튼을 찾지 못했습니다.")
    btn.click()
    page.wait_for_timeout(400)

    menu, menu_sel = first_visible_locator(page, menu_candidates)
    if not menu:
        raise ValueError(
            f"「{step_label}」 메뉴를 찾지 못했습니다. "
            "「다음 단계」 드롭다운 항목을 확인해 주세요."
        )

    menu.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)
    dismiss_popup_ok(page)
    page.wait_for_timeout(400)


def click_next_step_by_selection(page: Page) -> None:
    """
    체크된 행이 1건 이상이면 「다음 단계」→「선택 주문서처리로」를 클릭합니다.
    전체 선택·일부 선택 모두 동일 메뉴를 사용합니다.
    """
    click_next_step_with_menu(
        page,
        [MENU_SELECT],
        step_label="선택 주문서처리",
    )
