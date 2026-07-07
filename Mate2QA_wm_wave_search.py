# QA WMS 출고예정·웨이브 — 검색 조건 JSON 저장·적용·WAVE 처리

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import first_visible_locator
from Mate2QA_order_search import capture_selected_order_snos, click_select_all_orders
from Mate2QA_order_step import (
    OutWkOrdProcessingError,
    click_popup_ok_if_visible,
    get_abort_popup_messages,
    wait_out_wk_ord_popups_after_next_step,
)

from Mate2QA_site_config import SEARCH_FILTER_WM_WAVE_FILE

SEARCH_FILTER_FILE = SEARCH_FILTER_WM_WAVE_FILE

OUT_ALLOC_RGST_PATH_FRAGMENT = "outallocrgst.do"
MSG_OUT_ALLOC_RGST_NO_RESULTS = (
    "검색결과가 없어 출고차수 할당을 진행할 수 없습니다."
)


class OutAllocRgstSearchEmptyError(Exception):
    """출고차수할당(outAllocRgst) 화면에서 검색 결과 행이 없을 때."""


def print_out_alloc_rgst_no_results() -> None:
    """출고차수할당 검색 결과 없음 안내를 출력합니다."""
    print(f"[안내] {MSG_OUT_ALLOC_RGST_NO_RESULTS}", flush=True)


MSG_OUT_WK_ORD_NO_RESULTS = (
    "출고작업 목록에서 검색 결과를 찾지 못했습니다. "
    "출고차수명·할당 상태를 확인해 주세요."
)


class OutWkOrdSearchEmptyError(Exception):
    """출고작업(outWkOrdList) 화면에서 검색 결과 행이 없을 때."""


def print_out_wk_ord_no_results() -> None:
    """출고작업 목록 검색 결과 없음 안내를 출력합니다."""
    print(f"[경고] {MSG_OUT_WK_ORD_NO_RESULTS}", flush=True)


DEFAULT_WAVE_PROCESS: Dict[str, str] = {
    "id": "selBoxPackBtn",
    "data_type": "boxPack",
    "data_div": "select",
    "label": "화주 합포장 기준",
}

WAVE_PROCESS_WAIT_MS = 3000

TOTAL_GROUP_BOX_MODAL = "#totalGroupBoxModal.show, #totalGroupBoxModal.in"
BOX_RECOMMEND_ALERT_POLL_MS = 150
BOX_RECOMMEND_ALERT_CLICK_MS = 200

# 단계별 alert OK 자동 클릭 설정입니다.
# True: alert OK 자동 클릭, False: 화면에 남겨두고 사용자가 직접 확인
ALERT_OK_POLICY: Dict[str, bool] = {
    "wave_process": True,
    "address_refine_confirm": True,
    "address_refine_result": True,
    "out_alloc_rgst": False,
    "box_recommend": True,
    "all_picking_instrt": False,
}

# 출고차수할당 화면 분류설비
DIST_PACKING_CD_MANUAL = "HAND"
DIST_PACKING_CD_BOX = "BOX"

# WAVE 팝업: 입수량/입수량+낱개 선택 시 분류설비=생산박스출고
WAVE_PROCESS_BOX_DATA_TYPES = frozenset({"insPack", "insPackEa"})
WAVE_PROCESS_BOX_BTN_IDS = frozenset({"selInsertPackBtn", "selInsertPackEaBtn"})

# 출고예정 searchColumn → 할당 alloc_kwd (value가 다른 경우만)
ALLOC_SRCH_TXT_CANDIDATES = [
    "#srch_txt",
    'input[name="srch_txt"]',
    "#alloc_kwd_txt",
    'input[name="alloc_kwd_txt"]',
]

SEARCH_COLUMN_TO_ALLOC_KWD: Dict[str, str] = {
    "mall_prod_nm": "",
}

# 웨이브 그리드 dlvr_div_cd_nm → 할당 화면 #dlvr_div_cd value
DLVR_DIV_CD_BY_LABEL: Dict[str, str] = {
    "일반배송": "01",
    "도착보장": "03",
    "당일배송": "04",
    "판매자 스타배송": "07",
    "스타배송": "10",
    "오늘출발": "05",
}

EXP_TYPE_DIRECT = "00"  # 직배

# 웨이브 그리드 out_div_cd → 할당 화면 #out_div_cd value
OUT_DIV_CD_BY_LABEL: Dict[str, str] = {
    "B2C": "02",
    "B2B": "01",
}


def _fill_alloc_search_text(page: Page, value: str) -> str:
    """할당 화면 검색어 입력란(#srch_txt 우선)에 값을 넣습니다."""
    loc, sel = first_visible_locator(page, ALLOC_SRCH_TXT_CANDIDATES)
    if not loc:
        raise ValueError(
            "할당 검색어 입력란(#srch_txt / #alloc_kwd_txt)을 찾지 못했습니다."
        )
    loc.evaluate(
        """(el, v) => {
            el.value = v || '';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        value or "",
    )
    return sel


def make_out_tseq_nm(now: datetime | None = None) -> str:
    """출고차수명: J yymmdd hhmm (예: J 260604 1430)."""
    dt = now or datetime.now()
    return f"J {dt.strftime('%y%m%d %H%M')}"


def load_out_tseq_nm() -> Optional[str]:
    """search_filter_wm_wave.json에 저장된 출고차수명을 읽습니다."""
    data = load_wm_wave_filter()
    if not data:
        return None
    value = (data.get("out_tseq_nm") or "").strip()
    return value or None


def read_out_tseq_nm_on_alloc_page(page: Page) -> str:
    """출고차수할당 화면 #out_tseq_nm 현재 값을 읽습니다 (사용자 수정 반영)."""
    loc = page.locator('#out_tseq_nm, input[name="out_tseq_nm"]').first
    loc.wait_for(state="visible", timeout=10_000)
    return (loc.input_value() or "").strip()


def capture_out_tseq_nm_from_alloc_page(page: Page) -> str:
    """할당 화면의 출고차수명을 읽어 JSON에 저장한 뒤 반환합니다."""
    value = read_out_tseq_nm_on_alloc_page(page)
    if value:
        data = load_wm_wave_filter() or {}
        data["out_tseq_nm"] = value
        save_wm_wave_filter(data)
    return value


# JSON 저장 시 이전 값을 유지할 필드 (출고예정 캡처 등으로 덮어쓰기 방지)
_PRESERVED_FILTER_KEYS = (
    "out_tseq_nm",
    "out_div_cd",
    "dlvr_div_cd_nm",
    "wave_process",
)


def _merge_preserved_filter_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """기존 JSON에 있던 출고차수명·웨이브 선택 등을 새 data에 보존합니다."""
    existing = load_wm_wave_filter() or {}
    for key in _PRESERVED_FILTER_KEYS:
        if existing.get(key) is not None and key not in data:
            data[key] = existing[key]
    return data


def _handle_alert_ok_by_policy(
    page: Page,
    policy_key: str,
    label: str,
    *,
    timeout_ms: int = 5000,
    max_attempts: int = 1,
    required: bool = False,
) -> bool:
    """단계별 설정에 따라 alert OK를 자동 클릭하거나 수동 확인으로 남깁니다."""
    auto_click = ALERT_OK_POLICY.get(policy_key, False)
    watch_abort = bool(get_abort_popup_messages())
    if not auto_click and not watch_abort:
        return False

    clicked = False
    for attempt in range(1, max_attempts + 1):
        wait_ms = timeout_ms if attempt == 1 else min(timeout_ms, 3000)
        try:
            if not click_popup_ok_if_visible(page, wait_ms):
                break
        except OutWkOrdProcessingError:
            raise
        clicked = True
        if watch_abort and not auto_click:
            break

    if required and not clicked:
        raise ValueError(f"{label} alert에서 OK 버튼을 찾지 못했습니다.")
    if not clicked:
        pass
    return clicked


def resolve_out_tseq_nm() -> str:
    """JSON에서 출고차수명을 읽고, 없으면 터미널 입력을 받아 저장합니다."""
    value = load_out_tseq_nm()
    if value:
        return value

    print("[경고] search_filter_wm_wave.json에 out_tseq_nm이 없습니다.")
    print(
        "       Mate2QA_WmMovetoAlloc 실행 시 자동 저장되거나, "
        "아래에 할당 단계에서 사용한 출고차수명을 입력할 수 있습니다."
    )
    try:
        value = input("출고차수명 입력 (예: J 260604 1341): ").strip()
    except EOFError:
        value = ""
    if not value:
        raise ValueError(
            "출고차수명(out_tseq_nm)이 없습니다. "
            "Mate2QA_WmMovetoAlloc을 먼저 실행하거나 출고차수명을 입력해 주세요."
        )

    data = load_wm_wave_filter() or {}
    data["out_tseq_nm"] = value
    save_wm_wave_filter(data)
    return value


def load_wm_wave_filter() -> Optional[Dict[str, Any]]:
    """search_filter_wm_wave.json을 읽습니다. 없으면 None."""
    if not SEARCH_FILTER_FILE.exists():
        return None
    with SEARCH_FILTER_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def save_wm_wave_filter(data: Dict[str, Any]) -> None:
    """WMS 웨이브 검색·선택 정보를 JSON에 저장합니다."""
    with SEARCH_FILTER_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _set_input_value(page: Page, selector: str, value: str) -> None:
    """daterange·검색어 입력란에 값을 넣습니다."""
    loc = page.locator(selector).first
    if loc.count() == 0:
        raise ValueError(f"입력란을 찾지 못했습니다: {selector}")
    loc.evaluate(
        """(el, v) => {
            el.value = v || '';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        value or "",
    )


def capture_wm_wave_filter_from_page(page: Page) -> Dict[str, Any]:
    """출고예정 화면의 검색 조건·선택 주문(od_sno)을 읽어 JSON에 저장합니다."""
    try:
        page.locator("#searchDateRange").wait_for(state="visible", timeout=15_000)
        page.locator("#searchColumn").wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "출고예정 검색 폼을 찾지 못했습니다. "
            "화주가 선택되었는지, WMS 출고예정 화면인지 확인해 주세요."
        ) from exc

    existing = load_wm_wave_filter() or {}
    data: Dict[str, Any] = {
        "search_date_range": page.locator("#searchDateRange").input_value(),
        "sach_cd": page.locator("#sach_cd").input_value(),
        "search_column": page.locator("#searchColumn").input_value(),
        "srch_txt": page.locator("#srch_txt").input_value(),
        "selected_od_snos": capture_selected_order_snos(page),
    }
    data = _merge_preserved_filter_fields(data)
    save_wm_wave_filter(data)
    if data["selected_od_snos"]:
        pass
    else:
        print("[경고] 체크된 주문이 없습니다. WAVE 처리 전에 주문을 선택해 주세요.")
    return data


def fill_wm_wave_search(page: Page, filter_data: Dict[str, Any]) -> None:
    """저장된 날짜·채널·검색컬럼·검색어를 화면에 반영합니다."""
    _set_input_value(page, "#searchDateRange", filter_data.get("search_date_range", ""))

    sach = filter_data.get("sach_cd", "")
    if sach:
        page.select_option("#sach_cd", value=sach)
    else:
        page.select_option("#sach_cd", value="")

    search_column = (filter_data.get("search_column") or "").strip()
    srch_txt = (filter_data.get("srch_txt") or "").strip()

    # 검색어가 비어 있으면 선택된 od_sno로 대체 (하위 호환)
    if not srch_txt:
        snos = filter_data.get("selected_od_snos") or []
        if snos:
            search_column = "od_sno"
            srch_txt = ";".join(snos)

    if search_column:
        page.select_option("#searchColumn", value=search_column)
    _set_input_value(page, "#srch_txt", srch_txt)


def click_wm_search_button(page: Page) -> None:
    """WMS 목록 검색(button#searchBtn)을 클릭합니다."""
    btn = page.locator("#searchBtn").first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)


def wait_wm_search_grid(page: Page, timeout_ms: int = 30_000) -> None:
    """Tabulator 그리드가 보일 때까지 대기합니다."""
    page.locator(".tabulator-row").first.wait_for(state="visible", timeout=timeout_ms)


def _wm_search_grid_row_count(page: Page) -> int:
    """현재 화면 Tabulator 데이터 행 수를 반환합니다."""
    try:
        return int(
            page.evaluate(
                "() => document.querySelectorAll('.tabulator-row').length"
            )
            or 0
        )
    except Exception:
        return 0


def _is_out_alloc_rgst_page(page: Page) -> bool:
    return OUT_ALLOC_RGST_PATH_FRAGMENT in (page.url or "").lower()


def ensure_alloc_rgst_has_search_results(
    page: Page, timeout_ms: int = 30_000
) -> None:
    """출고차수할당 검색 후 그리드 행이 생길 때까지 대기합니다. 없으면 중단 예외를 냅니다."""
    if not _is_out_alloc_rgst_page(page):
        wait_wm_search_grid(page, timeout_ms=timeout_ms)
        return

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if _wm_search_grid_row_count(page) > 0:
            return
        page.wait_for_timeout(500)

    raise OutAllocRgstSearchEmptyError(MSG_OUT_ALLOC_RGST_NO_RESULTS)


def select_orders_by_od_sno(page: Page, od_snos: List[str]) -> None:
    """검색 결과 그리드에서 저장된 od_sno와 일치하는 행 체크박스를 선택합니다.

    웨이브 목록에 없는 od_sno(수량 불일치 등)는 경고만 출력하고, 찾은 건만 선택합니다.
    """
    targets = [str(s).strip() for s in od_snos if str(s).strip()]
    if not targets:
        raise ValueError("선택할 od_sno 목록이 비어 있습니다.")

    wait_wm_search_grid(page)
    result = page.evaluate(
        """(snos) => {
            const targets = new Set(snos);
            const found = [];
            const rows = document.querySelectorAll('.tabulator-row');
            for (const row of rows) {
                const field = row.querySelector('[tabulator-field="od_sno"]');
                let text = field ? (field.innerText || '').trim() : '';
                if (!text) {
                    for (const cell of row.querySelectorAll('.tabulator-cell')) {
                        const t = (cell.innerText || '').trim();
                        if (/^\\d{6,}$/.test(t)) { text = t; break; }
                    }
                }
                if (!targets.has(text)) continue;
                const cb = row.querySelector(
                    'input[type="checkbox"][aria-label="Select Row"], input[type="checkbox"]'
                );
                if (cb && !cb.checked) cb.click();
                if (cb && cb.checked) found.push(text);
            }
            const missing = snos.filter(s => !found.includes(s));
            return { found, missing };
        }""",
        targets,
    )
    page.wait_for_timeout(400)

    found = result.get("found") or []
    missing = result.get("missing") or []
    if missing:
        print(
            f"[경고] 웨이브 목록에서 od_sno {len(missing)}건을 찾지 못했습니다: "
            f"{';'.join(missing)}",
            flush=True,
        )


def capture_wave_selected_row_context(
    page: Page, filter_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """웨이브 목록: 선택된 첫 번째 행의 out_div_cd·dlvr_div_cd_nm을 JSON에 저장합니다."""
    wait_wm_search_grid(page)
    ctx = page.evaluate(
        """() => {
            const rows = document.querySelectorAll('.tabulator-row');
            for (const row of rows) {
                const cb = row.querySelector(
                    'input[type="checkbox"][aria-label="Select Row"], input[type="checkbox"]'
                );
                if (!cb || !cb.checked) continue;
                const outDiv = row.querySelector('[tabulator-field="out_div_cd"]');
                const dlvr = row.querySelector('[tabulator-field="dlvr_div_cd_nm"]');
                return {
                    out_div_cd: outDiv ? (outDiv.innerText || '').trim() : '',
                    dlvr_div_cd_nm: dlvr ? (dlvr.innerText || '').trim() : '',
                };
            }
            return { out_div_cd: '', dlvr_div_cd_nm: '' };
        }"""
    )
    data = dict(filter_data or load_wm_wave_filter() or {})
    data["out_div_cd"] = str(ctx.get("out_div_cd") or "").strip()
    data["dlvr_div_cd_nm"] = str(ctx.get("dlvr_div_cd_nm") or "").strip()
    save_wm_wave_filter(data)
    return data


def is_dlvr_div_empty(filter_data: Dict[str, Any]) -> bool:
    """배송구분(dlvr_div_cd_nm)이 비어 있는지 확인합니다."""
    return not (filter_data.get("dlvr_div_cd_nm") or "").strip()


def _set_out_div_cd_on_alloc(page: Page, filter_data: Dict[str, Any]) -> None:
    """할당 화면 #out_div_cd(B2C/B2B) 선택 — 이후 #dlvr_div_cd 옵션이 로드됩니다."""
    out_div = (filter_data.get("out_div_cd") or "").strip().upper()
    if not out_div:
        return
    out_sel = page.locator("#out_div_cd").first
    if out_sel.count() == 0:
        return
    out_value = OUT_DIV_CD_BY_LABEL.get(out_div)
    if out_value:
        page.select_option("#out_div_cd", value=out_value)
    else:
        page.select_option("#out_div_cd", label=out_div)
    page.wait_for_timeout(500)


def _wait_dlvr_div_cd_options(page: Page, timeout_ms: int = 10_000) -> None:
    """#out_div_cd 선택 후 #dlvr_div_cd 옵션이 채워질 때까지 대기합니다."""
    page.locator("#dlvr_div_cd option:not([value=''])").first.wait_for(
        state="attached", timeout=timeout_ms
    )


def apply_dlvr_div_or_exp_type(page: Page, filter_data: Dict[str, Any]) -> None:
    """할당 화면: out_div_cd → dlvr_div_cd 또는 exp_type(직배) 설정."""
    _set_out_div_cd_on_alloc(page, filter_data)

    dlvr_nm = (filter_data.get("dlvr_div_cd_nm") or "").strip()
    if not dlvr_nm:
        page.locator("#exp_type").wait_for(state="visible", timeout=10_000)
        page.select_option("#exp_type", value=EXP_TYPE_DIRECT)
        return

    dlvr_sel = page.locator("#dlvr_div_cd").first
    if dlvr_sel.count() == 0:
        return

    try:
        _wait_dlvr_div_cd_options(page)
    except PlaywrightTimeoutError:
        if not (filter_data.get("out_div_cd") or "").strip():
            raise ValueError(
                "배송구분 옵션을 불러오지 못했습니다. "
                "웨이브 목록에서 out_div_cd(B2C/B2B)가 선택 행에 있는지 확인해 주세요."
            ) from None
        raise ValueError(
            f"배송구분 옵션을 불러오지 못했습니다. dlvr_div_cd_nm={dlvr_nm}"
        ) from None

    dlvr_value = DLVR_DIV_CD_BY_LABEL.get(dlvr_nm)
    try:
        if dlvr_value:
            dlvr_sel.select_option(value=dlvr_value)
        else:
            dlvr_sel.select_option(label=dlvr_nm)
    except PlaywrightTimeoutError:
        dlvr_sel.select_option(label=dlvr_nm)


def apply_wm_wave_search(
    page: Page,
    filter_data: Optional[Dict[str, Any]] = None,
    *,
    wait_grid: bool = True,
    select_orders: bool = False,
) -> None:
    """저장된 검색 조건으로 WMS 목록을 조회합니다."""
    data = filter_data or load_wm_wave_filter()
    if not data:
        raise ValueError(
            "출고예정 화면에서 검색 조건을 저장하지 못했습니다. "
            "날짜·채널 설정 → 「검색」 → 주문 체크 → Enter 순서로 진행해 주세요."
        )
    fill_wm_wave_search(page, data)
    click_wm_search_button(page)
    if wait_grid:
        try:
            wait_wm_search_grid(page)
        except PlaywrightTimeoutError:
            return
    if select_orders:
        select_orders_by_od_sno(page, data.get("selected_od_snos") or [])


def _install_wave_process_click_listener(page: Page) -> None:
    """WAVE 선택 팝업(button.waveProcess) 클릭을 document에서 감지합니다."""
    page.evaluate(
        """() => {
            window.__wmWaveChoice = null;
            if (window.__wmWaveClickHandler) {
                document.removeEventListener('click', window.__wmWaveClickHandler, true);
            }
            window.__wmWaveClickHandler = (event) => {
                const btn = event.target.closest('button.waveProcess');
                if (!btn) return;
                window.__wmWaveChoice = {
                    id: btn.id || '',
                    data_type: btn.dataset.type || '',
                    data_div: btn.dataset.div || '',
                    label: (btn.innerText || '').trim().replace(/\\s+/g, ' ')
                };
            };
            document.addEventListener('click', window.__wmWaveClickHandler, true);
        }"""
    )


def _wait_for_user_wave_process_choice(
    page: Page, wait_ms: int = WAVE_PROCESS_WAIT_MS, poll_ms: int = 200
) -> Optional[Dict[str, str]]:
    """wait_ms 동안 사용자 WAVE 선택 클릭을 기다립니다. 없으면 None."""
    elapsed = 0
    while elapsed < wait_ms:
        choice = _read_wave_process_choice(page)
        if choice and choice.get("id"):
            return choice
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    return None


def _read_wave_process_choice(page: Page) -> Optional[Dict[str, str]]:
    """사용자가 직접 클릭한 합포장 기준 정보를 읽습니다."""
    choice = page.evaluate("() => window.__wmWaveChoice")
    if not choice or not isinstance(choice, dict):
        return None
    return {
        "id": str(choice.get("id") or "").strip(),
        "data_type": str(choice.get("data_type") or "").strip(),
        "data_div": str(choice.get("data_div") or "").strip(),
        "label": str(choice.get("label") or "").strip(),
    }


def _save_wave_process_choice(
    filter_data: Optional[Dict[str, Any]], choice: Dict[str, str]
) -> Dict[str, Any]:
    """합포장 기준 선택값을 filter_data·JSON에 저장합니다."""
    data = dict(filter_data or load_wm_wave_filter() or {})
    data["wave_process"] = choice
    save_wm_wave_filter(data)
    return data


def _click_wave_process_button(page: Page, choice: Dict[str, str]) -> None:
    """저장된 id(또는 data-type)로 합포장 기준 버튼을 클릭합니다."""
    btn_id = choice.get("id") or DEFAULT_WAVE_PROCESS["id"]
    btn = page.locator(f"#{btn_id}").first
    if btn.count() > 0 and btn.is_visible():
        btn.click()
        return

    data_type = choice.get("data_type") or DEFAULT_WAVE_PROCESS["data_type"]
    fallback = page.locator(f'button.waveProcess[data-type="{data_type}"]').first
    if fallback.count() > 0 and fallback.is_visible():
        fallback.click()
        return

    label = choice.get("label") or DEFAULT_WAVE_PROCESS["label"]
    text_btn = page.locator(f'button.waveProcess:has-text("{label}")').first
    if text_btn.count() > 0 and text_btn.is_visible():
        text_btn.click()
        return

    raise ValueError(
        f"합포장 기준 버튼을 찾지 못했습니다. id={btn_id}, type={data_type}, label={label}"
    )


def run_wave_process_on_expect_list(
    page: Page,
    filter_data: Optional[Dict[str, Any]] = None,
    *,
    wait_ms: int = WAVE_PROCESS_WAIT_MS,
) -> Dict[str, Any]:
    """출고예정: WAVE 클릭 후 3초 대기, 사용자 미선택 시에만 화주 합포장 기준 자동 클릭."""
    wave_btn = page.locator("#doWavePorc").first
    wave_btn.wait_for(state="visible", timeout=10_000)
    wave_btn.click()
    page.wait_for_timeout(800)

    page.locator("button.waveProcess").first.wait_for(state="visible", timeout=15_000)
    _install_wave_process_click_listener(page)

    wait_sec = wait_ms / 1000

    user_choice = _wait_for_user_wave_process_choice(page, wait_ms)

    if user_choice:
        data = _save_wave_process_choice(filter_data, user_choice)
    else:
        default_choice = dict(DEFAULT_WAVE_PROCESS)
        box_btn = page.locator("#selBoxPackBtn").first
        if not box_btn.is_visible():
            raise ValueError(
                "3초 대기 후에도 WAVE 선택이 없고 #selBoxPackBtn이 보이지 않습니다. "
                "팝업 상태를 확인해 주세요."
            )
        box_btn.click()
        data = _save_wave_process_choice(filter_data, default_choice)

    page.wait_for_timeout(500)
    _handle_alert_ok_by_policy(
        page,
        "wave_process",
        "WAVE 처리",
        timeout_ms=5000,
        max_attempts=3,
    )
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    return data


def click_address_refine(page: Page) -> None:
    """웨이브 목록: 주소 정제 드롭다운 → 항목 선택 → 확인·결과 alert OK."""
    dropdown_candidates = [
        'button.dropdown-toggle:has-text("주소 정제")',
        'button.bg-success.dropdown-toggle:has-text("주소")',
        'button[data-toggle="dropdown"]:has-text("주소")',
    ]
    dropdown, dropdown_sel = first_visible_locator(page, dropdown_candidates)
    if not dropdown:
        raise ValueError("「주소 정제」 드롭다운 버튼을 찾지 못했습니다.")
    dropdown.click()
    page.wait_for_timeout(500)

    refine_btn = page.locator("#selectAddrRefineBtn").first
    refine_btn.wait_for(state="visible", timeout=10_000)
    refine_btn.click()
    page.wait_for_timeout(500)

    _handle_alert_ok_by_policy(
        page,
        "address_refine_confirm",
        "주소 정제 확인",
        timeout_ms=15_000,
        required=True,
    )

    page.wait_for_timeout(800)
    _handle_alert_ok_by_policy(
        page,
        "address_refine_result",
        "주소 정제 결과",
        timeout_ms=30_000,
        required=True,
    )


def click_out_alloc_assign(page: Page, alloc_url: str) -> None:
    """웨이브 목록에서 「출고차수 할당」(#outAllocBtn) 클릭 후 할당 등록 화면으로 이동합니다."""
    btn = page.locator("#outAllocBtn").first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    if "outAllocRgst.do" not in page.url and alloc_url not in page.url:
        page.goto(alloc_url, wait_until="domcontentloaded")
        page.wait_for_timeout(800)


def _resolve_alloc_search(filter_data: Dict[str, Any]) -> tuple[str, str]:
    """할당 화면용 (alloc_kwd, srch_txt) 값을 만듭니다."""
    srch_txt = (filter_data.get("srch_txt") or "").strip()

    if not srch_txt:
        snos = filter_data.get("selected_od_snos") or []
        if not snos:
            return "", ""
        return "od_sno", ";".join(str(s).strip() for s in snos if str(s).strip())

    search_column = (filter_data.get("search_column") or "").strip()
    alloc_kwd = SEARCH_COLUMN_TO_ALLOC_KWD.get(search_column, search_column)
    return alloc_kwd, srch_txt


def _resolve_dist_packing_cd(filter_data: Dict[str, Any]) -> tuple[str, str]:
    """WAVE 선택에 따라 할당 화면 #dist_packing_cd value·라벨을 반환합니다."""
    wave = filter_data.get("wave_process") or {}
    data_type = (wave.get("data_type") or "").strip()
    btn_id = (wave.get("id") or "").strip()
    if data_type in WAVE_PROCESS_BOX_DATA_TYPES or btn_id in WAVE_PROCESS_BOX_BTN_IDS:
        return DIST_PACKING_CD_BOX, "생산박스출고"
    return DIST_PACKING_CD_MANUAL, "수동(HAND)"


def fill_out_alloc_rgst_form(page: Page, filter_data: Dict[str, Any]) -> None:
    """출고차수할당 화면: 출고차수명·분류설비·날짜·검색 조건 설정 후 검색합니다."""
    page.locator("#out_tseq_nm").wait_for(state="visible", timeout=10_000)
    out_tseq_nm = make_out_tseq_nm()
    _set_input_value(page, "#out_tseq_nm", out_tseq_nm)
    filter_data["out_tseq_nm"] = out_tseq_nm
    save_wm_wave_filter(filter_data)

    page.locator("#dist_packing_cd").wait_for(state="visible", timeout=10_000)
    dist_value, dist_label = _resolve_dist_packing_cd(filter_data)
    page.select_option("#dist_packing_cd", value=dist_value)
    wave = filter_data.get("wave_process") or {}
    wave_label = (wave.get("label") or wave.get("id") or "화주 합포장 기준").strip()

    apply_dlvr_div_or_exp_type(page, filter_data)

    date_range = filter_data.get("search_date_range", "")
    if date_range:
        _set_input_value(page, "#searchDateRange", date_range)

    alloc_kwd, srch_txt = _resolve_alloc_search(filter_data)
    if alloc_kwd:
        page.select_option("#alloc_kwd", value=alloc_kwd)
    elif (filter_data.get("search_column") or "").strip():


        pass

    if srch_txt:
        used_sel = _fill_alloc_search_text(page, srch_txt)

    click_wm_search_button(page)


def select_all_alloc_rgst_targets(page: Page) -> None:
    """출고할당 대상 그리드 맨 앞 헤더 체크박스로 검색 결과 전체 선택."""
    ensure_alloc_rgst_has_search_results(page)
    click_select_all_orders(page)


def click_out_alloc_rgst_button(page: Page) -> None:
    """할당 등록 화면 「출고차수 할당」(#outAllocBtn) 클릭 후 정책에 따라 alert OK 처리."""
    btn = page.locator("#outAllocBtn").first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_timeout(800)
    _handle_alert_ok_by_policy(
        page,
        "out_alloc_rgst",
        "출고차수 할당",
        timeout_ms=10_000,
    )


def _locate_out_wk_ord_tseq_nm_input(page: Page):
    """(하위 호환) 출고작업 화면 검색어 입력란 #srch_txt."""
    return page.locator("#searchForm #srch_txt, #srch_txt").first


def fill_out_wk_ord_tseq_nm(page: Page, out_tseq_nm: str) -> None:
    """출고작업(outWkOrdList) 화면: 검색구분=출고차수명 + #srch_txt 입력."""
    page.locator("#srch_gubun").wait_for(state="visible", timeout=10_000)
    page.select_option("#srch_gubun", value="out_tseq_nm")
    _set_input_value(page, "#srch_txt", out_tseq_nm)


def click_out_wk_ord_search_button(page: Page) -> None:
    """출고작업 목록 상단 「검색」 버튼을 클릭합니다."""
    btn = page.locator("#searchBtn").first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)


def wait_out_wk_ord_main_grid(page: Page, timeout_ms: int = 30_000) -> None:
    """출고작업 목록(#grid-table) 그리드 행이 보일 때까지 대기합니다."""
    try:
        page.locator("#grid-table .tabulator-row").first.wait_for(
            state="visible", timeout=timeout_ms
        )
    except PlaywrightTimeoutError as exc:
        raise OutWkOrdSearchEmptyError(MSG_OUT_WK_ORD_NO_RESULTS) from exc


def search_out_wk_ord_by_tseq_nm(page: Page, out_tseq_nm: str) -> None:
    """저장된 출고차수명으로 출고작업 목록을 검색합니다."""
    fill_out_wk_ord_tseq_nm(page, out_tseq_nm)
    click_out_wk_ord_search_button(page)
    wait_out_wk_ord_main_grid(page)


def select_out_wk_ord_row_by_tseq_nm(page: Page, out_tseq_nm: str) -> None:
    """검색 결과에서 출고차수명이 일치하는 행을 선택합니다."""
    target = (out_tseq_nm or "").strip()
    if not target:
        raise ValueError("선택할 출고차수명(out_tseq_nm)이 비어 있습니다.")

    wait_out_wk_ord_main_grid(page)
    result = page.evaluate(
        """(outTseqNm) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const target = norm(outTseqNm);
            const grid = document.querySelector('#grid-table');
            if (!grid) return { found: false, tseq_sno: '' };
            for (const row of grid.querySelectorAll('.tabulator-row')) {
                const field = row.querySelector('[tabulator-field="out_tseq_nm"]');
                let text = field ? (field.innerText || '').trim() : '';
                if (!text) {
                    for (const cell of row.querySelectorAll('.tabulator-cell')) {
                        const t = (cell.innerText || '').trim();
                        if (norm(t) === target) { text = t; break; }
                    }
                }
                if (norm(text) !== target) continue;

                row.scrollIntoView({ block: 'center', inline: 'nearest' });
                row.click();

                const hidden = document.querySelector('#selected_out_alloc_tseq_sno');
                const tseqField = row.querySelector('[tabulator-field="out_alloc_tseq_sno"]');
                let tseq_sno = hidden ? (hidden.value || '').trim() : '';
                if (!tseq_sno && tseqField) {
                    tseq_sno = (tseqField.innerText || '').trim();
                }
                return { found: true, tseq_sno };
            }
            return { found: false, tseq_sno: '' };
        }""",
        target,
    )
    page.wait_for_timeout(800)

    if not result.get("found"):
        raise ValueError(
            f"출고작업 목록에서 출고차수명 '{target}' 행을 찾지 못했습니다."
        )

    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)

    tseq_sno = str(result.get("tseq_sno") or "").strip()


def _wait_out_wk_ord_tab3_rows(page: Page, timeout_ms: int = 60_000) -> int:
    """출고지시(#grid-table-tab3) 그리드 행이 생길 때까지 대기합니다."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        count = page.evaluate(
            """() => document.querySelectorAll('#grid-table-tab3 .tabulator-row').length"""
        )
        if count and count > 0:
            return int(count)
        page.wait_for_timeout(500)
    raise PlaywrightTimeoutError(
        f"출고지시 그리드(#grid-table-tab3) 행이 {timeout_ms}ms 안에 나타나지 않았습니다."
    )


def wait_out_wk_ord_tab4_rows(page: Page, timeout_ms: int = 60_000) -> int:
    """피킹지시(#grid-table-tab4) 그리드 행 수를 대기·반환합니다. 없으면 0."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        count = page.evaluate(
            """() => {
                const selectors = [
                    '#grid-table-tab4 .tabulator-row',
                    '#tab_borders_icons-4 .tabulator-row',
                ];
                for (const sel of selectors) {
                    const n = document.querySelectorAll(sel).length;
                    if (n > 0) return n;
                }
                return 0;
            }"""
        )
        if count and count > 0:
            return int(count)
        page.wait_for_timeout(500)
    return 0


def click_out_instruction_tab(page: Page) -> None:
    """「출고지시」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "출고지시 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-3"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab3 === 'function') {
                grid_table_tab3(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    page.locator("#tab_borders_icons-3.active").wait_for(
        state="attached", timeout=10_000
    )


def click_out_picking_tab(page: Page) -> None:
    """「피킹지시」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "피킹지시 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-4"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab4 === 'function') {
                grid_table_tab4(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    page.locator("#tab_borders_icons-4.active").wait_for(
        state="attached", timeout=10_000
    )


def click_out_wk_ord_instruction_tab(page: Page) -> None:
    """출고상세 그리드 「출고지시」 탭 데이터를 로드합니다."""
    click_out_instruction_tab(page)
    _wait_out_wk_ord_tab3_rows(page)


def click_packing_instruction_tab(page: Page) -> None:
    """「포장지시」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "포장지시 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-5"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab === 'function') {
                grid_table_tab(sno, 'pk');
            } else if (typeof grid_table_tab5 === 'function') {
                grid_table_tab5(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    page.locator("#tab_borders_icons-5.tab-pane.active.show").wait_for(
        state="visible", timeout=10_000
    )


def click_out_confirm_tab(page: Page) -> None:
    """「출고확정」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "출고확정 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-8"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab8 === 'function') {
                grid_table_tab8(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    page.locator("#tab_borders_icons-8.active").wait_for(
        state="attached", timeout=10_000
    )


def click_out_complete_tab(page: Page) -> None:
    """「출고완료」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "출고완료 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-9"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab9 === 'function') {
                grid_table_tab9(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    page.locator("#tab_borders_icons-9.active").wait_for(
        state="attached", timeout=10_000
    )


def ensure_out_wk_ord_row_selected(page: Page) -> None:
    """출고작업 목록에서 첫 번째 행을 선택해 출고 실행 영역을 엽니다."""
    try:
        wait_out_wk_ord_main_grid(page)
    except OutWkOrdSearchEmptyError as exc:
        raise ValueError(
            "출고작업 목록에 검색 결과가 없습니다. "
            "목록에 출고차수 데이터를 준비해 주세요."
        ) from exc

    first_row = page.locator("#grid-table .tabulator-row").first
    first_row.wait_for(state="visible", timeout=10_000)
    first_row.scroll_into_view_if_needed()
    first_row.click()
    page.wait_for_timeout(800)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 첫 행 선택 후 #selected_out_alloc_tseq_sno가 비어 있습니다."
        )
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)


def click_box_recommend_dropdown(page: Page) -> None:
    """출고지시 영역 「박스추천」(#boxRecommandBtn) 드롭다운을 클릭합니다."""
    btn = page.locator("#boxRecommandBtn").first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_timeout(400)


def click_total_box_recommend_btn(page: Page) -> None:
    """박스추천 메뉴 「전체박스 추천 실행」(#totalBoxRecommendBtn) 버튼만 클릭합니다."""
    menu = page.locator("#totalBoxRecommendBtn").first
    menu.wait_for(state="visible", timeout=10_000)
    menu.click()
    page.wait_for_timeout(300)


def _is_group_box_modal_visible(page: Page) -> bool:
    """그룹 박스 선택 모달이 보이는지 확인합니다."""
    modal = page.locator(TOTAL_GROUP_BOX_MODAL).first
    return modal.count() > 0 and modal.is_visible()


def _click_group_box_modal_confirm(page: Page) -> bool:
    """그룹 박스 선택 모달의 확인 버튼을 클릭합니다."""
    if not _is_group_box_modal_visible(page):
        return False
    confirm = page.locator("#totalGroupBoxConfirmBtn").first
    if confirm.count() == 0 or not confirm.is_visible():
        return False
    confirm.click()
    page.wait_for_timeout(300)
    return True


def _close_group_box_modal_if_open(page: Page) -> None:
    """열려 있는 그룹 박스 선택 모달을 닫습니다."""
    if not _is_group_box_modal_visible(page):
        return
    try:
        page.locator(TOTAL_GROUP_BOX_MODAL).first.wait_for(state="hidden", timeout=5_000)
    except PlaywrightTimeoutError:
        close_btn = page.locator(
            '#totalGroupBoxModal button:has-text("닫기"), #totalGroupBoxModal .close'
        ).first
        if close_btn.count() and close_btn.is_visible():
            close_btn.click()
            page.wait_for_timeout(300)


def _handle_box_recommend_alerts(page: Page, *, max_wait_ms: int = 20_000) -> None:
    """박스추천 확인·완료 alert와 그룹 박스 모달을 빠르게 처리합니다."""
    deadline = time.monotonic() + max_wait_ms / 1000
    actions = 0
    last_action_at = 0.0
    quiet_after_ms = 2500

    while time.monotonic() < deadline:
        acted = False
        try:
            if click_popup_ok_if_visible(
                page,
                timeout_ms=BOX_RECOMMEND_ALERT_CLICK_MS,
                settle_ms=250,
                poll_ms=BOX_RECOMMEND_ALERT_POLL_MS,
            ):
                acted = True
        except OutWkOrdProcessingError:
            raise

        if not acted and _click_group_box_modal_confirm(page):
            acted = True

        if acted:
            actions += 1
            last_action_at = time.monotonic()
            continue

        if actions > 0 and (time.monotonic() - last_action_at) * 1000 >= quiet_after_ms:
            break

        page.wait_for_timeout(BOX_RECOMMEND_ALERT_POLL_MS)

    _close_group_box_modal_if_open(page)


def click_total_box_recommend(page: Page) -> None:
    """박스추천 메뉴 「전체박스 추천 실행」 클릭 후 모달·alert까지 처리합니다."""
    click_total_box_recommend_btn(page)
    _handle_box_recommend_alerts(page)


def click_out_wk_ord_next_step_dropdown(page: Page) -> None:
    """출고지시 영역 「다음 단계」 드롭다운을 클릭합니다."""
    next_candidates = [
        '#out_exec_view button.dropdown-toggle.bg-info:has-text("다음 단계")',
        '#out_exec_view button.dropdown-toggle:has-text("다음 단계")',
        'button.dropdown-toggle.bg-info:has-text("다음 단계")',
    ]
    btn, sel = first_visible_locator(page, next_candidates)
    if not btn:
        raise ValueError("「다음 단계」 드롭다운 버튼을 찾지 못했습니다.")
    btn.click()
    page.wait_for_timeout(400)


def click_all_picking_instrt(page: Page) -> None:
    """다음 단계 메뉴 「전체 다음단계」(#all_picking_instrt)를 클릭 후 alert를 처리합니다."""
    menu = page.locator("#all_picking_instrt").first
    menu.wait_for(state="visible", timeout=10_000)
    menu.click()
    page.wait_for_timeout(800)
    wait_out_wk_ord_popups_after_next_step(page)


def run_out_wk_ord_box_recommend_and_next_step(page: Page) -> None:
    """출고지시: 박스추천 → 전체박스 추천 → 다음 단계 → 전체 다음단계."""
    click_box_recommend_dropdown(page)
    click_total_box_recommend(page)
    page.wait_for_timeout(2000)
    click_out_wk_ord_next_step_dropdown(page)
    click_all_picking_instrt(page)
