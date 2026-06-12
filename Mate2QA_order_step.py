# #Mate2QA 공통 모듈 :  주문목록 — 다음 단계 → 선택 주문서처리로

import time
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

# 출고작업(outWkOrdList) 「전체 다음단계」 등 처리 실패 alert 감지 문구 (부분 일치)
OUT_WK_ORD_PROCESSING_ERROR = "처리중 오류"

MSG_OUT_WK_ORD_PROCESSING_ABORT = (
    "처리중 오류 alert — 출고작업 후속 단계를 중단하고 메뉴로 돌아갑니다."
)

_abort_on_messages: tuple[str, ...] = ()


class OutWkOrdProcessingError(Exception):
    """출고작업 화면에서 처리중 오류 alert가 표시되었습니다."""

    def __init__(self, alert_message: str = "") -> None:
        self.alert_message = (alert_message or "").strip()
        super().__init__(self.alert_message)


def print_out_wk_ord_processing_error(
    exc: OutWkOrdProcessingError | None = None,
) -> None:
    """처리중 오류 alert로 작업이 중단되었음을 안내합니다."""
    print(f"[경고] {MSG_OUT_WK_ORD_PROCESSING_ABORT}", flush=True)
    if exc and exc.alert_message:
        print(f"       alert: {exc.alert_message}", flush=True)


def get_abort_popup_messages() -> tuple[str, ...]:
    """abort_popup_on_messages 컨텍스트에 등록된 감지 문구를 반환합니다."""
    return _abort_on_messages


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


def _normalize_alert_text(text: str) -> str:
    """alert 비교용 — 공백·줄바꿈을 제거합니다."""
    return "".join((text or "").split())


def _message_matches_tokens(message: str, tokens: tuple[str, ...]) -> bool:
    """지정 문구가 alert 본문에 포함되는지 확인합니다 (공백 무시 부분 일치)."""
    if not message or not tokens:
        return False
    norm_message = _normalize_alert_text(message)
    for token in tokens:
        if not token:
            continue
        if token in message or _normalize_alert_text(token) in norm_message:
            return True
    return False


def _probe_visible_popup(page: Page) -> dict:
    """화면에 보이는 SweetAlert·모달 팝업을 조사합니다."""
    return page.evaluate(
        """() => {
            const selectors = [
                '.swal2-popup.swal2-show',
                '.swal2-container.swal2-shown .swal2-popup',
                '.modal.show',
                '.modal.in',
                '[role="dialog"]',
            ];
            const confirmSelectors = [
                'button.swal2-confirm.swal2-styled',
                'button.swal2-confirm',
                'button.btn-primary',
                'button.close',
            ];

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const roots = [];
            const seen = new Set();
            for (const sel of selectors) {
                for (const el of document.querySelectorAll(sel)) {
                    if (!isVisible(el) || seen.has(el)) continue;
                    seen.add(el);
                    roots.push(el);
                }
            }

            for (const root of roots) {
                const text = (root.innerText || '').trim();
                if (!text) continue;

                let confirmSelector = '';
                for (const sel of confirmSelectors) {
                    const btn = Array.from(root.querySelectorAll(sel)).find(isVisible);
                    if (btn) {
                        confirmSelector = sel;
                        break;
                    }
                }
                if (!confirmSelector) {
                    const btn = Array.from(root.querySelectorAll('button, a.btn'))
                        .find((el) => {
                            if (!isVisible(el)) return false;
                            const label = (el.innerText || '').trim();
                            return label === 'OK' || label === '확인';
                        });
                    if (btn) confirmSelector = 'button';
                }

                return {
                    found: true,
                    text,
                    hasConfirm: !!confirmSelector,
                    confirmSelector,
                };
            }
            return { found: false, text: '', hasConfirm: false, confirmSelector: '' };
        }"""
    )


def _click_visible_popup_confirm(
    page: Page, probe: dict, *, settle_ms: int = 300
) -> bool:
    """조사된 팝업에서 확인 버튼을 클릭합니다."""
    if not probe.get("hasConfirm"):
        return False
    clicked = page.evaluate(
        """() => {
            const selectors = [
                '.swal2-popup.swal2-show',
                '.swal2-container.swal2-shown .swal2-popup',
                '.modal.show',
                '.modal.in',
                '[role="dialog"]',
            ];
            const confirmSelectors = [
                'button.swal2-confirm.swal2-styled',
                'button.swal2-confirm',
                'button.btn-primary',
                'button.close',
            ];

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const roots = [];
            const seen = new Set();
            for (const sel of selectors) {
                for (const el of document.querySelectorAll(sel)) {
                    if (!isVisible(el) || seen.has(el)) continue;
                    seen.add(el);
                    roots.push(el);
                }
            }

            for (const root of roots) {
                for (const sel of confirmSelectors) {
                    const btn = Array.from(root.querySelectorAll(sel)).find(isVisible);
                    if (btn) {
                        btn.click();
                        return true;
                    }
                }
                const btn = Array.from(root.querySelectorAll('button, a.btn'))
                    .find((el) => {
                        if (!isVisible(el)) return false;
                        const label = (el.innerText || '').trim();
                        return label === 'OK' || label === '확인';
                    });
                if (btn) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }"""
    )
    if clicked:
        page.wait_for_timeout(settle_ms)
    return bool(clicked)


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
    settle_ms: int = 300,
    poll_ms: int = 150,
) -> bool:
    """SweetAlert·모달 팝업이 보이면 OK(확인) 버튼을 클릭합니다."""
    tokens = abort_on_messages if abort_on_messages is not None else _abort_on_messages
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        probe = _probe_visible_popup(page)
        if not probe.get("found"):
            page.wait_for_timeout(poll_ms)
            continue

        message = str(probe.get("text") or "").strip()
        is_abort = _message_matches_tokens(message, tokens)
        clicked = _click_visible_popup_confirm(page, probe, settle_ms=settle_ms)

        if is_abort:
            raise OutWkOrdProcessingError(message)

        if clicked:
            return True

        if message:
            return False

        page.wait_for_timeout(poll_ms)

    return False


def wait_out_wk_ord_popups_after_next_step(
    page: Page,
    *,
    max_wait_ms: int = 25_000,
) -> None:
    """출고작업 「전체 다음단계」 클릭 후 alert를 폴링합니다. 처리중 오류 시 즉시 중단."""
    deadline = time.monotonic() + max_wait_ms / 1000
    dismissed = 0
    idle_rounds = 0

    while time.monotonic() < deadline:
        try:
            clicked = click_popup_ok_if_visible(page, timeout_ms=600)
        except OutWkOrdProcessingError:
            raise

        if clicked:
            dismissed += 1
            idle_rounds = 0
            if dismissed >= 3:
                return
            continue

        idle_rounds += 1
        if dismissed > 0 and idle_rounds >= 3:
            return
        page.wait_for_timeout(400)


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
