# Mate2QA — 항목설정(#setItemBtn) JSON 기억·화면별 적용 (런처 8번)
#
# 실행: python Mate2QA_setItemBtn.py
# 사이트 URL: Mate2QA_site_config.py (또는 Mate2QA_login.env)

import jsonimport time
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from Mate2QA_login import first_visible_locator
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    refresh_config_from_env,
)

SETTINGS_FILE = PROJECT_DIR / "grid_item_settings.json"

CONFIG = {**_SITE_CONFIG}

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

APPLY_MENU_TEXT = """
------------------------------------------------------------
항목설정 — 적용할 화면을 선택하세요 (JSON: grid_item_settings.json)
m  통합관리 JSON 저장 
a  전체 일괄적용(0 ~ 8)
0  주문발주관리       /  1  주문서처리
2  출고준비           /  3  발송준비
4  발송대기           /  5  배송중
6  배송완료           /  7  통합관리
8  출고보류           /  9  메인메뉴 복귀

※ 복수 선택: 123 → 1·2·3번 순서대로 적용
------------------------------------------------------------
"""

def build_apply_screen_urls(config: Dict) -> Dict[int, tuple[str, str]]:
    """화면 번호 → (표시명, URL)"""
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
    if text == "m":
        return []
    ids: List[int] = []
    for ch in text:
        if not ch.isdigit():
            continue
        num = int(ch)
        if 0 <= num <= 8 and num not in ids:
            ids.append(num)
    return ids


def prompt_apply_selection() -> str:
    """적용/기억 서브메뉴 입력을 받습니다."""
    print(APPLY_MENU_TEXT, flush=True)
    try:
        return input("선택 입력 (0~9 / a / m / 123): ").strip()
    except EOFError:
        return "9"


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


def _pull_user_saved_capture(page: Page) -> Dict[str, Any] | None:
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
        page, raw.get("unused") or [], raw.get("used") or []
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
                "다시 8번을 실행하고 [저장]을 눌러 주세요."
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


def wait_for_user_to_click_save(page: Page, timeout_ms: int = 600_000) -> Dict[str, Any]:
    """사용자가 [저장]을 누를 때까지 대기하고, 저장 직전 팝업 설정을 읽습니다."""
    pop = page.locator(SET_ITEM_POP).first
    if not pop.is_visible():
        raise ValueError("항목설정 팝업이 열려 있지 않습니다.")

    _wait_for_user_save_click(page, timeout_ms=timeout_ms)

    captured = _pull_user_saved_capture(page)
    if captured is None and pop.is_visible():
        captured = capture_item_settings_from_popup(page)

    if captured is None:
        raise ValueError(
            "저장 직후 항목설정을 읽지 못했습니다. "
            "다시 8번을 실행해 주세요."
        )

    _complete_save_after_user_click(page)
    return captured


def _normalize_column_list(
    columns: List[Dict[str, Any]], *, expsr_yn: str
) -> List[Dict[str, Any]]:
    """항목 목록에 구역별 순서(order)와 expsr_yn을 맞춥니다."""
    normalized: List[Dict[str, Any]] = []
    for idx, col in enumerate(columns, start=1):
        width = col.get("width")
        normalized.append(
            {
                "order": idx,
                "grid_itm_sno": str(col.get("grid_itm_sno") or "").strip(),
                "label": str(col.get("label") or "").strip(),
                "expsr_yn": expsr_yn,
                "width": width if width is None else int(width),
            }
        )
    return normalized


def build_settings_payload(
    page: Page,
    unused_raw: List[Dict[str, Any]],
    used_raw: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """미사용 → 사용 순서로 구분된 JSON 구조를 만듭니다."""
    return {
        "screen": "intg_manage",
        "url": page.url,
        "미사용": _normalize_column_list(unused_raw, expsr_yn="N"),
        "사용": _normalize_column_list(used_raw, expsr_yn="Y"),
    }


def capture_item_settings_from_popup(page: Page) -> Dict[str, Any]:
    """열린 항목설정 팝업에서 미사용·사용 항목을 순서대로 읽습니다."""
    unused_raw = _read_board_items(page, "leftBoard")
    used_raw = _read_board_items(page, "rightBoard")
    return build_settings_payload(page, unused_raw, used_raw)


def save_item_settings(data: Dict[str, Any]) -> Path:
    """캡처한 항목설정을 JSON 파일로 저장합니다."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return SETTINGS_FILE


def load_item_settings() -> Dict[str, Any] | None:
    """저장된 항목설정 JSON을 읽습니다. 없으면 None."""
    if not SETTINGS_FILE.exists():
        return None
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _split_settings_sections(
    data: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """저장 JSON에서 미사용·사용 목록을 읽습니다 (구·신 형식 모두 지원)."""
    if "미사용" in data or "사용" in data:
        return data.get("미사용") or [], data.get("사용") or []
    return data.get("unused_columns") or [], data.get("used_columns") or []


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
    """적용용 payload — sno·label·labels·width."""
    out: List[Dict[str, Any]] = []
    for col in columns:
        sno = str(col.get("grid_itm_sno") or "").strip()
        labels = _column_label_keys(col)
        if not sno and not labels:
            continue
        primary = _column_primary_label(col)
        out.append(
            {
                "grid_itm_sno": sno,
                "label": primary,
                "labels": labels,
                "width": col.get("width"),
            }
        )
    return out


def _label_key(label: str) -> str:
    """항목명 비교용 — 공백 제거."""
    return "".join(str(label or "").split())


def _column_label_keys(col: Dict[str, Any]) -> List[str]:
    """항목의 label·labels 후보를 정규화해 반환합니다 (순서 유지, 중복 제거)."""
    keys: List[str] = []
    seen: set[str] = set()
    raw = col.get("labels")
    if isinstance(raw, list) and raw:
        candidates = [str(x).strip() for x in raw]
    else:
        candidates = [str(col.get("label") or "").strip()]
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
        raise ValueError(
            f"{prefix}JSON 항목 {len(missing)}개를 팝업에서 찾지 못해 "
            f"JSON과 동일하게 맞출 수 없습니다: {', '.join(missing[:10])}"
            f"{'...' if len(missing) > 10 else ''}"
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
    """통합관리에서 사용자 저장 후 JSON 기억."""
    goto_intg_manage_list(page, config)
    data = remember_settings_after_user_save(page)
    save_item_settings(data)


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


def goto_intg_manage_list(page: Page, config: Dict) -> None:
    """통합관리 화면으로 이동합니다."""
    url = config["intg_order_list_url"]
    page.goto(url, wait_until="domcontentloaded")
    wait_screen_ready(page)


def remember_settings_after_user_save(page: Page) -> Dict[str, Any]:
    """항목설정을 열고, 사용자가 [저장]한 뒤 JSON으로 기억할 데이터를 반환합니다."""
    open_item_settings_popup(page)
    _install_user_save_listener(page)
    data = wait_for_user_to_click_save(page)
    return data


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
            "서브메뉴 9 → 메인메뉴에서 8번을 다시 실행해 주세요."
        ) from exc


def run_task(page, context, config, *, keep_browser: bool = False):
    """항목설정 서브메뉴 루프 — m·0·1~8·a 적용 후 반복, 9로 메인메뉴 복귀."""
    config = refresh_config_from_env(config)
    while True:
        page = ensure_working_page(page, context)
        choice = prompt_apply_selection()
        lower = choice.strip().lower()

        if lower == "9":
            return

        if not choice.strip():
            continue

        if lower == "m":
            run_remember_flow(page, config, keep_browser=keep_browser)
            continue

        screen_ids = parse_apply_selection(choice)
        if not screen_ids:
            print(f"[경고] 알 수 없는 선택입니다: {choice!r}", flush=True)
            continue

        settings = load_item_settings()
        if not settings:
            raise FileNotFoundError(
                f"설정 파일이 없습니다: {SETTINGS_FILE}\n"
                "먼저 m(통합관리 기억)으로 JSON을 저장해 주세요."
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
