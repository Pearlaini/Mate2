# Mate2QA — WMS 출고작업 출고확정 탭 항목설정 JSON 저장·적용 (런처 7번 서브 371·372)
#
# 실행: python -m item_settings.Mate2QA_setItemBtnOutConfirm

import time
from typing import Any, Dict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_browser_session import wait_enter_after_task
from Mate2QA_login import first_visible_locator
from item_settings.Mate2QA_setItemBtn import (
    CONFIG as _BASE_CONFIG,
    _split_settings_sections,
    apply_settings_from_json,
    build_settings_payload,
    capture_item_settings_from_popup,
    click_save_success_alert_ok,
    load_item_settings,
    save_item_settings,
    verify_popup_matches_json,
    wait_item_settings_boards_ready,
)
from Mate2QA_shipper_select import select_shipper_on_page
from Mate2QA_site_config import (
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    refresh_config_from_env,
)
from Mate2QA_wm_wave_search import (
    click_out_confirm_tab,
    ensure_out_wk_ord_row_selected,
)

SETTINGS_FILE_OUTCONFIRM = PROJECT_DIR / "grid_item_settings_outconfirm.json"
SCREEN_NAME = "출고확정"
ACTION_SAVE = "save"
ACTION_APPLY = "apply"

CONFIG = {
    **_BASE_CONFIG,
    "item_settings_file": SETTINGS_FILE_OUTCONFIRM.name,
    "outconfirm_item_action": ACTION_SAVE,
}

STATE_FILE = STATE_FILE_DOMESTIC
PAGE_READY_OUT_WK_ORD = ["#srch_gubun", "#searchBtn", "#grid-table"]
OUT_CONFIRM_TAB_PANEL = "#tab_borders_icons-8"
OUT_CONFIRM_SET_ITEM_BTN_CANDIDATES = [
    f"{OUT_CONFIRM_TAB_PANEL} #setItemBtn",
    f'{OUT_CONFIRM_TAB_PANEL} button#setItemBtn[data-code="08"]',
]
OUT_CONFIRM_SET_ITEM_POP = "#outSetItemModal"


def is_outconfirm_item_settings_popup_visible(page: Page) -> bool:
    """출고확정 항목설정 팝업 표시 여부."""
    pop = page.locator(OUT_CONFIRM_SET_ITEM_POP).first
    try:
        return pop.count() > 0 and pop.is_visible()
    except Exception:
        return False


def wait_outconfirm_item_settings_popup_ready(page: Page) -> None:
    """출고확정 항목설정 팝업과 보드 로딩을 기다립니다."""
    page.locator(OUT_CONFIRM_SET_ITEM_POP).wait_for(state="visible", timeout=15_000)
    wait_item_settings_boards_ready(page)


def wait_outconfirm_item_settings_popup_closed(
    page: Page, timeout_ms: int = 15_000
) -> None:
    """출고확정 항목설정 팝업이 닫힐 때까지 대기합니다."""
    try:
        page.locator(OUT_CONFIRM_SET_ITEM_POP).first.wait_for(
            state="hidden", timeout=timeout_ms
        )
    except PlaywrightTimeoutError:
        pass


def install_outconfirm_item_settings_save_listener(page: Page) -> None:
    """출고확정 팝업이 열려 있을 때 [저장] 클릭 감지 리스너를 설치합니다."""
    if is_outconfirm_item_settings_popup_visible(page):
        _install_outconfirm_user_save_listener(page)


def _install_outconfirm_user_save_listener(page: Page) -> None:
    """사용자가 출고확정 [저장] 버튼을 누를 때 팝업 상태를 즉시 스냅샷합니다."""
    page.evaluate(
        """() => {
            window.__outConfirmSetItemUserSaved = false;
            window.__outConfirmSetItemCapturedData = null;

            const snapshotBoards = () => {
                const readBoard = (boardId) => {
                    const board = document.getElementById(boardId);
                    if (!board) return [];
                    return [...board.querySelectorAll('.col-lg-12')].map((el, idx) => {
                        const sno = el.querySelector('input[name="grid_itm_sno"]');
                        const expsr = el.querySelector('input[name="expsr_yn"]');
                        const width = el.querySelector('input[name="itm_width"]');
                        const label = el.querySelector('.move-tag strong');
                        return {
                            order: idx + 1,
                            grid_itm_sno: sno ? sno.value : '',
                            label: label ? label.textContent.trim() : '',
                            expsr_yn: expsr ? expsr.value : '',
                            width: width ? Number(width.value) : null,
                        };
                    });
                };
                return {
                    unused: readBoard('leftBoard'),
                    used: readBoard('rightBoard'),
                };
            };

            const onSaveIntent = () => {
                window.__outConfirmSetItemCapturedData = snapshotBoards();
                window.__outConfirmSetItemUserSaved = true;
            };

            const pop = document.getElementById('outSetItemModal');
            if (!pop) return;
            for (const btn of pop.querySelectorAll('button')) {
                const text = (btn.textContent || '').replace(/\\s+/g, '');
                if (!text.includes('저장')) continue;
                btn.addEventListener('mousedown', onSaveIntent, { capture: true });
                btn.addEventListener('click', onSaveIntent, { capture: true });
            }
        }"""
    )


def _outconfirm_user_clicked_save(page: Page) -> bool:
    return bool(page.evaluate("() => !!window.__outConfirmSetItemUserSaved"))


def _pull_outconfirm_user_saved_capture(
    page: Page, *, config: Dict | None = None
) -> Dict[str, Any] | None:
    """저장 클릭 직전 JS 스냅샷을 JSON payload로 변환합니다."""
    raw = page.evaluate(
        """() => {
            const d = window.__outConfirmSetItemCapturedData;
            if (!d) return null;
            return d;
        }"""
    )
    if not raw:
        return None
    return build_settings_payload(
        page, raw.get("unused") or [], raw.get("used") or [], config=config
    )


def _wait_for_outconfirm_user_save_click(
    page: Page, timeout_ms: int = 600_000
) -> None:
    """열린 출고확정 팝업에서 사용자 [저장] 클릭을 대기합니다."""
    pop = page.locator(OUT_CONFIRM_SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("출고확정 항목설정 팝업이 열려 있지 않습니다.")

    _install_outconfirm_user_save_listener(page)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _outconfirm_user_clicked_save(page):
            return
        if not pop.is_visible():
            raise ValueError(
                "출고확정 항목설정 팝업이 닫혔지만 [저장]이 눌리지 않았습니다. "
                "다시 371번으로 실행해 주세요."
            )
        page.wait_for_timeout(200)
    raise TimeoutError(
        "저장 대기 시간이 초과되었습니다. [저장] 버튼을 눌러 주세요."
    )


def _complete_outconfirm_save_after_user_click(
    page: Page, *, screen_name: str = ""
) -> None:
    """사용자 [저장] 후 alert OK·출고확정 팝업 닫힘까지 처리합니다."""
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        prefix = f"{screen_name}: " if screen_name else ""
        print(f"[경고] {prefix}저장 alert OK 버튼을 찾지 못했습니다.", flush=True)
    wait_outconfirm_item_settings_popup_closed(page, timeout_ms=10_000)
    page.wait_for_timeout(300)


def click_save_in_outconfirm_item_settings_popup(page: Page) -> None:
    """출고확정 항목설정 팝업에서 저장 버튼을 클릭합니다."""
    pop = page.locator(OUT_CONFIRM_SET_ITEM_POP).first
    if pop.count() == 0 or not pop.is_visible():
        raise ValueError("출고확정 항목설정 팝업이 열려 있지 않습니다.")

    save_btn = pop.locator(
        'button[onclick*="insUpdItemRgst"], button:has-text("저장")'
    ).first
    try:
        save_btn.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as exc:
        raise ValueError("출고확정 항목설정 팝업의 저장 버튼을 찾지 못했습니다.") from exc

    save_btn.scroll_into_view_if_needed()
    try:
        save_btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        save_btn.click(force=True)


def wait_for_outconfirm_user_to_click_save(
    page: Page, timeout_ms: int = 600_000, *, config: Dict | None = None
) -> Dict[str, Any]:
    """사용자가 [저장]을 누를 때까지 대기하고, 저장 직전 팝업 설정을 읽습니다."""
    pop = page.locator(OUT_CONFIRM_SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("출고확정 항목설정 팝업이 열려 있지 않습니다.")

    install_outconfirm_item_settings_save_listener(page)
    _wait_for_outconfirm_user_save_click(page, timeout_ms=timeout_ms)

    captured = _pull_outconfirm_user_saved_capture(page, config=config)
    if captured is None and pop.is_visible():
        captured = capture_item_settings_from_popup(page, config=config)

    if captured is None:
        raise ValueError(
            "저장 직후 출고확정 항목설정을 읽지 못했습니다. "
            "다시 371번 항목설정을 실행해 주세요."
        )

    _complete_outconfirm_save_after_user_click(page, screen_name=SCREEN_NAME)
    return captured


def wait_out_confirm_screen_ready(page: Page, timeout_ms: int = 30_000) -> None:
    """출고확정 탭의 항목설정 버튼이 보일 때까지 대기합니다."""
    btn, _sel = first_visible_locator(page, OUT_CONFIRM_SET_ITEM_BTN_CANDIDATES)
    if btn is None:
        loc = page.locator(OUT_CONFIRM_SET_ITEM_BTN_CANDIDATES[0])
        loc.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(500)


def open_out_confirm_item_settings_popup(page: Page) -> None:
    """출고확정 탭 전용 항목설정 버튼을 클릭하고 팝업을 엽니다."""
    if is_outconfirm_item_settings_popup_visible(page):
        wait_outconfirm_item_settings_popup_ready(page)
        return

    btn, _sel = first_visible_locator(page, OUT_CONFIRM_SET_ITEM_BTN_CANDIDATES)
    if btn is None:
        raise ValueError(
            "출고확정 탭 항목설정 버튼을 찾지 못했습니다. "
            "출고확정 탭이 열려 있는지 확인해 주세요."
        )
    btn.scroll_into_view_if_needed()
    try:
        btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        btn.click(force=True)

    page.wait_for_timeout(400)
    if not is_outconfirm_item_settings_popup_visible(page):
        btn.evaluate("el => el.click()")
        page.wait_for_timeout(400)

    if not is_outconfirm_item_settings_popup_visible(page):
        raise PlaywrightTimeoutError(
            f"{OUT_CONFIRM_SET_ITEM_POP} 팝업이 열리지 않았습니다."
        )

    wait_outconfirm_item_settings_popup_ready(page)


def goto_out_confirm_tab(page: Page, config: Dict) -> None:
    """출고작업 화면 → 출고차수 선택 → 출고확정 탭으로 이동합니다."""
    url = (config.get("out_wk_ord_list_url") or "").strip()
    if not url:
        raise ValueError("out_wk_ord_list_url이 설정되지 않았습니다.")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    select_shipper_on_page(
        page, config, page_ready_selectors=PAGE_READY_OUT_WK_ORD
    )
    ensure_out_wk_ord_row_selected(page)
    click_out_confirm_tab(page)


def run_save_outconfirm(page: Page, config: Dict) -> None:
    """출고확정 탭의 현재 항목설정을 JSON으로 저장합니다."""
    goto_out_confirm_tab(page, config)
    wait_out_confirm_screen_ready(page)
    open_out_confirm_item_settings_popup(page)
    print(
        f"[안내] {SCREEN_NAME} 팝업에서 원하는 대로 수정한 뒤 [저장] 버튼을 눌러 주세요.",
        flush=True,
    )
    captured = wait_for_outconfirm_user_to_click_save(page, config=config)
    captured["screen"] = "out_wk_ord_confirm"
    path = save_item_settings(captured, config=config)
    print(f"[완료] {SCREEN_NAME} 항목설정 JSON 저장: {path}", flush=True)


def run_apply_outconfirm(page: Page, config: Dict, *, keep_browser: bool = True) -> None:
    """JSON에 저장된 출고확정 항목설정을 화면에 반영·저장합니다."""
    settings = load_item_settings(config=config)
    if not settings:
        raise FileNotFoundError(
            f"설정 파일이 없습니다: {SETTINGS_FILE_OUTCONFIRM}\n"
            "먼저 371번으로 JSON을 저장해 주세요."
        )

    unused, used = _split_settings_sections(settings)
    if not used and not unused:
        raise ValueError("JSON에 미사용·사용 항목이 없습니다.")

    goto_out_confirm_tab(page, config)
    wait_out_confirm_screen_ready(page)
    open_out_confirm_item_settings_popup(page)
    missing = apply_settings_from_json(page, settings, screen_name=SCREEN_NAME)
    snapshot = capture_item_settings_from_popup(page, config=config)
    try:
        verify_popup_matches_json(
            settings, snapshot, missing, screen_name=SCREEN_NAME
        )
    except ValueError as exc:
        print(f"[경고] {exc}", flush=True)
        wait_for_outconfirm_user_to_click_save(page, config=config)
        print(f"[완료] {SCREEN_NAME} 항목설정 수동 저장 완료", flush=True)
        return

    click_save_in_outconfirm_item_settings_popup(page)
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        print(
            f"[경고] {SCREEN_NAME} 저장 alert OK를 찾지 못했습니다.",
            flush=True,
        )
    wait_outconfirm_item_settings_popup_closed(page)
    print(f"[완료] {SCREEN_NAME} 항목설정 JSON 적용·저장", flush=True)


def run_task(page, context, config=None, *, keep_browser: bool = False):
    """371(save) 또는 372(apply) 항목설정 작업을 실행합니다."""
    cfg = refresh_config_from_env(config or CONFIG)
    action = (cfg.get("outconfirm_item_action") or ACTION_SAVE).strip().lower()

    if action == ACTION_APPLY:
        run_apply_outconfirm(page, cfg, keep_browser=keep_browser)
    else:
        run_save_outconfirm(page, cfg)

    if keep_browser:
        return cfg

    message = (
        f"{SCREEN_NAME} JSON 적용 후 Enter를 누르세요."
        if action == ACTION_APPLY
        else f"{SCREEN_NAME} JSON 저장 후 Enter를 누르세요."
    )
    wait_enter_after_task(keep_browser=False, message=message)
    return cfg


def run():
    """단독 실행: 저장(기본) 후 종료."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
