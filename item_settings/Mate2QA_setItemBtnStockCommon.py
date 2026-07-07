# Mate2QA — WMS 재고현황 항목설정 JSON 저장·적용 공통 처리

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
    save_item_settings,
    verify_popup_matches_json,
    wait_item_settings_boards_ready,
)
from Mate2QA_site_config import STATE_FILE_DOMESTIC, refresh_config_from_env

ACTION_SAVE = "save"
ACTION_APPLY = "apply"
STATE_FILE = STATE_FILE_DOMESTIC

CONFIG = {
    **_BASE_CONFIG,
    "stock_item_action": ACTION_SAVE,
}

STOCK_SET_ITEM_POP = "#outSetItemModal"
STOCK_SET_ITEM_POP_CANDIDATES = [
    "#stockItemModal",
    "#stkItemModal",
    "#stockSetItemModal",
    "#outSetItemModal",
    "#setItemPop",
    ".modal.show:has(button[onclick*='insUpdItemRgst'])",
    ".modal.show:has(button[onclick*='StkColum'])",
    ".modal.show:has(#leftBoard)",
    ".modal.show:has(#rightBoard)",
    ".modal.show:has(form#setItemForm)",
    ".modal.show:has-text('항목')",
]


def _stock_item_settings_popup(page: Page):
    """현재 화면에서 보이는 재고현황 항목설정 팝업 locator를 반환합니다."""
    for selector in STOCK_SET_ITEM_POP_CANDIDATES:
        pop = page.locator(selector).first
        try:
            if pop.count() > 0 and pop.is_visible():
                return pop
        except Exception:
            continue
    return None


def is_stock_item_settings_popup_visible(page: Page) -> bool:
    """재고현황 항목설정 팝업 표시 여부."""
    return _stock_item_settings_popup(page) is not None


def wait_stock_item_settings_popup_ready(page: Page) -> None:
    """재고현황 항목설정 팝업과 보드 로딩을 기다립니다."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if is_stock_item_settings_popup_visible(page):
            break
        page.wait_for_timeout(200)
    else:
        raise PlaywrightTimeoutError("재고현황 항목설정 팝업이 열리지 않았습니다.")
    wait_item_settings_boards_ready(page)


def wait_stock_item_settings_popup_closed(
    page: Page, timeout_ms: int = 15_000
) -> None:
    """재고현황 항목설정 팝업이 닫힐 때까지 대기합니다."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if not is_stock_item_settings_popup_visible(page):
            return
        page.wait_for_timeout(200)


def install_stock_item_settings_save_listener(page: Page) -> None:
    """재고현황 팝업이 열려 있을 때 [저장] 클릭 감지 리스너를 설치합니다."""
    if is_stock_item_settings_popup_visible(page):
        _install_stock_user_save_listener(page)


def _install_stock_user_save_listener(page: Page) -> None:
    """사용자가 재고현황 [저장] 버튼을 누를 때 팝업 상태를 즉시 스냅샷합니다."""
    page.evaluate(
        """() => {
            window.__stockSetItemUserSaved = false;
            window.__stockSetItemCapturedData = null;

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
                window.__stockSetItemCapturedData = snapshotBoards();
                window.__stockSetItemUserSaved = true;
            };

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const pop = document.getElementById('stockItemModal')
                || document.getElementById('stkItemModal')
                || document.getElementById('stockSetItemModal')
                || document.getElementById('outSetItemModal')
                || document.getElementById('setItemPop')
                || [...document.querySelectorAll('.modal')].find((el) =>
                    isVisible(el)
                    && (
                        el.querySelector('button[onclick*="insUpdItemRgst"]')
                        || el.querySelector('button[onclick*="StkColum"]')
                        || el.querySelector('#leftBoard')
                        || el.querySelector('#rightBoard')
                        || el.querySelector('form#setItemForm')
                        || (el.textContent || '').includes('항목')
                    )
                );
            if (!pop) return;
            for (const btn of pop.querySelectorAll('button')) {
                const text = (btn.textContent || '').replace(/\\s+/g, '');
                if (!text.includes('저장')) continue;
                btn.addEventListener('mousedown', onSaveIntent, { capture: true });
                btn.addEventListener('click', onSaveIntent, { capture: true });
            }
        }"""
    )


def _stock_user_clicked_save(page: Page) -> bool:
    return bool(page.evaluate("() => !!window.__stockSetItemUserSaved"))


def _pull_stock_user_saved_capture(
    page: Page, *, config: Dict | None = None
) -> Dict[str, Any] | None:
    """저장 클릭 직전 JS 스냅샷을 JSON payload로 변환합니다."""
    raw = page.evaluate(
        """() => {
            const d = window.__stockSetItemCapturedData;
            if (!d) return null;
            return d;
        }"""
    )
    if not raw:
        return None
    return build_settings_payload(
        page, raw.get("unused") or [], raw.get("used") or [], config=config
    )


def _wait_for_stock_user_save_click(
    page: Page, timeout_ms: int = 600_000
) -> None:
    """열린 재고현황 팝업에서 사용자 [저장] 클릭을 대기합니다."""
    pop = _stock_item_settings_popup(page)
    if pop is None:
        raise ValueError("재고현황 항목설정 팝업이 열려 있지 않습니다.")

    _install_stock_user_save_listener(page)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _stock_user_clicked_save(page):
            return
        if not pop.is_visible():
            raise ValueError(
                "재고현황 항목설정 팝업이 닫혔지만 [저장]이 눌리지 않았습니다. "
                "다시 저장 메뉴를 실행해 주세요."
            )
        page.wait_for_timeout(200)
    raise TimeoutError(
        "저장 대기 시간이 초과되었습니다. [저장] 버튼을 눌러 주세요."
    )


def _complete_stock_save_after_user_click(
    page: Page, *, screen_name: str = ""
) -> None:
    """사용자 [저장] 후 alert OK·재고현황 팝업 닫힘까지 처리합니다."""
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        prefix = f"{screen_name}: " if screen_name else ""
        print(f"[경고] {prefix}저장 alert OK 버튼을 찾지 못했습니다.", flush=True)
    wait_stock_item_settings_popup_closed(page, timeout_ms=10_000)
    page.wait_for_timeout(300)


def click_save_in_stock_item_settings_popup(page: Page) -> None:
    """재고현황 항목설정 팝업에서 저장 버튼을 클릭합니다."""
    pop = _stock_item_settings_popup(page)
    if pop is None:
        raise ValueError("재고현황 항목설정 팝업이 열려 있지 않습니다.")

    save_btn = pop.locator(
        'button[onclick*="insUpdItemRgst"], button:has-text("저장")'
    ).first
    try:
        save_btn.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as exc:
        raise ValueError("재고현황 항목설정 팝업의 저장 버튼을 찾지 못했습니다.") from exc

    save_btn.scroll_into_view_if_needed()
    try:
        save_btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        save_btn.click(force=True)


def wait_for_stock_user_to_click_save(
    page: Page, timeout_ms: int = 600_000, *, config: Dict | None = None
) -> Dict[str, Any]:
    """사용자가 [저장]을 누를 때까지 대기하고, 저장 직전 팝업 설정을 읽습니다."""
    pop = _stock_item_settings_popup(page)
    if pop is None:
        raise ValueError("재고현황 항목설정 팝업이 열려 있지 않습니다.")

    install_stock_item_settings_save_listener(page)
    _wait_for_stock_user_save_click(page, timeout_ms=timeout_ms)

    captured = _pull_stock_user_saved_capture(page, config=config)
    if captured is None and pop.is_visible():
        captured = capture_item_settings_from_popup(page, config=config)

    if captured is None:
        raise ValueError(
            "저장 직후 재고현황 항목설정을 읽지 못했습니다. "
            "다시 저장 메뉴를 실행해 주세요."
        )

    screen_name = (config or {}).get("stock_item_screen_name", "")
    _complete_stock_save_after_user_click(page, screen_name=screen_name)
    return captured


def wait_stock_item_screen_ready(page: Page, timeout_ms: int = 30_000) -> None:
    """재고현황 화면에서 항목설정 버튼이 준비될 때까지 대기합니다."""
    try:
        page.locator("#setItemBtn, button:has-text('항목설정')").first.wait_for(
            state="visible", timeout=timeout_ms
        )
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "재고현황 화면에서 항목설정 버튼을 찾지 못했습니다. "
            "화면이 완전히 로드됐는지 확인해 주세요."
        ) from exc
    page.wait_for_timeout(500)


def open_stock_item_settings_popup(page: Page) -> None:
    """재고현황 항목설정 버튼을 클릭하고 팝업을 엽니다."""
    if is_stock_item_settings_popup_visible(page):
        wait_stock_item_settings_popup_ready(page)
        return

    btn = page.locator("#setItemBtn, button:has-text('항목설정')").first
    try:
        btn.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeoutError as exc:
        raise ValueError("재고현황 항목설정 버튼을 찾지 못했습니다.") from exc

    btn.scroll_into_view_if_needed()
    try:
        btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        btn.click(force=True)

    page.wait_for_timeout(400)
    if not is_stock_item_settings_popup_visible(page):
        btn.evaluate("el => el.click()")
        page.wait_for_timeout(400)

    if not is_stock_item_settings_popup_visible(page):
        raise PlaywrightTimeoutError(f"{STOCK_SET_ITEM_POP} 팝업이 열리지 않았습니다.")

    wait_stock_item_settings_popup_ready(page)


def goto_stock_item_screen(page: Page, config: Dict) -> None:
    """설정된 재고현황 화면 URL로 이동합니다."""
    url_key = (config.get("stock_item_url_key") or "").strip()
    if not url_key:
        raise ValueError("stock_item_url_key가 설정되지 않았습니다.")

    url = (config.get(url_key) or "").strip()
    if not url:
        raise ValueError(f"{url_key} URL이 설정되지 않았습니다.")

    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    wait_stock_item_screen_ready(page)


def run_save_stock_item_settings(page: Page, config: Dict) -> None:
    """재고현황 화면의 현재 항목설정을 JSON으로 저장합니다."""
    screen_name = config["stock_item_screen_name"]
    screen_key = config["stock_item_screen_key"]

    goto_stock_item_screen(page, config)
    open_stock_item_settings_popup(page)
    print(
        f"[안내] {screen_name} 팝업에서 원하는 대로 수정한 뒤 [저장] 버튼을 눌러 주세요.",
        flush=True,
    )
    captured = wait_for_stock_user_to_click_save(page, config=config)
    captured["screen"] = screen_key
    path = save_item_settings(captured, config=config)
    print(f"[완료] {screen_name} 항목설정 JSON 저장: {path}", flush=True)


def run_apply_stock_item_settings(
    page: Page, config: Dict, *, keep_browser: bool = True
) -> None:
    """JSON에 저장된 재고현황 항목설정을 화면에 반영·저장합니다."""
    screen_name = config["stock_item_screen_name"]
    settings = load_item_settings(config=config)
    if not settings:
        raise FileNotFoundError(
            f"설정 파일이 없습니다: {config['item_settings_file']}\n"
            f"먼저 {config['stock_item_save_menu_no']}번으로 JSON을 저장해 주세요."
        )

    unused, used = _split_settings_sections(settings)
    if not used and not unused:
        raise ValueError("JSON에 미사용·사용 항목이 없습니다.")

    goto_stock_item_screen(page, config)
    open_stock_item_settings_popup(page)
    missing = apply_settings_from_json(page, settings, screen_name=screen_name)
    snapshot = capture_item_settings_from_popup(page, config=config)
    try:
        verify_popup_matches_json(settings, snapshot, missing, screen_name=screen_name)
    except ValueError as exc:
        print(f"[경고] {exc}", flush=True)
        wait_for_stock_user_to_click_save(page, config=config)
        print(f"[완료] {screen_name} 항목설정 수동 저장 완료", flush=True)
        return

    click_save_in_stock_item_settings_popup(page)
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        print(f"[경고] {screen_name} 저장 alert OK를 찾지 못했습니다.", flush=True)
    wait_stock_item_settings_popup_closed(page)
    print(f"[완료] {screen_name} 항목설정 JSON 적용·저장", flush=True)


def run_stock_item_task(page, context, config=None, *, keep_browser: bool = False):
    """재고현황 항목설정 저장 또는 적용 작업을 실행합니다."""
    cfg = refresh_config_from_env(config or CONFIG)
    action = (cfg.get("stock_item_action") or ACTION_SAVE).strip().lower()

    if action == ACTION_APPLY:
        run_apply_stock_item_settings(page, cfg, keep_browser=keep_browser)
    else:
        run_save_stock_item_settings(page, cfg)

    if keep_browser:
        return cfg

    message = (
        f"{cfg['stock_item_screen_name']} JSON 적용 후 Enter를 누르세요."
        if action == ACTION_APPLY
        else f"{cfg['stock_item_screen_name']} JSON 저장 후 Enter를 누르세요."
    )
    wait_enter_after_task(keep_browser=False, message=message)
    return cfg
