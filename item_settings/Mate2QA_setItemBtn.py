# Mate2QA — 항목설정(#setItemBtn) JSON 기억·화면별 적용 (런처 7번 → 서브 11)
#
# 실행: python -m item_settings.Mate2QA_setItemBtn
# 사이트 URL: Mate2QA_site_config.py (또는 Mate2QA_login.env)

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from Mate2QA_login import first_visible_locator
from Mate2QA_menu_nav import (
    LauncherExit,
    MAIN_MENU_EXIT,
    SUBMENU_BACK,
    submenu_nav_footer,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    join_origin_path,
    refresh_config_from_env,
)

SETTINGS_FILE_DOMESTIC = PROJECT_DIR / "grid_item_settings.json"
SETTINGS_FILE_OVERSEAS = PROJECT_DIR / "grid_item_settings_overseas.json"
SCOPE_DOMESTIC = "domestic"
SCOPE_OVERSEAS = "overseas"

CONFIG = {
    **_SITE_CONFIG,
    "item_settings_scope": SCOPE_DOMESTIC,
    "item_settings_file": SETTINGS_FILE_DOMESTIC.name,
}

SET_ITEM_BTN_CANDIDATES = [
    "#setItemBtn",
    'button#setItemBtn.btn-warning.btn-sm:has-text("항목설정")',
    'button.btn-warning:has-text("항목설정")',
]
SET_ITEM_POP = "#setItemPop"
CLOSE_BTN = f"{SET_ITEM_POP} button:has-text('닫기')"
SAVE_BTN_CANDIDATES = [
    f"{SET_ITEM_POP} button:has-text('저장')",
    '#setItemForm button:has-text("저장")',
    'button.btn-primary:has-text("저장")',
]

def is_overseas_scope(config: Dict) -> bool:
    """해외 항목설정(서브 21번) 여부를 반환합니다."""
    return (config.get("item_settings_scope") or SCOPE_DOMESTIC).strip().lower() == SCOPE_OVERSEAS


def resolve_settings_file(config: Dict) -> Path:
    """CONFIG 기준 항목설정 JSON 경로를 반환합니다."""
    raw = (config.get("item_settings_file") or SETTINGS_FILE_DOMESTIC.name).strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_DIR / raw


def format_apply_menu_text(config: Dict) -> str:
    """국내·해외 항목설정 서브메뉴 문구를 반환합니다."""
    json_name = resolve_settings_file(config).name
    if is_overseas_scope(config):
        remember_label = "해외 주문발주관리"
    else:
        remember_label = "통합관리"
    return f"""
------------------------------------------------------------
항목설정 — 적용할 화면을 선택하세요 (JSON: {json_name})
m/ㅡ  {remember_label} JSON 저장 
a  전체 일괄적용(0 ~ 8)
0  주문발주관리       /  1  주문서처리
2  출고준비           /  3  발송준비
4  발송대기           /  5  배송중
6  배송완료           /  7  통합관리
8  출고보류
{submenu_nav_footer(back_label="상위 메뉴 복귀")}

※ 복수 선택: 123 → 1·2·3번 순서대로 적용
------------------------------------------------------------
"""


def build_apply_screen_urls(config: Dict) -> Dict[int, tuple[str, str]]:
    """화면 번호 → (표시명, URL)"""
    if is_overseas_scope(config):
        return {
            0: ("해외 주문발주관리", config["intl_order_list_url"]),
            1: ("해외 주문서처리", config["intl_put_order_list_url"]),
            2: ("해외 출고준비", config["intl_out_ready_list_url"]),
            3: ("해외 발송준비", config["intl_ship_ready_list_url"]),
            4: ("해외 발송대기", config["intl_ship_wait_list_url"]),
            5: ("해외 배송중", config["intl_shipping_list_url"]),
            6: ("해외 배송완료", config["intl_dlvr_compt_list_url"]),
            7: ("해외 통합관리", config["intl_intg_order_list_url"]),
            8: ("해외 출고보류", config["intl_out_hold_list_url"]),
        }
    return {
        0: ("주문발주관리", config["order_list_url"]),
        1: ("주문서처리", config["put_order_list_url"]),
        2: ("출고준비", config["out_ready_list_url"]),
        3: ("발송준비", config["ship_ready_list_url"]),
        4: ("발송대기", config["ship_wait_list_url"]),
        5: ("배송중", config["shipping_list_url"]),
        6: ("배송완료", config["dlvr_compt_list_url"]),
        7: ("통합관리", config["intg_order_list_url"]),
        8: ("출고보류", config["out_hold_list_url"]),
    }


def parse_apply_selection(raw: str) -> List[int]:
    """0, a, 7, 123 등 입력을 화면 번호 목록으로 변환합니다."""
    text = (raw or "").strip().lower()
    if not text:
        return []
    if text == "0":
        return [0]
    if text == "a":
        return list(range(0, 9))
    if text in {"m", "ㅡ"}:
        return []
    ids: List[int] = []
    for ch in text:
        if not ch.isdigit():
            continue
        num = int(ch)
        if 0 <= num <= 8 and num not in ids:
            ids.append(num)
    return ids


def prompt_apply_selection(config: Dict) -> str:
    """적용/기억 서브메뉴 입력을 받습니다."""
    print(format_apply_menu_text(config), flush=True)
    try:
        return input(
            f"선택 입력 (0~8 / a / m(또는 ㅡ) / 123 / {SUBMENU_BACK} / {MAIN_MENU_EXIT}): "
        ).strip()
    except EOFError:
        return SUBMENU_BACK


def _read_board_items(page: Page, board_id: str) -> List[Dict[str, Any]]:
    """leftBoard / rightBoard 항목 목록을 읽습니다."""
    return page.evaluate(
        """(boardId) => {
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
        }""",
        board_id,
    )


def open_item_settings_popup(page: Page) -> None:
    """항목설정 버튼을 클릭하고 팝업이 열릴 때까지 대기합니다."""
    btn, _sel = first_visible_locator(page, SET_ITEM_BTN_CANDIDATES)
    if btn is None:
        try:
            page.locator("#setItemBtn").wait_for(state="visible", timeout=15_000)
            btn = page.locator("#setItemBtn").first
        except PlaywrightTimeoutError as exc:
            raise ValueError(
                "항목설정 버튼(#setItemBtn)을 찾지 못했습니다. "
                "주문목록 화면이 완전히 로드됐는지 확인해 주세요."
            ) from exc
    btn.scroll_into_view_if_needed()
    btn.click()
    page.locator(SET_ITEM_POP).wait_for(state="visible", timeout=15_000)
    wait_item_settings_boards_ready(page)


def wait_wm_exec_tab_item_settings_button(
    page: Page,
    *,
    tab_panel: str,
    data_code: str,
    timeout_ms: int = 30_000,
) -> None:
    """출고작업(outWkOrdList) 활성 탭의 항목설정 버튼이 보일 때까지 대기합니다."""
    panel = page.locator(
        f"{tab_panel}.tab-pane.active.show, {tab_panel}.active.show"
    ).first
    panel.wait_for(state="visible", timeout=timeout_ms)
    panel.locator(
        f'button#setItemBtn[data-code="{data_code}"], #setItemBtn'
    ).first.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(500)


def open_wm_exec_tab_item_settings_popup(
    page: Page,
    *,
    tab_panel: str,
    data_code: str,
    screen_label: str,
) -> None:
    """출고작업(outWkOrdList) 활성 탭의 항목설정 팝업을 엽니다."""
    wait_wm_exec_tab_item_settings_button(
        page, tab_panel=tab_panel, data_code=data_code
    )
    panel = page.locator(
        f"{tab_panel}.tab-pane.active.show, {tab_panel}.active.show"
    ).first
    btn = panel.locator(
        f'button#setItemBtn[data-code="{data_code}"], #setItemBtn'
    ).first
    btn.scroll_into_view_if_needed()
    try:
        btn.click(timeout=5_000)
    except PlaywrightTimeoutError:
        btn.click(force=True)
    pop = page.locator(SET_ITEM_POP)
    try:
        pop.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeoutError:
        btn.evaluate("el => el.click()")
        try:
            pop.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeoutError as exc:
            raise ValueError(
                f"{screen_label} 항목설정 팝업({SET_ITEM_POP})이 열리지 않았습니다. "
                "탭·화주·출고차수 선택을 확인해 주세요."
            ) from exc
    wait_item_settings_boards_ready(page)


def wait_item_settings_boards_ready(page: Page, timeout_ms: int = 20_000) -> None:
    """항목설정 팝업의 미사용·사용 보드 항목이 로드될 때까지 대기합니다."""
    page.locator("#leftBoard").wait_for(state="attached", timeout=timeout_ms)
    page.locator("#rightBoard").wait_for(state="attached", timeout=timeout_ms)
    try:
        page.wait_for_function(
            """() => {
                const left = document.querySelectorAll('#leftBoard .col-lg-12').length;
                const right = document.querySelectorAll('#rightBoard .col-lg-12').length;
                return left + right > 0;
            }""",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "항목설정 팝업은 열렸지만 항목 목록이 로드되지 않았습니다."
        ) from exc
    page.wait_for_timeout(300)


def close_item_settings_popup(page: Page) -> None:
    """항목설정 팝업을 닫습니다."""
    pop = page.locator(SET_ITEM_POP)
    if pop.count() == 0 or not pop.first.is_visible():
        return
    close = page.locator(CLOSE_BTN).first
    if close.is_visible():
        close.click()
    else:
        page.keyboard.press("Escape")
    click_save_success_alert_ok(page, timeout_ms=3_000)
    try:
        pop.first.wait_for(state="hidden", timeout=5_000)
    except PlaywrightTimeoutError:
        pass


def wait_item_settings_popup_closed(page: Page, timeout_ms: int = 15_000) -> None:
    """항목설정 팝업이 닫힐 때까지 대기합니다."""
    try:
        page.locator(SET_ITEM_POP).first.wait_for(state="hidden", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def is_item_settings_popup_visible(page: Page) -> bool:
    """항목설정 팝업(#setItemPop) 표시 여부."""
    pop = page.locator(SET_ITEM_POP).first
    try:
        return pop.count() > 0 and pop.is_visible()
    except Exception:
        return False


def install_item_settings_save_listener(page: Page) -> None:
    """팝업이 열려 있을 때 [저장] 클릭 감지 리스너를 설치합니다."""
    if is_item_settings_popup_visible(page):
        _install_user_save_listener(page)


def wait_item_settings_popup_after_manual_instruction(
    page: Page,
    *,
    open_wait_ms: int = 20_000,
    assume_saved_quiet_ms: int = 3_000,
) -> bool:
    """
    수동 안내 후 대기.
    True: 팝업이 열려 있음 → [저장] 클릭 대기 계속
    False: 저장 완료·팝업 닫힘 추정 → 재오픈 후 읽기
    """
    seen_open = False
    started = time.monotonic()
    deadline = started + open_wait_ms / 1000
    last_msg = started

    while time.monotonic() < deadline:
        now = time.monotonic()
        if is_item_settings_popup_visible(page):
            wait_item_settings_boards_ready(page)
            install_item_settings_save_listener(page)
            return True

        if seen_open:
            click_save_success_alert_ok(page, timeout_ms=2_000)
            return False

        if now - started >= assume_saved_quiet_ms / 1000:
            click_save_success_alert_ok(page, timeout_ms=2_000)
            print(
                "[안내] 저장을 완료하셨다면 저장된 설정을 읽습니다…",
                flush=True,
            )
            return False

        if now - last_msg >= 5:
            print(
                "[안내] 항목설정·저장 대기 중… "
                "(이미 저장하셨다면 곧 자동으로 설정을 읽습니다)",
                flush=True,
            )
            last_msg = now

        page.wait_for_timeout(200)

    click_save_success_alert_ok(page, timeout_ms=2_000)
    return False


def _install_user_save_listener(page: Page) -> None:
    """사용자가 항목설정 [저장] 버튼을 누를 때 팝업 상태를 즉시 스냅샷합니다."""
    page.evaluate(
        """() => {
            window.__setItemUserSaved = false;
            window.__setItemCapturedData = null;

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
                window.__setItemCapturedData = snapshotBoards();
                window.__setItemUserSaved = true;
            };

            const pop = document.getElementById('setItemPop');
            if (!pop) return;
            for (const btn of pop.querySelectorAll('button')) {
                const text = (btn.textContent || '').replace(/\\s+/g, '');
                if (!text.includes('저장')) continue;
                btn.addEventListener('mousedown', onSaveIntent, { capture: true });
                btn.addEventListener('click', onSaveIntent, { capture: true });
            }
        }"""
    )


def _user_clicked_save(page: Page) -> bool:
    return bool(page.evaluate("() => !!window.__setItemUserSaved"))


def _pull_user_saved_capture(
    page: Page, *, config: Dict | None = None
) -> Dict[str, Any] | None:
    """저장 클릭 직전 JS 스냅샷을 JSON payload로 변환합니다."""
    raw = page.evaluate(
        """() => {
            const d = window.__setItemCapturedData;
            if (!d) return null;
            return d;
        }"""
    )
    if not raw:
        return None
    return build_settings_payload(
        page, raw.get("unused") or [], raw.get("used") or [], config=config
    )


def click_save_success_alert_ok(page: Page, timeout_ms: int = 15_000) -> bool:
    """저장 후 표시되는 alert의 OK(확인) 버튼을 클릭합니다."""
    from Mate2QA_order_step import click_popup_ok_if_visible

    ok_selectors = [
        "button.swal2-confirm.swal2-styled",
        "button.swal2-confirm",
        ".swal2-popup.swal2-show button.swal2-confirm",
        ".swal2-container.swal2-shown button.swal2-confirm",
        '.swal2-container button:has-text("OK")',
        '.swal2-container button:has-text("확인")',
        'button:has-text("OK")',
        'button:has-text("확인")',
    ]

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if click_popup_ok_if_visible(page, timeout_ms=400):
            return True

        for sel in ok_selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0 and loc.is_visible():
                    loc.click()
                    page.wait_for_timeout(300)
                    return True
            except Exception:
                pass

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
                for (const btn of document.querySelectorAll('button, a.btn')) {
                    if (!isVisible(btn)) continue;
                    const label = (btn.innerText || btn.textContent || '').trim();
                    const lower = label.toLowerCase();
                    if (lower === 'ok' || label === '확인') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if clicked:
            page.wait_for_timeout(300)
            return True

        page.wait_for_timeout(200)

    return False


def _wait_for_user_save_click(page: Page, timeout_ms: int = 600_000) -> None:
    """열린 항목설정 팝업에서 사용자 [저장] 클릭을 대기합니다."""
    pop = page.locator(SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("항목설정 팝업이 열려 있지 않습니다.")

    _install_user_save_listener(page)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _user_clicked_save(page):
            return
        if not pop.is_visible():
            raise ValueError(
                "항목설정 팝업이 닫혔지만 [저장]이 눌리지 않았습니다. "
                "저장된 설정을 다시 읽습니다."
            )
        page.wait_for_timeout(200)
    raise TimeoutError(
        "저장 대기 시간이 초과되었습니다. [저장] 버튼을 눌러 주세요."
    )


def _complete_save_after_user_click(page: Page, *, screen_name: str = "") -> None:
    """사용자 [저장] 후 alert OK·팝업 닫힘까지 처리합니다."""
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        prefix = f"{screen_name}: " if screen_name else ""
        print(f"[경고] {prefix}저장 alert OK 버튼을 찾지 못했습니다.", flush=True)
    wait_item_settings_popup_closed(page, timeout_ms=10_000)
    page.wait_for_timeout(300)


def wait_for_user_manual_save_in_popup(
    page: Page, *, screen_name: str = "", timeout_ms: int = 600_000
) -> None:
    """검증 실패 등 — 사용자가 [저장]하면 alert OK 후 다음 화면으로 진행합니다."""
    _wait_for_user_save_click(page, timeout_ms=timeout_ms)
    _complete_save_after_user_click(page, screen_name=screen_name)


def wait_for_user_to_click_save(
    page: Page, timeout_ms: int = 600_000, *, config: Dict | None = None
) -> Dict[str, Any]:
    """사용자가 [저장]을 누를 때까지 대기하고, 저장 직전 팝업 설정을 읽습니다."""
    pop = page.locator(SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("항목설정 팝업이 열려 있지 않습니다.")

    install_item_settings_save_listener(page)
    _wait_for_user_save_click(page, timeout_ms=timeout_ms)

    captured = _pull_user_saved_capture(page, config=config)
    if captured is None and pop.is_visible():
        captured = capture_item_settings_from_popup(page, config=config)

    if captured is None:
        raise ValueError(
            "저장 직후 항목설정을 읽지 못했습니다. "
            "다시 메인 7번 → 11 또는 21번 항목설정을 실행해 주세요."
        )

    _complete_save_after_user_click(page)
    return captured


def capture_item_settings_after_user_popup_save(
    page: Page,
    *,
    config: Dict | None = None,
    screen_name: str = "",
    timeout_ms: int = 600_000,
) -> Dict[str, Any]:
    """열린 항목설정 팝업에서 사용자가 [저장]한 뒤 설정을 캡처합니다."""
    install_item_settings_save_listener(page)
    label = screen_name or "항목설정"
    print(
        f"[안내] {label} 팝업에서 원하는 대로 수정한 뒤 [저장] 버튼을 눌러 주세요.",
        flush=True,
    )
    return wait_for_user_to_click_save(
        page, timeout_ms=timeout_ms, config=config
    )


def _safe_column_width(width) -> int | None:
    """항목 width를 int로 변환합니다. 빈 값·비숫자는 None."""
    if width is None or width == "":
        return None
    try:
        return int(width)
    except (TypeError, ValueError):
        return None


def _normalize_column_list(
    columns: List[Dict[str, Any]], *, expsr_yn: str
) -> List[Dict[str, Any]]:
    """항목 목록에 구역별 순서(order)와 expsr_yn을 맞춥니다."""
    normalized: List[Dict[str, Any]] = []
    for idx, col in enumerate(columns, start=1):
        entry: Dict[str, Any] = {
            "order": idx,
            "grid_itm_sno": str(col.get("grid_itm_sno") or "").strip(),
            "label": str(col.get("label") or "").strip(),
            "expsr_yn": expsr_yn,
            "width": _safe_column_width(col.get("width")),
        }
        labels_for_json = _labels_for_json_column(col)
        if labels_for_json:
            entry["labels"] = labels_for_json
        normalized.append(entry)
    return normalized


def url_to_relative_path(url: str) -> str:
    """절대 URL을 사이트 상대 경로(/om/...)로 변환합니다."""
    parsed = urlparse((url or "").strip())
    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if path and not path.startswith("/"):
        path = f"/{path}"
    return path


def resolve_settings_url(config: Dict, url_or_path: str) -> str:
    """JSON의 상대 경로 또는 절대 URL을 현재 로그인 호스트 기준 URL로 만듭니다."""
    text = (url_or_path or "").strip()
    if not text:
        if is_overseas_scope(config):
            return str(config.get("intl_order_list_url") or "")
        return str(config.get("intg_order_list_url") or "")
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return text
    login_url = str(config.get("login_url") or "")
    return join_origin_path(login_url, text)


def build_settings_payload(
    page: Page,
    unused_raw: List[Dict[str, Any]],
    used_raw: List[Dict[str, Any]],
    *,
    config: Dict | None = None,
) -> Dict[str, Any]:
    """미사용 → 사용 순서로 구분된 JSON 구조를 만듭니다."""
    cfg = config or CONFIG
    default_screen = "intl_order_list" if is_overseas_scope(cfg) else "intg_manage"
    return {
        "screen": default_screen,
        "url": url_to_relative_path(page.url),
        "미사용": _normalize_column_list(unused_raw, expsr_yn="N"),
        "사용": _normalize_column_list(used_raw, expsr_yn="Y"),
    }


def capture_item_settings_from_popup(page: Page, *, config: Dict | None = None) -> Dict[str, Any]:
    """열린 항목설정 팝업에서 미사용·사용 항목을 순서대로 읽습니다."""
    unused_raw = _read_board_items(page, "leftBoard")
    used_raw = _read_board_items(page, "rightBoard")
    return build_settings_payload(page, unused_raw, used_raw, config=config)


def save_item_settings(data: Dict[str, Any], *, config: Dict | None = None) -> Path:
    """캡처한 항목설정을 JSON 파일로 저장합니다."""
    settings_file = resolve_settings_file(config or CONFIG)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return settings_file


def load_item_settings(*, config: Dict | None = None) -> Dict[str, Any] | None:
    """저장된 항목설정 JSON을 읽습니다. 없으면 None."""
    settings_file = resolve_settings_file(config or CONFIG)
    if not settings_file.exists():
        return None
    with settings_file.open(encoding="utf-8") as f:
        return json.load(f)


def _split_settings_sections(
    data: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """저장 JSON에서 미사용·사용 목록을 읽습니다 (구·신 형식 모두 지원)."""
    if "미사용" in data or "사용" in data:
        return data.get("미사용") or [], data.get("사용") or []
    return data.get("unused_columns") or [], data.get("used_columns") or []


def _column_identity(col: Dict[str, Any]) -> str:
    """항목 병합용 식별자(grid_itm_sno 우선, 없으면 label 키)"""
    sno = str(col.get("grid_itm_sno") or "").strip()
    if sno:
        return f"sno:{sno}"
    return f"label:{_label_key(col.get('label', ''))}"


def _merge_preserving_existing_columns(
    captured: List[Dict[str, Any]], existing: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    사용자 저장 캡처를 우선하되,
    기존 JSON에만 있던 항목은 뒤에 보존해 붙입니다.
    """
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for col in captured:
        ident = _column_identity(col)
        if ident in seen:
            continue
        seen.add(ident)
        merged.append(col)

    for col in existing:
        ident = _column_identity(col)
        if ident in seen:
            continue
        seen.add(ident)
        merged.append(col)
    return merged


def _match_fixed_column(col: Dict[str, Any], *, sno: str, label: str) -> bool:
    """고정 선두 항목 매칭(grid_itm_sno 우선, 보조로 label 사용)"""
    col_sno = str(col.get("grid_itm_sno") or "").strip()
    if col_sno and col_sno == sno:
        return True
    return _label_key(col.get("label", "")) == _label_key(label)


def _pin_fixed_front_used_columns(columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    통합관리 '사용' 목록 선두를 고정합니다.
    1: 출고 보류 사유(2540), 2: 출고 보류 사유 상세(2533)
    """
    fixed_specs = [
        {"grid_itm_sno": "2540", "label": "출고 보류 사유", "width": 150},
        {"grid_itm_sno": "2533", "label": "출고 보류 사유 상세", "width": 200},
    ]
    remaining = list(columns)
    pinned: List[Dict[str, Any]] = []

    for spec in fixed_specs:
        idx = next(
            (
                i
                for i, col in enumerate(remaining)
                if _match_fixed_column(
                    col,
                    sno=str(spec["grid_itm_sno"]),
                    label=str(spec["label"]),
                )
            ),
            None,
        )
        if idx is not None:
            col = dict(remaining.pop(idx))
            col["grid_itm_sno"] = str(spec["grid_itm_sno"])
            col["label"] = str(spec["label"])
            if col.get("width") in (None, "", 0):
                col["width"] = int(spec["width"])
            pinned.append(col)
            continue

        pinned.append(
            {
                "grid_itm_sno": str(spec["grid_itm_sno"]),
                "label": str(spec["label"]),
                "width": int(spec["width"]),
                "expsr_yn": "Y",
            }
        )

    return pinned + remaining


def merge_remember_payload_with_existing(
    captured_data: Dict[str, Any], *, config: Dict | None = None
) -> Dict[str, Any]:
    """
    m/ㅡ 저장 시 기존 JSON의 수동 추가 항목이 사라지지 않도록 병합합니다.
    """
    cfg = config or CONFIG
    existing = load_item_settings(config=cfg) or {}
    existing_unused, existing_used = _split_settings_sections(existing)
    captured_unused, captured_used = _split_settings_sections(captured_data)

    merged_unused = _merge_preserving_existing_columns(captured_unused, existing_unused)
    merged_used = _merge_preserving_existing_columns(captured_used, existing_used)
    if not is_overseas_scope(cfg):
        merged_used = _pin_fixed_front_used_columns(merged_used)

    default_screen = "intl_order_list" if is_overseas_scope(cfg) else "intg_manage"
    return {
        "screen": captured_data.get("screen") or existing.get("screen") or default_screen,
        "url": captured_data.get("url") or existing.get("url") or "",
        "미사용": _normalize_column_list(merged_unused, expsr_yn="N"),
        "사용": _normalize_column_list(merged_used, expsr_yn="Y"),
    }


def wait_screen_ready(page: Page, timeout_ms: int = 30_000) -> None:
    """화면 로딩 후 항목설정 버튼이 보일 때까지 대기합니다."""
    try:
        page.locator("#setItemBtn").wait_for(
            state="visible", timeout=timeout_ms
        )
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "항목설정 버튼(#setItemBtn)이 보이지 않습니다. "
            "화면 로딩·화주 선택을 확인해 주세요."
        ) from exc
    page.wait_for_timeout(500)


def click_save_in_item_settings_popup(page: Page) -> None:
    """항목설정 팝업에서 저장 버튼을 클릭합니다."""
    btn, _sel = first_visible_locator(page, SAVE_BTN_CANDIDATES)
    if btn is None:
        raise ValueError("항목설정 팝업의 저장 버튼을 찾지 못했습니다.")
    btn.scroll_into_view_if_needed()
    btn.click()


def _columns_for_apply(columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """적용용 payload — sno·label·labels(원문)·width."""
    out: List[Dict[str, Any]] = []
    for col in columns:
        sno = str(col.get("grid_itm_sno") or "").strip()
        keys = _column_label_keys(col)
        if not sno and not keys:
            continue
        primary = _column_primary_label(col)
        # JS findItem이 labelKey로 정규화하므로 원문 labels를 전달
        raw_labels = _labels_for_json_column(col) or [primary]
        out.append(
            {
                "grid_itm_sno": sno,
                "label": primary,
                "labels": raw_labels,
                "width": col.get("width"),
            }
        )
    return out


def _label_key(label: str) -> str:
    """항목명 비교용 — 공백 제거."""
    return "".join(str(label or "").split())


def _labels_for_json_column(col: Dict[str, Any]) -> List[str] | None:
    """JSON 저장용 labels — label·labels 후보를 원문 그대로 반환 (1개면 생략)."""
    seen: set[str] = set()
    out: List[str] = []
    for text in [str(col.get("label") or "").strip()]:
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    raw = col.get("labels")
    if isinstance(raw, list):
        for item in raw:
            t = str(item or "").strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out if len(out) > 1 else None


def _column_label_keys(col: Dict[str, Any]) -> List[str]:
    """항목의 label·labels 후보를 정규화해 반환합니다 (순서 유지, 중복 제거)."""
    keys: List[str] = []
    seen: set[str] = set()
    candidates: List[str] = []
    primary = str(col.get("label") or "").strip()
    if primary:
        candidates.append(primary)
    raw = col.get("labels")
    if isinstance(raw, list):
        candidates.extend(str(x or "").strip() for x in raw)
    for text in candidates:
        if not text:
            continue
        key = _label_key(text)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _column_primary_label(col: Dict[str, Any]) -> str:
    """대표 항목명 — label 없으면 labels[0]."""
    label = str(col.get("label") or "").strip()
    if label:
        return label
    keys = _column_label_keys(col)
    return keys[0] if keys else ""


def _missing_label_keys(missing: List[str]) -> set[str]:
    """missing 목록(대표 label)을 정규화 키 집합으로 변환합니다."""
    return {_label_key(m) for m in missing if _label_key(m)}


def _json_columns_excluding_missing(
    columns: List[Dict[str, Any]], missing: List[str]
) -> List[Dict[str, Any]]:
    """missing에 해당하는 JSON 항목을 제외합니다 (labels 후보 포함)."""
    missing_keys = _missing_label_keys(missing)
    out: List[Dict[str, Any]] = []
    for col in columns:
        keys = _column_label_keys(col)
        if not keys:
            continue
        if any(k in missing_keys for k in keys):
            continue
        out.append(col)
    return out


def _refresh_item_settings_sortable(page: Page) -> None:
    """드래그 UI(sortable)에 DOM 변경을 반영합니다."""
    page.evaluate(
        """() => {
            if (typeof $ === 'undefined') return;
            try {
                const $l = $('#leftBoard');
                const $r = $('#rightBoard');
                if ($l.data('ui-sortable')) $l.sortable('refresh');
                if ($r.data('ui-sortable')) $r.sortable('refresh');
            } catch (e) { /* sortable 미사용 화면 */ }
        }"""
    )


def verify_popup_matches_json(
    settings: Dict[str, Any],
    snapshot: Dict[str, Any],
    missing: List[str],
    *,
    screen_name: str = "",
) -> None:
    """적용 후 팝업 상태가 JSON과 일치하는지 검증합니다."""
    prefix = f"{screen_name}: " if screen_name else ""
    json_unused, json_used = _split_settings_sections(settings)
    snap_unused, snap_used = _split_settings_sections(snapshot)

    json_used_active = _json_columns_excluding_missing(json_used, missing)
    json_unused_active = _json_columns_excluding_missing(json_unused, missing)

    if len(snap_used) < len(json_used_active):
        expected = [_column_primary_label(c) for c in json_used_active]
        actual = [_label_key(c.get("label", "")) for c in snap_used]
        raise ValueError(
            f"{prefix}적용 후 '사용' 항목이 JSON보다 적습니다.\n"
            f"  JSON: {len(json_used_active)}개 {expected[:8]}"
            f"{'...' if len(expected) > 8 else ''}\n"
            f"  팝업: {len(snap_used)}개 {actual[:8]}"
            f"{'...' if len(actual) > 8 else ''}"
        )

    for idx, (jc, sc) in enumerate(
        zip(json_used_active, snap_used[: len(json_used_active)]), start=1
    ):
        actual = _label_key(sc.get("label", ""))
        allowed = _column_label_keys(jc)
        if actual not in allowed:
            raise ValueError(
                f"{prefix}적용 후 '사용' {idx}번째 항목이 JSON과 다릅니다.\n"
                f"  JSON(후보): {allowed}\n"
                f"  팝업: {sc.get('label', '')!r}"
            )

    actual_unused = {_label_key(c.get("label", "")) for c in snap_unused}

    for jc in json_unused_active:
        allowed = _column_label_keys(jc)
        if not any(k in actual_unused for k in allowed):
            raise ValueError(
                f"{prefix}JSON '미사용' 항목 '{_column_primary_label(jc)}'"
                f"(후보: {allowed})이(가) 팝업 미사용에 없습니다."
            )

    if missing:
        print(
            f"[안내] {prefix}이 화면에 없는 항목 {len(missing)}개는 건너뛰었습니다: "
            f"{', '.join(str(m) for m in missing[:8])}"
            f"{'...' if len(missing) > 8 else ''}",
            flush=True,
        )


def apply_settings_from_json(
    page: Page, settings: Dict[str, Any], *, screen_name: str = ""
) -> List[str]:
    """JSON(미사용·사용)을 항목설정 팝업에 반영합니다. 찾지 못한 label 목록 반환."""
    unused, used = _split_settings_sections(settings)
    payload = {
        "unused": _columns_for_apply(unused),
        "used": _columns_for_apply(used),
    }
    result = page.evaluate(
        """(data) => {
            const left = document.getElementById('leftBoard');
            const right = document.getElementById('rightBoard');
            if (!left || !right) {
                return { ok: false, error: 'leftBoard 또는 rightBoard를 찾지 못했습니다.' };
            }

            const labelKey = (t) => (t || '').replace(/\\s+/g, '').trim();
            const matchedEls = new Set();

            const collectAll = () => {
                const items = [];
                for (const board of [left, right]) {
                    for (const el of board.querySelectorAll('.col-lg-12')) {
                        const strong = el.querySelector('.move-tag strong');
                        const inp = el.querySelector('input[name="grid_itm_sno"]');
                        items.push({
                            el,
                            label: strong ? strong.textContent.trim() : '',
                            key: labelKey(strong ? strong.textContent : ''),
                            sno: inp ? inp.value : '',
                        });
                    }
                }
                return items;
            };

            const findItem = (col) => {
                const wantLabels = (col.labels && col.labels.length)
                    ? col.labels
                    : (col.label ? [col.label] : []);
                const wantKeys = wantLabels.map(labelKey).filter(Boolean);
                const wantSno = col.grid_itm_sno || '';
                for (const wantKey of wantKeys) {
                    for (const item of collectAll()) {
                        if (matchedEls.has(item.el)) continue;
                        if (item.key === wantKey) return item.el;
                    }
                }
                for (const item of collectAll()) {
                    if (matchedEls.has(item.el)) continue;
                    if (wantSno && item.sno === wantSno) return item.el;
                }
                return null;
            };

            const setWidth = (el, width) => {
                const w = el.querySelector('input[name="itm_width"]');
                if (w && width != null && width !== '') {
                    w.value = String(width);
                    w.dispatchEvent(new Event('input', { bubbles: true }));
                    w.dispatchEvent(new Event('change', { bubbles: true }));
                }
            };

            const missing = [];
            let appliedUsed = 0;
            let appliedUnused = 0;

            // 1) JSON 미사용 → left
            data.unused.forEach((col) => {
                const el = findItem(col);
                if (!el) {
                    missing.push(col.label || col.grid_itm_sno);
                    return;
                }
                matchedEls.add(el);
                const expsr = el.querySelector('input[name="expsr_yn"]');
                if (expsr) expsr.value = 'N';
                setWidth(el, col.width);
                left.appendChild(el);
                appliedUnused += 1;
            });

            // 2) JSON 사용 → right (순서 유지)
            data.used.forEach((col) => {
                const el = findItem(col);
                if (!el) {
                    missing.push(col.label || col.grid_itm_sno);
                    return;
                }
                matchedEls.add(el);
                const expsr = el.querySelector('input[name="expsr_yn"]');
                if (expsr) expsr.value = 'Y';
                setWidth(el, col.width);
                right.appendChild(el);
                appliedUsed += 1;
            });

            // 3) JSON에 없는 나머지 → 사용(right) 맨 끝에 유지
            let appendedExtra = 0;
            if (appliedUsed > 0 || appliedUnused > 0) {
                const extras = [];
                for (const board of [left, right]) {
                    for (const el of board.querySelectorAll('.col-lg-12')) {
                        if (matchedEls.has(el)) continue;
                        extras.push(el);
                    }
                }
                for (const el of extras) {
                    const expsr = el.querySelector('input[name="expsr_yn"]');
                    if (expsr) expsr.value = 'Y';
                    right.appendChild(el);
                    appendedExtra += 1;
                }
            }

            const applied = appliedUsed + appliedUnused;
            return {
                ok: true,
                missing,
                applied,
                appliedUsed,
                appliedUnused,
                appendedExtra,
                boardCount:
                    left.querySelectorAll('.col-lg-12').length
                    + right.querySelectorAll('.col-lg-12').length,
            };
        }""",
        payload,
    )
    if not result.get("ok"):
        raise ValueError(result.get("error") or "항목설정 반영에 실패했습니다.")

    missing = result.get("missing") or []
    prefix = f"{screen_name}: " if screen_name else ""

    if missing:
        print(
            f"[경고] {prefix}찾지 못한 항목 {len(missing)}개 — "
            f"{', '.join(str(m) for m in missing[:5])}"
            f"{'...' if len(missing) > 5 else ''}",
            flush=True,
        )

    _refresh_item_settings_sortable(page)
    return [str(m) for m in missing]


def apply_settings_to_screen(
    page: Page,
    url: str,
    screen_name: str,
    settings: Dict[str, Any],
    *,
    keep_browser: bool = True,
) -> bool:
    """지정 화면으로 이동해 JSON 항목설정을 적용·검증·저장합니다. 성공 시 True."""
    page.goto(url, wait_until="domcontentloaded")
    wait_screen_ready(page)
    open_item_settings_popup(page)
    missing = apply_settings_from_json(page, settings, screen_name=screen_name)

    snapshot = capture_item_settings_from_popup(page)
    try:
        verify_popup_matches_json(
            settings, snapshot, missing, screen_name=screen_name
        )
    except ValueError as exc:
        print(f"[경고] {exc}", flush=True)
        wait_for_user_manual_save_in_popup(page, screen_name=screen_name)
        return True

    click_save_in_item_settings_popup(page)
    page.wait_for_timeout(500)
    if not click_save_success_alert_ok(page, timeout_ms=15_000):
        print(f"[경고] {screen_name} 저장 alert OK를 찾지 못했습니다.", flush=True)
    wait_item_settings_popup_closed(page)
    return True


def run_remember_flow(page: Page, config: Dict, *, keep_browser: bool) -> None:
    """기억 대상 화면에서 사용자 저장 후 JSON 기억."""
    goto_remember_list(page, config)
    captured_data = remember_settings_after_user_save(page, config=config)
    merged_data = merge_remember_payload_with_existing(captured_data, config=config)
    path = save_item_settings(merged_data, config=config)
    print(f"[안내] 항목설정 JSON 저장: {path}", flush=True)


def run_apply_flow(
    page: Page,
    config: Dict,
    screen_ids: List[int],
    settings: Dict[str, Any],
    *,
    keep_browser: bool,
) -> None:
    """선택한 화면에 JSON 항목설정을 일괄 적용합니다."""
    screens = build_apply_screen_urls(config)
    for sid in screen_ids:
        name, url = screens[sid]
        apply_settings_to_screen(
            page, url, name, settings, keep_browser=keep_browser
        )


def goto_remember_list(page: Page, config: Dict) -> None:
    """JSON 기억(m/ㅡ)용 기준 화면으로 이동합니다."""
    if is_overseas_scope(config):
        url = config["intl_order_list_url"]
    else:
        url = config["intg_order_list_url"]
    page.goto(url, wait_until="domcontentloaded")
    wait_screen_ready(page)


def remember_settings_after_user_save(
    page: Page, *, config: Dict | None = None
) -> Dict[str, Any]:
    """항목설정을 열고, 사용자가 [저장]한 뒤 JSON으로 기억할 데이터를 반환합니다."""
    open_item_settings_popup(page)
    _install_user_save_listener(page)
    return wait_for_user_to_click_save(page, config=config)


def ensure_working_page(page: Page, context: BrowserContext) -> Page:
    """닫힌 탭이면 사용 가능한 탭을 찾거나 새로 엽니다."""
    try:
        if page and not page.is_closed():
            return page
    except Exception:
        pass
    for p in context.pages:
        try:
            if not p.is_closed():
                p.bring_to_front()
                return p
        except Exception:
            continue
    try:
        return context.new_page()
    except Exception as exc:
        raise RuntimeError(
            "브라우저 창이 닫혔습니다. "
            "서브메뉴 9 → 메인 7번에서 항목설정(11·21)을 다시 실행해 주세요."
        ) from exc


def run_task(page, context, config, *, keep_browser: bool = False):
    """항목설정 서브메뉴 루프 — m·0·1~8·a 적용 후 반복, 9로 메인메뉴 복귀."""
    config = refresh_config_from_env(config)
    while True:
        page = ensure_working_page(page, context)
        choice = prompt_apply_selection(config)
        lower = choice.strip().lower()

        if lower == SUBMENU_BACK:
            return
        if lower == MAIN_MENU_EXIT:
            raise LauncherExit()

        if not choice.strip():
            continue

        if lower in {"m", "ㅡ"}:
            run_remember_flow(page, config, keep_browser=keep_browser)
            continue

        screen_ids = parse_apply_selection(choice)
        if not screen_ids:
            print(f"[경고] 알 수 없는 선택입니다: {choice!r}", flush=True)
            continue

        settings = load_item_settings(config=config)
        if not settings:
            settings_path = resolve_settings_file(config)
            raise FileNotFoundError(
                f"설정 파일이 없습니다: {settings_path}\n"
                "먼저 m 또는 ㅡ(기억)로 JSON을 저장해 주세요."
            )

        unused, used = _split_settings_sections(settings)
        if not used and not unused:
            raise ValueError("JSON에 미사용·사용 항목이 없습니다.")

        run_apply_flow(
            page, config, screen_ids, settings, keep_browser=keep_browser
        )


def run():
    """로그인 후 항목설정 서브메뉴 실행 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE_DOMESTIC)


if __name__ == "__main__":
    run()
