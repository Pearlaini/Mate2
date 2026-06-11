# #Mate2QA 공통 모듈 : 검색조건 저장,화주 정보 저장

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import first_visible_locator

from Mate2QA_site_config import SEARCH_FILTER_DOMESTIC_FILE

SEARCH_FILTER_FILE = SEARCH_FILTER_DOMESTIC_FILE

SEARCH_FIELD_KEYS = (
    "search_dtm",
    "search_start_dtm",
    "search_end_dtm",
    "search_sach_cd",
    "search_column",
    "search_txt",
)

# 주문목록·주문서처리·출고준비 공통 검색 버튼 (id=searchBtn, btn-info)
SEARCH_BTN_CANDIDATES = [
    "button#searchBtn.btn-info.btn-sm:has-text('검색')",
    "button#searchBtn.btn-info:has-text('검색')",
    "button#searchBtn:has-text('검색')",
    "button#searchBtn.btn-info.btn-sm",
    "button#searchBtn",
    "#searchBtn",
]

def load_search_filter() -> Optional[Dict[str, Any]]:
    """search_filter_domestic.json을 읽습니다. 없으면 None."""
    if not SEARCH_FILTER_FILE.exists():
        return None
    with SEARCH_FILTER_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def save_search_filter(data: Dict[str, Any]) -> None:
    """검색·화주 설정을 동일 경로에 덮어씁니다."""
    with SEARCH_FILTER_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_default_criteria() -> Dict[str, str]:
    """빈 검색 조건 기본값."""
    return {k: "" for k in SEARCH_FIELD_KEYS}


def _close_datepicker_if_open(page: Page) -> None:
    """열려 있는 날짜 달력 팝업을 닫습니다."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)


def _set_date_input_value(page: Page, selector: str, value: str) -> None:
    """
    날짜 입력란에 값을 넣습니다.
    page.fill()은 포커스 때문에 달력이 열리고 화면이 흔들릴 수 있어 JS로 설정합니다.
    """
    loc = page.locator(selector).first
    if loc.count() == 0:
        raise ValueError(f"날짜 입력란을 찾지 못했습니다: {selector}")

    loc.evaluate(
        """(el, v) => {
            el.value = v || '';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        value or "",
    )
    _close_datepicker_if_open(page)


def capture_selected_order_snos(page: Page) -> List[str]:
    """
    체크된 행에서 주문일련번호(od_sno) 목록을 읽습니다.
    Tabulator 그리드: tabulator-field="od_sno"
    """
    snos: List[str] = page.evaluate(
        """() => {
            const out = [];
            const seen = new Set();
            const boxes = document.querySelectorAll(
                '.tabulator-row input[type="checkbox"][aria-label="Select Row"]:checked, '
                + '.tabulator-row input[type="checkbox"]:checked'
            );
            for (const cb of boxes) {
                const row = cb.closest('.tabulator-row');
                if (!row) continue;
                let text = '';
                const byField = row.querySelector('[tabulator-field="od_sno"]');
                if (byField) {
                    text = (byField.innerText || '').trim();
                }
                if (!text) {
                    const cells = row.querySelectorAll('.tabulator-cell');
                    for (const c of cells) {
                        const t = (c.innerText || '').trim();
                        if (/^\\d{6,}$/.test(t)) { text = t; break; }
                    }
                }
                if (text && !seen.has(text)) {
                    seen.add(text);
                    out.push(text);
                }
            }
            return out;
        }"""
    )
    return snos or []


def build_search_criteria_for_next_page(filter_data: Dict[str, Any]) -> Dict[str, str]:
    """
    주문서처리 목록 등 다음 화면 검색용 criteria.

    주문발주관리 #searchTxt 가 비어 있으면 선택된 주문일련번호(od_sno)로 검색합니다.
    검색어가 있으면 저장된 검색 컬럼·검색어·기간 등을 그대로 사용합니다.
    """
    criteria = dict(filter_data.get("default") or {})
    saved_txt = (criteria.get("search_txt") or "").strip()
    if saved_txt:
        return criteria

    snos = filter_data.get("selected_od_snos") or []
    if snos:
        criteria["search_column"] = "od_sno"
        criteria["search_txt"] = ";".join(snos)
    return criteria


def capture_search_from_page(page: Page) -> Dict[str, str]:
    """주문목록 화면에서 검색 6개 값을 읽습니다."""
    return {
        "search_dtm": page.locator("#searchDtm").input_value(),
        "search_start_dtm": page.locator("#search_start_dtm").input_value(),
        "search_end_dtm": page.locator("#search_end_dtm").input_value(),
        "search_sach_cd": page.locator("#search_sach_cd").input_value(),
        "search_column": page.locator("#searchColumn").input_value(),
        "search_txt": page.locator("#searchTxt").input_value(),
    }


def wait_order_search_form(page: Page, timeout_ms: int = 15_000) -> None:
    """주문발주/주문서처리·출고준비 목록의 검색 영역이 보일 때까지 대기합니다."""
    btn, sel = first_visible_locator(page, SEARCH_BTN_CANDIDATES)
    if not btn:
        raise ValueError(
            "검색 버튼(button#searchBtn)을 찾지 못했습니다. 검색 영역 로딩을 확인해 주세요."
        )
    btn.wait_for(state="visible", timeout=timeout_ms)
    txt_candidates = ['input[name="searchTxt"]', "#searchTxt"]
    txt_loc, _ = first_visible_locator(page, txt_candidates)
    if not txt_loc:
        raise ValueError("searchTxt 입력란을 찾지 못했습니다.")
    txt_loc.wait_for(state="visible", timeout=timeout_ms)


def fill_search_filter(
    page: Page, criteria: Dict[str, str], *, tell_manual_search: bool = True
) -> None:
    """검색 6개 입력란을 채웁니다."""
    page.select_option("#searchDtm", value=criteria.get("search_dtm") or "reg_dtm")
    _set_date_input_value(
        page, "#search_start_dtm", criteria.get("search_start_dtm", "")
    )
    _set_date_input_value(page, "#search_end_dtm", criteria.get("search_end_dtm", ""))
    sach = criteria.get("search_sach_cd", "")
    if sach:
        page.select_option("#search_sach_cd", value=sach)
    else:
        page.select_option("#search_sach_cd", value="")
    col = criteria.get("search_column") or "od_sno"
    page.select_option("#searchColumn", value=col)
    txt_candidates = ['input[name="searchTxt"]', "#searchTxt"]
    txt_loc, txt_sel = first_visible_locator(page, txt_candidates)
    if not txt_loc:
        raise ValueError("searchTxt 입력란을 찾지 못했습니다.")
    txt_loc.fill(criteria.get("search_txt", ""))
    _close_datepicker_if_open(page)
    if tell_manual_search:
        print("[안내] 검색 조건을 입력했습니다. 「검색」 버튼은 직접 눌러 주세요.")
    else:




        pass


def click_search_button(page: Page) -> None:
    """주문 목록 검색(button#searchBtn)을 클릭해 그리드를 조회합니다."""
    btn, sel = first_visible_locator(page, SEARCH_BTN_CANDIDATES)
    if not btn:
        raise ValueError(
            "「검색」 버튼(button#searchBtn.btn-info)을 찾지 못했습니다."
        )
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)
    _close_datepicker_if_open(page)


HEADER_SELECT_ALL = (
    '.tabulator-header input[type="checkbox"], '
    'div.tabulator-col-title input[type="checkbox"]'
)
ROW_CHECKBOX = (
    '.tabulator-row input[type="checkbox"][aria-label="Select Row"], '
    '.tabulator-row input[type="checkbox"]'
)


def click_select_all_orders(page: Page) -> None:
    """검색 후 Tabulator 헤더(.tabulator-col-title) 체크박스로 전체 선택합니다."""
    wait_search_grid(page)

    row_count = page.locator(ROW_CHECKBOX).count()
    if row_count == 0:
        raise ValueError(
            "검색 결과에 선택 가능한 주문 행이 없습니다. "
            "검색 조건·이동 여부를 확인해 주세요."
        )

    header_cb = page.locator(HEADER_SELECT_ALL).first
    try:
        header_cb.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as e:
        raise ValueError(
            "전체 선택 체크박스(.tabulator-header input)를 찾지 못했습니다."
        ) from e

    if not header_cb.is_checked():
        try:
            header_cb.click(force=True)
        except Exception:
            page.evaluate(
                """() => {
                    const el = document.querySelector(
                        '.tabulator-header input[type="checkbox"], '
                        + 'div.tabulator-col-title input[type="checkbox"]'
                    );
                    if (el && !el.checked) el.click();
                }"""
            )
    page.wait_for_timeout(500)

    rows = page.locator(ROW_CHECKBOX)
    total = rows.count()
    checked = sum(1 for i in range(total) if rows.nth(i).is_checked())
    if checked == 0 and total > 0:
        for i in range(total):
            cb = rows.nth(i)
            if not cb.is_checked():
                cb.click(force=True)
        page.wait_for_timeout(300)
        checked = sum(1 for i in range(total) if rows.nth(i).is_checked())


def apply_criteria_and_search(
    page: Page, criteria: Dict[str, str], *, select_all_after: bool = False
) -> None:
    """검색 6개를 채운 뒤 #searchBtn으로 조회하고, 필요 시 전체 선택합니다."""
    wait_order_search_form(page)
    fill_search_filter(page, criteria, tell_manual_search=False)
    click_search_button(page)
    wait_search_grid(page)
    if select_all_after:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                click_select_all_orders(page)
                return
            except ValueError as exc:
                last_error = exc
                if attempt == 3:
                    break
                page.wait_for_timeout(1500 * attempt)
                click_search_button(page)
                wait_search_grid(page, timeout_ms=45_000)
        if last_error:
            raise last_error


def _print_criteria_summary(criteria: Dict[str, str], *, prefix: str = "") -> None:
    """검색 6개 요약을 터미널에 출력합니다."""
    head = f"{prefix} " if prefix else ""


def run_saved_search_on_page(
    page: Page,
    filter_data: Optional[Dict[str, Any]] = None,
    *,
    select_shipper: bool = False,
    select_all_after: bool = True,
) -> None:
    """
    저장된 검색 조건을 화면에 넣고 #searchBtn으로 조회합니다.
    select_all_after=True(기본)이면 검색 직후 헤더 체크박스로 전체 선택합니다.
    주문 이동 후 재검색 시에는 select_shipper=False(기본)로 화주를 다시 고르지 않습니다.
    """
    data = filter_data or load_search_filter()
    if not data or "default" not in data:
        raise ValueError(
            "주문목록에서 검색 조건을 저장하지 못했습니다. "
            "6개 설정 → 「검색」 클릭 → Enter 순서로 다시 진행해 주세요."
        )

    criteria = build_search_criteria_for_next_page(data)
    saved_txt = ((data.get("default") or {}).get("search_txt") or "").strip()
    snos = data.get("selected_od_snos") or []
    if saved_txt:
        pass
    elif snos:
        pass
    else:
        pass
    _print_criteria_summary(criteria)

    wait_order_search_form(page)
    if select_shipper:
        shipper_label = data.get("shipper_label", "")
        select_shipper_if_configured(page, shipper_label)
        if shipper_label:
            page.wait_for_timeout(600)
    else:

        pass

    apply_criteria_and_search(page, criteria, select_all_after=select_all_after)
    if select_all_after:
        pass
    else:


        pass


# 하위 호환 alias
apply_search_filter = fill_search_filter


def wait_search_grid(page: Page, timeout_ms: int = 30_000) -> None:
    """검색 결과 그리드(행 체크박스)가 나타날 때까지 대기합니다."""
    row_cb = page.locator(ROW_CHECKBOX).first
    try:
        row_cb.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(500)


def select_shipper_if_configured(
    page: Page,
    shipper_label: str,
    *,
    page_ready_selectors: Optional[List[str]] = None,
) -> None:
    """지정한 화주명으로 pwn_header_change를 선택합니다 (shipper_select 위임)."""
    from Mate2QA_shipper_select import select_shipper_on_page

    select_shipper_on_page(
        page,
        {"shipper_label": shipper_label},
        page_ready_selectors=page_ready_selectors,
    )


def save_search_criteria_from_page(page: Page) -> Dict[str, Any]:
    """
    주문목록 화면의 검색 6개·화주를 읽어 JSON에 저장합니다.
    (Enter 대기는 호출하는 쪽에서 1회만 합니다.)
    """
    criteria = capture_search_from_page(page)
    shipper = ""
    try:
        sel = page.locator('select[name="pwn_header_change"]')
        if sel.count() > 0:
            opt = sel.locator("option:checked")
            if opt.count() > 0:
                shipper = opt.first.inner_text().strip()
    except Exception:
        pass

    selected_snos = capture_selected_order_snos(page)
    data: Dict[str, Any] = {
        "default": criteria,
        "shipper_label": shipper,
        "selected_od_snos": selected_snos,
    }
    save_search_filter(data)
    _print_criteria_summary(criteria, prefix="→")
    if selected_snos:
        saved_txt = (criteria.get("search_txt") or "").strip()
        if saved_txt:
            pass
        else:
            pass
    else:
        pass
    return data


# 하위 호환
run_search_flow = save_search_criteria_from_page
