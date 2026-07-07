# Mate2QA — WMS 출고통합관리 항목설정 JSON 저장·적용 (런처 7번 서브 391·392)
#
# 391: 11번 m/ㅡ(통합관리 JSON 저장)과 동일 흐름 → grid_item_settings_outall.json
# 실행: python -m item_settings.Mate2QA_setItemBtnOutall

import time
from typing import Any, Dict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_browser_session import wait_enter_after_task
from item_settings.Mate2QA_setItemBtn import (
    CONFIG as _BASE_CONFIG,
    _split_settings_sections,
    apply_settings_from_json,
    build_settings_payload,
    capture_item_settings_from_popup,
    click_save_success_alert_ok,
    load_item_settings,
    merge_remember_payload_with_existing,
    save_item_settings,
    verify_popup_matches_json,
    wait_item_settings_boards_ready,
    wait_screen_ready,
)
from Mate2QA_shipper_select import select_shipper_on_page
from Mate2QA_site_config import (
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    refresh_config_from_env,
)

SETTINGS_FILE_OUTALL = PROJECT_DIR / "grid_item_settings_outall.json"
SCREEN_NAME = "출고통합관리"
ACTION_SAVE = "save"
ACTION_APPLY = "apply"

CONFIG = {
    **_BASE_CONFIG,
    "item_settings_file": SETTINGS_FILE_OUTALL.name,
    "outall_item_action": ACTION_SAVE,
}

STATE_FILE = STATE_FILE_DOMESTIC
PAGE_READY_OUTALL = ["#setItemBtn", 'button:has-text("항목설정")']
OUTALL_SET_ITEM_POP = "#outSetItemModal"


def is_outall_item_settings_popup_visible(page: Page) -> bool:
    """출고통합관리 항목설정 팝업 표시 여부."""
    pop = page.locator(OUTALL_SET_ITEM_POP).first
    try:
        return pop.count() > 0 and pop.is_visible()
    except Exception:
        return False


def wait_outall_item_settings_popup_ready(page: Page) -> None:
    """출고통합관리 항목설정 팝업과 보드 로딩을 기다립니다."""
    page.locator(OUTALL_SET_ITEM_POP).wait_for(state="visible", timeout=15_000)
    wait_item_settings_boards_ready(page)


def close_outall_item_settings_popup(page: Page) -> None:
    """출고통합관리 항목설정 팝업을 닫습니다."""
    pop = page.locator(OUTALL_SET_ITEM_POP).first
    if pop.count() == 0 or not pop.is_visible():
        return

    close_btn = pop.locator(
        'button[data-dismiss="modal"], button:has-text("닫기")'
    ).last
    close_btn.click()
    page.wait_for_timeout(300)


def wait_outall_item_settings_popup_closed(
    page: Page, timeout_ms: int = 15_000
) -> None:
    """출고통합관리 항목설정 팝업이 닫힐 때까지 대기합니다."""
    try:
        page.locator(OUTALL_SET_ITEM_POP).first.wait_for(
            state="hidden", timeout=timeout_ms
        )
    except PlaywrightTimeoutError:
        pass


def install_outall_item_settings_save_listener(page: Page) -> None:
    """출고통합관리 팝업이 열려 있을 때 [저장] 클릭 감지 리스너를 설치합니다."""
    if is_outall_item_settings_popup_visible(page):
        _install_outall_user_save_listener(page)


def _install_outall_user_save_listener(page: Page) -> None:
    """사용자가 출고통합관리 [저장] 버튼을 누를 때 팝업 상태를 즉시 스냅샷합니다."""
    page.evaluate(
        """() => {
            window.__outAllSetItemUserSaved = false;
            window.__outAllSetItemCapturedData = null;

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
                window.__outAllSetItemCapturedData = snapshotBoards();
                window.__outAllSetItemUserSaved = true;
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


def _outall_user_clicked_save(page: Page) -> bool:
    return bool(page.evaluate("() => !!window.__outAllSetItemUserSaved"))


def _pull_outall_user_saved_capture(
    page: Page, *, config: Dict | None = None
) -> Dict[str, Any] | None:
    """저장 클릭 직전 JS 스냅샷을 JSON payload로 변환합니다."""
    raw = page.evaluate(
        """() => {
            const d = window.__outAllSetItemCapturedData;
            if (!d) return null;
            return d;
        }"""
    )
    if not raw:
        return None
    return build_settings_payload(
        page, raw.get("unused") or [], raw.get("used") or [], config=config
    )


def _wait_for_outall_user_save_click(
    page: Page, timeout_ms: int = 600_000
) -> None:
    """열린 출고통합관리 팝업에서 사용자 [저장] 클릭을 대기합니다."""
    pop = page.locator(OUTALL_SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("출고통합관리 항목설정 팝업이 열려 있지 않습니다.")

    _install_outall_user_save_listener(page)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _outall_user_clicked_save(page):
            return
        if not pop.is_visible():
            raise ValueError(
                "출고통합관리 항목설정 팝업이 닫혔지만 [저장]이 눌리지 않았습니다. "
                "다시 391번으로 실행해 주세요."
            )
        page.wait_for_timeout(200)
    raise TimeoutError(
        "저장 대기 시간이 초과되었습니다. [저장] 버튼을 눌러 주세요."
    )


def _complete_outall_save_after_user_click(
    page: Page, *, screen_name: str = ""
) -> None:
    """사용자 [저장] 후 alert OK·출고통합관리 팝업 닫힘까지 처리합니다."""
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        prefix = f"{screen_name}: " if screen_name else ""
        print(f"[경고] {prefix}저장 alert OK 버튼을 찾지 못했습니다.", flush=True)
    wait_outall_item_settings_popup_closed(page, timeout_ms=10_000)
    page.wait_for_timeout(300)


def click_save_in_outall_item_settings_popup(page: Page) -> None:
    """출고통합관리 항목설정 팝업에서 저장 버튼을 클릭합니다."""
    pop = page.locator(OUTALL_SET_ITEM_POP).first
    if pop.count() == 0 or not pop.is_visible():
        raise ValueError("출고통합관리 항목설정 팝업이 열려 있지 않습니다.")

    save_btn = pop.locator(
        'button[onclick*="insUpdItemRgst"], button:has-text("저장")'
    ).first
    try:
        save_btn.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as exc:
        raise ValueError("출고통합관리 항목설정 팝업의 저장 버튼을 찾지 못했습니다.") from exc

    save_btn.scroll_into_view_if_needed()
    try:
        save_btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        save_btn.click(force=True)


def wait_for_outall_user_to_click_save(
    page: Page, timeout_ms: int = 600_000, *, config: Dict | None = None
) -> Dict[str, Any]:
    """사용자가 [저장]을 누를 때까지 대기하고, 저장 직전 팝업 설정을 읽습니다."""
    pop = page.locator(OUTALL_SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("출고통합관리 항목설정 팝업이 열려 있지 않습니다.")

    install_outall_item_settings_save_listener(page)
    _wait_for_outall_user_save_click(page, timeout_ms=timeout_ms)

    captured = _pull_outall_user_saved_capture(page, config=config)
    if captured is None and pop.is_visible():
        captured = capture_item_settings_from_popup(page, config=config)

    if captured is None:
        raise ValueError(
            "저장 직후 출고통합관리 항목설정을 읽지 못했습니다. "
            "다시 391번 항목설정을 실행해 주세요."
        )

    _complete_outall_save_after_user_click(page, screen_name=SCREEN_NAME)
    return captured


def open_outall_item_settings_popup(page: Page) -> None:
    """출고통합관리 항목설정 버튼을 눌러 팝업을 엽니다."""
    if is_outall_item_settings_popup_visible(page):
        wait_outall_item_settings_popup_ready(page)
        return

    btn = page.locator('button#setItemBtn:has-text("항목설정"), #setItemBtn').first
    btn.wait_for(state="visible", timeout=30_000)
    btn.scroll_into_view_if_needed()

    try:
        btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        btn.click(force=True)

    page.wait_for_timeout(500)
    if not is_outall_item_settings_popup_visible(page):
        clicked = page.evaluate(
            """() => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                };
                const buttons = [
                    ...document.querySelectorAll('button#setItemBtn'),
                    ...document.querySelectorAll('button')
                ];
                const btn = buttons.find((el) =>
                    isVisible(el)
                    && (el.id === 'setItemBtn'
                        || (el.textContent || '').includes('항목설정'))
                );
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if not clicked:
            raise ValueError("출고통합관리 항목설정 버튼을 찾지 못했습니다.")

    wait_outall_item_settings_popup_ready(page)


def goto_out_all_list(page: Page, config: Dict) -> None:
    """출고통합관리 화면으로 이동합니다(11번 m/ㅡ의 goto_remember_list와 동일 역할)."""
    url = (config.get("out_all_list_url") or "").strip()
    if not url:
        raise ValueError("out_all_list_url이 설정되지 않았습니다.")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    select_shipper_on_page(
        page, config, page_ready_selectors=PAGE_READY_OUTALL
    )
    wait_screen_ready(page)


def remember_outall_settings_after_user_save(
    page: Page, *, config: Dict | None = None
) -> Dict:
    """항목설정을 열고, 사용자가 [저장]한 뒤 JSON으로 기억할 데이터를 반환합니다."""
    open_outall_item_settings_popup(page)
    print(
        f"[안내] {SCREEN_NAME} 팝업에서 원하는 대로 수정한 뒤 [저장] 버튼을 눌러 주세요.",
        flush=True,
    )
    return wait_for_outall_user_to_click_save(page, config=config)


def run_save_outall(page: Page, config: Dict) -> None:
    """11번 run_remember_flow와 동일 — 출고통합관리 항목설정을 JSON으로 저장."""
    print(
        f"[안내] 저장 대상 파일: {SETTINGS_FILE_OUTALL}",
        flush=True,
    )
    goto_out_all_list(page, config)
    captured = remember_outall_settings_after_user_save(page, config=config)
    merged = merge_remember_payload_with_existing(captured, config=config)
    merged["screen"] = "outall_manage"
    path = save_item_settings(merged, config=config)
    print(f"[완료] {SCREEN_NAME} 항목설정 JSON 저장: {path}", flush=True)


def run_apply_outall(page: Page, config: Dict, *, keep_browser: bool = True) -> None:
    """JSON에 저장된 출고통합관리 항목설정을 화면에 반영·저장합니다."""
    settings = load_item_settings(config=config)
    if not settings:
        raise FileNotFoundError(
            f"설정 파일이 없습니다: {SETTINGS_FILE_OUTALL}\n"
            "먼저 391번으로 JSON을 저장해 주세요."
        )

    unused, used = _split_settings_sections(settings)
    if not used and not unused:
        raise ValueError("JSON에 미사용·사용 항목이 없습니다.")

    goto_out_all_list(page, config)
    open_outall_item_settings_popup(page)
    missing = apply_settings_from_json(page, settings, screen_name=SCREEN_NAME)
    snapshot = capture_item_settings_from_popup(page, config=config)
    try:
        verify_popup_matches_json(
            settings, snapshot, missing, screen_name=SCREEN_NAME
        )
    except ValueError as exc:
        print(f"[경고] {exc}", flush=True)
        wait_for_outall_user_to_click_save(page, config=config)
        print(f"[완료] {SCREEN_NAME} 항목설정 수동 저장 완료", flush=True)
        return

    click_save_in_outall_item_settings_popup(page)
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        print(
            f"[경고] {SCREEN_NAME} 저장 alert OK를 찾지 못했습니다.",
            flush=True,
        )
    wait_outall_item_settings_popup_closed(page)
    print(f"[완료] {SCREEN_NAME} 항목설정 JSON 적용·저장", flush=True)


def run_task(page, context, config=None, *, keep_browser: bool = False):
    """391(save) 또는 392(apply) 항목설정 작업을 실행합니다."""
    cfg = refresh_config_from_env(config or CONFIG)
    action = (cfg.get("outall_item_action") or ACTION_SAVE).strip().lower()

    if action == ACTION_APPLY:
        run_apply_outall(page, cfg, keep_browser=keep_browser)
    else:
        run_save_outall(page, cfg)

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
