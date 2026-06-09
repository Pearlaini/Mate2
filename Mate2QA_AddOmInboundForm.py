# QA OMS 입고예정 목록 — 로그인·화주 선택·입고예정 목록 이동
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
    popup_page_zoom,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    join_origin_path,
    print_site_url_banner,
)

# 로그인 후 이동 — OMS 입고예정 목록
OM_PUT_EXPECT_LIST_PATH = "/om/put/expect/expectList.do"
from Mate2QA_order_search import load_search_filter, select_shipper_if_configured
from Mate2QA_order_step import click_popup_ok_if_visible

# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    **_SITE_CONFIG,
    # 로그인 후 이동 URL (LOGIN_URL 호스트 + 입고예정 목록 경로)
    "om_put_expect_list_url": join_origin_path(
        _SITE_CONFIG["login_url"], OM_PUT_EXPECT_LIST_PATH
    ),
    # 화주 선택 이름 (search_filter_domestic.json shipper_label이 있으면 그 값 우선)
    "shipper_label": "아이니",
    # 입고등록 화면 물류센터 이름 (없으면 목록 첫 번째 선택)
    "depot_label": "구로센터",
    # 입고등록 화면 공급사 — Ably는 목록 첫 번째 항목 자동 선택
    # 입고상품추가 팝업 — 검색조건·검색어·입고수량
    "item_search_column": "prod_cd",
    "item_search_keyword": "P000000000000055",
    "item_put_plan_qty": "10",
    # 2번(엑셀 업로드) — Mate2QA_login.env EXCEL_UPLOAD_FILE 이 있으면 그 경로 우선
    # 기본: D:\py3\샘플_입고요청.xlsx (화면 양식 다운로드 후 해당 이름으로 저장)
}

STATE_FILE = STATE_FILE_DOMESTIC


def resolve_shipper_label(config: Dict) -> str:
    """화주 이름: search_filter_domestic.json → CONFIG 순으로 읽습니다."""
    data = load_search_filter()
    if data:
        label = (data.get("shipper_label") or "").strip()
        if label:
            return label
    return (config.get("shipper_label") or "").strip()


def select_company_value(page, config: Dict) -> None:
    """pwn_header_change에서 화주사를 선택합니다."""
    target_label = resolve_shipper_label(config)
    if not target_label:
        return

    selector = 'select[name="pwn_header_change"]'
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=15_000)
        page.wait_for_function(
            """() => {
                const el = document.querySelector('select[name="pwn_header_change"]');
                return el && el.options && el.options.length > 1;
            }""",
            timeout=15_000,
        )
    except PlaywrightTimeoutError:


        pass

    select_shipper_if_configured(page, target_label)


def goto_om_put_expect_list(page, config: Dict):
    """OMS 입고예정 목록 화면으로 이동한 뒤 화주를 선택합니다."""
    target_url = config["om_put_expect_list_url"]
    page.goto(target_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    select_company_value(page, config)


def click_inbound_register_button(page):
    """입고요청 목록에서 '입고등록' 버튼을 클릭해 등록 화면으로 이동합니다."""
    btn_candidates = [
        "#btnReqRgst",
        'button:has-text("입고등록")',
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'입고등록' 버튼(btnReqRgst)을 찾지 못했습니다.")

    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1200)


def _read_fixed_depot_info(page) -> tuple[str, str]:
    """readonly·hidden 형태로 고정된 물류센터 이름·코드를 읽습니다."""
    depot_nm = ""
    depot_cd = ""

    nm_loc = page.locator('input[name="depot_nm"], #depot_nm').first
    if nm_loc.count() > 0:
        try:
            depot_nm = (nm_loc.input_value() or "").strip()
        except Exception:
            depot_nm = (nm_loc.get_attribute("value") or "").strip()

    cd_loc = page.locator(
        'input[type="hidden"][name="depot_cd"], input#depot_cd[type="hidden"]'
    ).first
    if cd_loc.count() > 0:
        depot_cd = (cd_loc.get_attribute("value") or "").strip()

    return depot_nm, depot_cd


def _is_depot_selectable(page) -> bool:
    """물류센터를 드롭다운으로 선택할 수 있는지 확인합니다."""
    select_loc = page.locator('select[name="depot_cd"]').first
    if select_loc.count() == 0:
        return False
    if not select_loc.is_visible():
        return False
    if select_loc.is_disabled():
        return False
    return True


def select_depot_cd(page, depot_label: str = "구로센터") -> None:
    """입고등록 화면에서 물류센터(depot_cd)를 선택합니다. 선택 불가면 건너뜁니다."""
    if not _is_depot_selectable(page):
        fixed_nm, fixed_cd = _read_fixed_depot_info(page)
        if fixed_nm or fixed_cd:
            pass
        else:
            pass
        return

    selector = 'select[name="depot_cd"]'
    select_loc = page.locator(selector).first
    target_label = (depot_label or "구로센터").strip()
    picked = select_loc.evaluate(
        """(el, label) => {
            const opts = Array.from(el.options || []);
            const byLabel = opts.find(
                (o) => (o.textContent || '').trim() === label && o.value && o.value.trim() !== ''
            );
            const pick = byLabel || opts.find((o) => o.value && o.value.trim() !== '');
            if (!pick) return { value: '', text: '', matched: false };
            el.value = pick.value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return {
                value: pick.value,
                text: (pick.textContent || '').trim(),
                matched: !!byLabel,
            };
        }""",
        target_label,
    )
    if not picked.get("value"):
        raise ValueError("depot_cd에서 선택 가능한 option이 없습니다.")

    if picked.get("matched"):
        pass
    else:


        pass


def select_vendor_cd(page) -> None:
    """입고등록 화면에서 공급사(vendor_cd) 목록 첫 번째 항목을 선택합니다."""
    selector = 'select[name="vendor_cd"]'
    select_loc = page.locator(selector).first
    if select_loc.count() == 0:
        raise ValueError("공급사 select[name='vendor_cd'] 요소를 찾지 못했습니다.")
    if not select_loc.is_visible():
        raise ValueError("공급사 select[name='vendor_cd']가 화면에 보이지 않습니다.")
    if select_loc.is_disabled():
        return

    picked = select_loc.evaluate(
        """(el) => {
            const opts = Array.from(el.options || []);
            const first = opts.find((o) => o.value && o.value.trim() !== '');
            if (!first) return { value: '', text: '' };
            el.value = first.value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return {
                value: first.value,
                text: (first.textContent || '').trim(),
            };
        }"""
    )
    if not picked.get("value"):
        raise ValueError("vendor_cd에서 선택 가능한 option이 없습니다.")


def fill_field(page, field_name: str, value: str, *, required: bool = True):
    """입력 필드 하나를 찾아 값을 채웁니다."""
    candidates = [
        f'input[name="{field_name}"]',
        f'textarea[name="{field_name}"]',
        f"#{field_name}",
    ]
    field, sel = first_visible_locator(page, candidates)
    if not field:
        if required:
            raise ValueError(f"{field_name} 입력 요소를 찾지 못했습니다.")
        return
    field.fill(value)
    safe_value = value.encode("cp949", errors="replace").decode("cp949")


def fill_put_request_info_fields(page):
    """입고등록 화면의 차량·운전자·ASN·비고 정보를 입력합니다."""
    now = datetime.now()
    yyyy = now.strftime("%Y")
    mmdd = now.strftime("%m%d")
    yyyymmdd = now.strftime("%Y%m%d")
    yymmddhhmm = now.strftime("%y%m%d%H%M")

    put_car_no = f"서울{yyyy}-{mmdd}"
    car_drv_nm = f"J{yyyymmdd}"
    car_drv_tel_no = f"010-{yyyy}-{mmdd}"
    sub_shipg_no = f"A{yymmddhhmm}"
    remark = "J"


    fill_field(page, "put_car_no", put_car_no)
    fill_field(page, "car_drv_nm", car_drv_nm)
    fill_field(page, "car_drv_tel_no", car_drv_tel_no)
    fill_field(page, "sub_shipg_no", sub_shipg_no)
    fill_field(page, "remark_ct", remark)


def ask_inbound_item_method() -> str:
    """입고상품 등록 방식을 사용자에게 묻습니다. 1=입고상품추가, 2=엑셀 업로드."""
    print(
        "\n입고상품 등록 방식을 선택해 주세요.\n"
        "  1  입고상품추가\n"
        "  2  엑셀 업로드\n"
    )
    try:
        choice = input("번호 입력 (1 또는 2, Enter=1): ").strip()
    except EOFError:
        return "1"
    if not choice:
        return "1"
    if choice not in ("1", "2"):
        return "1"
    return choice


def click_item_register_button(page) -> None:
    """입고등록 화면에서 '입고상품추가' 버튼을 클릭합니다."""
    btn_candidates = [
        "#itemRgstBtn",
        'button:has-text("입고상품추가")',
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'입고상품추가' 버튼(itemRgstBtn)을 찾지 못했습니다.")

    btn.click()
    page.wait_for_timeout(800)


def _get_item_add_modal(page):
    """입고상품추가 팝업(모달) 범위를 반환합니다."""
    modal = page.locator(".modal.show").filter(
        has=page.locator('input#searchTxt, input[name="searchTxt"]')
    ).first
    modal.wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(500)
    return modal


def _select_item_search_column(modal, column_value: str) -> None:
    """팝업 안 searchColumn(검색조건)을 선택합니다."""
    col_loc = modal.locator('select#searchColumn, select[name="searchColumn"]').first
    if col_loc.count() == 0 or not col_loc.is_visible():
        return

    value = (column_value or "prod_cd").strip()
    try:
        col_loc.select_option(value=value)
        return
    except Exception:
        pass

    # value 매칭 실패 시 라벨(prod_cd 텍스트)로 재시도
    try:
        col_loc.select_option(label=value)
    except Exception as exc:




        pass


def _wait_item_search_results(modal, *, timeout_ms: int = 12_000) -> int:
    """팝업 그리드에 검색 결과 행이 나타날 때까지 대기합니다."""
    rows = modal.locator("#grid-table .tabulator-row, .tabulator-row")
    try:
        rows.first.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return 0
    count = rows.count()
    return count


def search_item_in_add_popup(page, config: Dict) -> None:
    """입고상품추가 팝업(모달) 안에서만 검색어 입력 후 검색합니다."""
    search_keyword = (config.get("item_search_keyword") or "").strip()
    if not search_keyword:
        raise ValueError("입고상품 검색어(item_search_keyword)가 비어 있습니다.")

    modal = _get_item_add_modal(page)
    _select_item_search_column(modal, config.get("item_search_column", "prod_cd"))

    txt_input = modal.locator('input#searchTxt, input[name="searchTxt"]').first
    if txt_input.count() == 0:
        raise ValueError("입고상품추가 팝업의 searchTxt 입력 요소를 찾지 못했습니다.")

    txt_input.click()
    txt_input.fill("")
    txt_input.fill(search_keyword)
    page.wait_for_timeout(300)
    filled = (txt_input.input_value() or "").strip()

    search_btn = modal.locator("#searchBtn, button#searchBtn").first
    if search_btn.count() == 0 or not search_btn.is_visible():
        raise ValueError("입고상품추가 팝업의 검색 버튼(searchBtn)을 찾지 못했습니다.")
    search_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)

    row_count = _wait_item_search_results(modal)
    if row_count == 0:
        # Enter 키로 한 번 더 시도
        txt_input.press("Enter")
        page.wait_for_timeout(1000)
        row_count = _wait_item_search_results(modal, timeout_ms=8000)

    if row_count == 0:
        pass
    else:


        pass


def _fill_put_plan_unit_qty(modal, page, qty: str) -> None:
    """검색 결과 첫 행의 입고수량(put_plan_unit_qty)에 수량을 입력합니다."""
    row = modal.locator("#grid-table .tabulator-row, .tabulator-row").first
    row.wait_for(state="visible", timeout=10_000)

    qty_cell = row.locator('[tabulator-field="put_plan_unit_qty"]').first
    if qty_cell.count() == 0:
        raise ValueError("입고수량(put_plan_unit_qty) 셀을 찾지 못했습니다.")

    qty_cell.click()
    page.wait_for_timeout(300)
    qty_cell.dblclick()
    page.wait_for_timeout(400)

    qty_input = qty_cell.locator("input").first
    if qty_input.count() == 0 or not qty_input.is_visible():
        qty_input = modal.locator(".tabulator-editing input").first
    if qty_input.count() == 0 or not qty_input.is_visible():
        qty_input = page.locator(".tabulator-editing input").first

    if qty_input.count() > 0 and qty_input.is_visible():
        qty_input.fill("")
        qty_input.fill(qty)
    else:
        qty_cell.evaluate(
            """(el, value) => {
                let input = el.querySelector('input');
                if (!input) {
                    input = document.createElement('input');
                    el.appendChild(input);
                }
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            qty,
        )

    page.wait_for_timeout(300)


def click_add_item_button(modal, page) -> None:
    """검색 결과 첫 행의 '추가' 버튼을 클릭합니다."""
    row = modal.locator("#grid-table .tabulator-row, .tabulator-row").first
    add_btn = row.locator(
        '[tabulator-field="item_ins"] button:has-text("추가"), '
        'button[onclick*="addItem"]'
    ).first
    if add_btn.count() == 0 or not add_btn.is_visible():
        add_btn = modal.locator('button:has-text("추가")').first
    if add_btn.count() == 0 or not add_btn.is_visible():
        raise ValueError("검색 결과 행의 '추가' 버튼을 찾지 못했습니다.")

    add_btn.click()
    page.wait_for_timeout(1000)


def click_item_add_modal_close(modal, page) -> None:
    """입고상품추가 팝업의 '닫기' 버튼을 클릭합니다."""
    close_btn = modal.locator(
        'button[onclick*="insReqDetailModalClose"], '
        'button[data-dismiss="modal"]:has-text("닫기")'
    ).first
    if close_btn.count() == 0 or not close_btn.is_visible():
        raise ValueError("입고상품추가 팝업의 '닫기' 버튼을 찾지 못했습니다.")

    close_btn.click()
    page.wait_for_timeout(800)
    try:
        modal.wait_for(state="hidden", timeout=8000)
    except PlaywrightTimeoutError:
        pass


def _fill_grid_input_field(
    page,
    *,
    field_name: str,
    value: str,
    label: str,
) -> None:
    """본 화면 Tabulator 셀 또는 일반 input에 값을 입력합니다."""
    field_input = page.locator(
        f'input#{field_name}, input[name="{field_name}"]'
    ).first
    if field_input.count() > 0 and field_input.is_visible():
        field_input.click()
        field_input.fill("")
        field_input.fill(value)
        return

    cell = page.locator(f'[tabulator-field="{field_name}"]').first
    if cell.count() == 0:
        raise ValueError(f"{label}({field_name}) 입력 요소를 찾지 못했습니다.")

    cell.click()
    page.wait_for_timeout(300)
    cell.dblclick()
    page.wait_for_timeout(400)

    field_input = page.locator(
        f'input#{field_name}, input[name="{field_name}"], .tabulator-editing input'
    ).first
    if field_input.count() == 0 or not field_input.is_visible():
        raise ValueError(f"{label}({field_name}) 편집 입력란을 찾지 못했습니다.")

    field_input.fill("")
    field_input.fill(value)
    field_input.press("Tab")
    page.wait_for_timeout(300)


def fill_batch_number(page, stamp_yymmddhh: str) -> None:
    """본 화면 배치번호(pwn_bat_no)에 B+yymmddhh 를 입력합니다."""
    _fill_grid_input_field(
        page,
        field_name="pwn_bat_no",
        value=f"B{stamp_yymmddhh}",
        label="배치번호",
    )


def fill_lot_number(page, stamp_yymmddhh: str) -> None:
    """본 화면 로트번호(pwn_lot_no)에 L+yymmddhh 를 입력합니다."""
    _fill_grid_input_field(
        page,
        field_name="pwn_lot_no",
        value=f"L{stamp_yymmddhh}",
        label="로트번호",
    )


def _get_item_grid_row(page):
    """입고상품 그리드(#grid-table)의 첫 데이터 행을 반환합니다."""
    row = page.locator("#grid-table .tabulator-row").first
    row.wait_for(state="visible", timeout=10_000)
    row.scroll_into_view_if_needed()
    return row


def _close_datepicker_if_open(page) -> None:
    """열려 있는 날짜 달력 팝업을 닫습니다."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)


def _read_input_value(field_input) -> str:
    try:
        return (field_input.input_value() or "").strip()
    except Exception:
        return (field_input.evaluate("(el) => (el.value || '').trim()") or "").strip()


def _read_grid_cell_text(row, field_name: str) -> str:
    cell = row.locator(f'[tabulator-field="{field_name}"]').first
    if cell.count() == 0:
        return ""
    return (cell.inner_text() or "").strip()


def _type_date_manually(page, field_input, value: str) -> str:
    """수기 입력처럼 키보드로 날짜를 타이핑합니다."""
    field_input.click()
    page.wait_for_timeout(300)
    field_input.press("Control+a")
    page.wait_for_timeout(100)
    field_input.press("Backspace")
    page.wait_for_timeout(100)
    field_input.press_sequentially(value, delay=80)
    page.wait_for_timeout(400)
    field_input.press("Enter")
    page.wait_for_timeout(300)
    field_input.press("Tab")
    page.wait_for_timeout(400)
    _close_datepicker_if_open(page)
    return _read_input_value(field_input)


def _set_date_via_jquery(field_input, value: str) -> bool:
    """bootstrap-datepicker jQuery API로 날짜를 설정합니다."""
    return bool(
        field_input.evaluate(
            """(el, v) => {
                const $ = window.jQuery || window.$;
                if (!$ || !$(el).data || !$(el).data('datepicker')) return false;
                try {
                    $(el).datepicker('setDate', v);
                    $(el).trigger('change');
                    return !!(el.value || '').trim();
                } catch (e) {
                    return false;
                }
            }""",
            value,
        )
    )


def _activate_grid_cell(row, field_name: str) -> None:
    """Tabulator 셀을 편집 모드로 활성화합니다."""
    cell = row.locator(f'[tabulator-field="{field_name}"]').first
    if cell.count() == 0:
        raise ValueError(f"그리드 셀을 찾지 못했습니다: {field_name}")
    cell.click()
    page_wait = cell.page
    page_wait.wait_for_timeout(300)
    cell.dblclick()
    page_wait.wait_for_timeout(600)


def _find_date_input(row, page, field_name: str):
    """그리드 행 안의 datepicker input을 찾습니다."""
    scoped = row.locator(
        f'[tabulator-field="{field_name}"] input#{field_name}, '
        f'[tabulator-field="{field_name}"] input[name="{field_name}"], '
        f'[tabulator-field="{field_name}"] input.datepicker'
    ).first
    if scoped.count() > 0 and scoped.is_visible():
        return scoped

    editing = page.locator(
        f'.tabulator-editing input#{field_name}, '
        f'.tabulator-editing input[name="{field_name}"], '
        f'input#{field_name}.datepicker:visible, '
        f'input[name="{field_name}"].datepicker:visible'
    ).first
    if editing.count() > 0 and editing.is_visible():
        return editing
    return None


def _fill_datepicker_grid_field(
    page,
    *,
    field_name: str,
    value_yyyymmdd: str,
    label: str,
) -> None:
    """Tabulator datepicker에 수기 입력 방식으로 YYYYMMDD를 넣습니다."""
    row = _get_item_grid_row(page)
    _activate_grid_cell(row, field_name)

    field_input = _find_date_input(row, page, field_name)
    if field_input is None:
        raise ValueError(f"{label}({field_name}) datepicker 입력란을 찾지 못했습니다.")

    # 1) 수기 타이핑 (YYYYMMDD)
    applied = _type_date_manually(page, field_input, value_yyyymmdd)

    # 2) 실패 시 하이픈 형식으로 재시도
    if not applied:
        value_dashed = (
            f"{value_yyyymmdd[0:4]}-{value_yyyymmdd[4:6]}-{value_yyyymmdd[6:8]}"
            if len(value_yyyymmdd) == 8
            else value_yyyymmdd
        )
        applied = _type_date_manually(page, field_input, value_dashed)

    # 3) jQuery datepicker API 시도
    if not applied:
        for candidate in (value_yyyymmdd, value_dashed):
            if _set_date_via_jquery(field_input, candidate):
                applied = _read_input_value(field_input)
                if applied:
                    break
        _close_datepicker_if_open(page)

    cell_text = _read_grid_cell_text(row, field_name)
    if not applied and cell_text:
        applied = cell_text

    if not applied:
        raise ValueError(
            f"{label}({field_name}) 값이 반영되지 않았습니다. "
            f"시도값: {value_yyyymmdd}, 셀표시: {cell_text!r}"
        )



def fill_manufacturing_date(page) -> None:
    """본 화면 제조일자(prod_mnfctur_dt)에 오늘 날짜(YYYYMMDD)를 입력합니다."""
    mnfctur_dt = datetime.now().strftime("%Y%m%d")
    _fill_datepicker_grid_field(
        page,
        field_name="prod_mnfctur_dt",
        value_yyyymmdd=mnfctur_dt,
        label="제조일자",
    )


def fill_expiration_date(page) -> None:
    """본 화면 소비기한(prod_expir_dt)에 오늘+365일(YYYYMMDD)을 입력합니다."""
    expir_dt = (datetime.now() + timedelta(days=365)).strftime("%Y%m%d")
    _fill_datepicker_grid_field(
        page,
        field_name="prod_expir_dt",
        value_yyyymmdd=expir_dt,
        label="소비기한",
    )


def run_item_add_flow(page, config: Dict) -> None:
    """입고상품추가 팝업: 검색 → 수량입력 → 추가 → 닫기 → 배치번호 입력."""
    qty = str(config.get("item_put_plan_qty", "10")).strip()
    stamp_yymmddhh = datetime.now().strftime("%y%m%d%H")

    click_item_register_button(page)
    page.wait_for_timeout(1200)

    with popup_page_zoom(page, config):
        search_item_in_add_popup(page, config)
        modal = _get_item_add_modal(page)
        _fill_put_plan_unit_qty(modal, page, qty)
        click_add_item_button(modal, page)
        click_item_add_modal_close(modal, page)

    # 그리드·datepicker는 줌 100%에서 수기 입력과 동일하게 타이핑합니다.
    with popup_page_zoom(page, config):
        fill_batch_number(page, stamp_yymmddhh)
        fill_lot_number(page, stamp_yymmddhh)
        fill_manufacturing_date(page)
        fill_expiration_date(page)


def get_configured_excel_path(config: Dict) -> Optional[Path]:
    """설정된 엑셀 파일 경로를 반환합니다. 파일이 없으면 None."""
    raw = (config.get("excel_upload_file_path") or "").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if path.is_file():
        return path.resolve()
    print(
        "[안내] 지정된 엑셀 파일이 없습니다.\n"
        f"  기대 경로: {path.resolve()}\n"
        "  팝업에서 직접 파일을 선택해 주세요. (첨부 완료까지 대기합니다)"
    )
    return None


def _get_excel_file_input(page):
    """엑셀 업로드 팝업의 파일 input 요소를 반환합니다."""
    candidates = [
        '#excelUploadModal input#odFormFile',
        '#excelUploadModal input[name="odFormFile"]',
        "#excelUploadModal input[type='file']",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0:
            return loc
    raise ValueError(
        "엑셀 업로드 팝업에서 첨부파일(odFormFile) 요소를 찾지 못했습니다."
    )


def _excel_file_input_has_selection(page) -> bool:
    """파일 input에 사용자가 선택한 파일이 있는지 확인합니다."""
    return bool(
        page.evaluate(
            """() => {
                const el = document.querySelector('#excelUploadModal input#odFormFile')
                    || document.querySelector('#excelUploadModal input[name="odFormFile"]')
                    || document.querySelector('#excelUploadModal input[type="file"]');
                return !!(el && el.files && el.files.length > 0);
            }"""
        )
    )


def wait_for_user_excel_upload(page, *, timeout_ms: int = 1_800_000) -> None:
    """지정 파일이 없을 때, 사용자가 팝업에서 엑셀을 직접 첨부할 때까지 대기합니다."""
    modal = page.locator("#excelUploadModal")
    modal.wait_for(state="visible", timeout=10_000)
    print(
        "\n[안내] '입고품목 엑셀 일괄 등록' 팝업이 열렸습니다.\n"
        "  브라우저에서 엑셀 파일을 직접 선택해 주세요.\n"
        "  첨부가 감지되면 자동으로 다음 단계(등록)로 진행합니다."
    )

    try:
        page.wait_for_function(
            """() => {
                const el = document.querySelector('#excelUploadModal input#odFormFile')
                    || document.querySelector('#excelUploadModal input[name="odFormFile"]')
                    || document.querySelector('#excelUploadModal input[type="file"]');
                return !!(el && el.files && el.files.length > 0);
            }""",
            timeout=timeout_ms,
        )
        file_input = _get_excel_file_input(page)
        file_name = file_input.evaluate(
            "(el) => (el.files && el.files[0] && el.files[0].name) || ''"
        )
        return
    except PlaywrightTimeoutError:
        print(
            "[안내] 파일 자동 감지 시간이 초과되었습니다.\n"
            "  팝업에서 첨부를 마쳤다면 터미널에서 Enter를 눌러 주세요."
        )

    try:
        input("엑셀 파일 첨부 완료 후 Enter: ")
    except EOFError:
        if not _excel_file_input_has_selection(page):
            raise TimeoutError(
                "사용자 엑셀 첨부를 확인하지 못했습니다. "
                "팝업에서 파일을 선택했는지 확인해 주세요."
            )


def run_excel_upload_flow(page, config: Dict) -> None:
    """엑셀 업로드 방식으로 입고상품을 등록합니다."""
    excel_path = get_configured_excel_path(config)
    with popup_page_zoom(page, config):
        click_excel_upload_button(page)
        if excel_path:
            attach_excel_upload_file(page, excel_path)
        else:
            wait_for_user_excel_upload(page)
        click_excel_upload_confirm_button(page)


def click_excel_upload_button(page):
    """입고등록 화면에서 '엑셀 업로드' 버튼을 클릭합니다."""
    btn_candidates = [
        "#xlsUploadBtn",
        'button:has-text("엑셀 업로드")',
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'엑셀 업로드' 버튼(xlsUploadBtn)을 찾지 못했습니다.")

    btn.click()
    page.wait_for_timeout(800)


def attach_excel_upload_file(page, file_path):
    """엑셀 업로드 팝업에서 지정한 xlsx 파일을 자동 첨부합니다."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"엑셀 첨부 파일을 찾지 못했습니다: {path}")

    modal = page.locator("#excelUploadModal")
    modal.wait_for(state="visible", timeout=10_000)

    file_input = _get_excel_file_input(page)
    file_input.set_input_files(str(path))
    page.wait_for_timeout(500)


def click_excel_upload_confirm_button(page):
    """엑셀 업로드 팝업에서 '등록' 클릭 → 성공 OK 팝업 처리 → 업로드 팝업 닫힘 대기."""
    modal = page.locator("#excelUploadModal")
    btn_candidates = [
        "#excelUploadModal #confirmBtn",
        "#confirmBtn",
        '#excelUploadModal button:has-text("등록")',
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'등록' 버튼(confirmBtn)을 찾지 못했습니다.")

    btn.click()

    if click_popup_ok_if_visible(page, timeout_ms=30000):
        pass
    else:
        raise ValueError("엑셀 업로드 성공 팝업을 찾지 못했습니다.")

    modal.wait_for(state="hidden", timeout=30000)
    page.wait_for_timeout(1000)


def click_save_button(page, *, confirm_swal: bool = False):
    """입고등록 화면에서 '저장' 버튼을 클릭합니다."""
    save_btn_candidates = [
        "#saveBtn",
        '[name="saveBtn"]',
        'button:has-text("저장")',
        '.btn.btn-primary:has-text("저장")',
    ]
    save_btn, save_sel = first_visible_locator(page, save_btn_candidates)
    if not save_btn:
        raise ValueError("'저장' 버튼(saveBtn)을 찾지 못했습니다.")

    save_btn.click()
    page.wait_for_timeout(800)

    popup = page.locator(".swal2-popup.swal2-show")

    def click_swal_confirm_if_visible(timeout_ms: int) -> bool:
        try:
            popup.first.wait_for(state="visible", timeout=timeout_ms)
            popup.locator("button.swal2-confirm.swal2-styled").first.click()
            page.wait_for_timeout(600)
            return True
        except PlaywrightTimeoutError:
            return False

    if confirm_swal:
        if click_swal_confirm_if_visible(5000):
            page.wait_for_timeout(400)
            if click_swal_confirm_if_visible(3000):
                pass
        else:
            print(
                "[경고] 저장 확인창을 찾지 못했습니다. "
                "화면에서 직접 확인하거나 네트워크·검증 오류를 확인해 주세요."
            )
    else:
        try:
            popup.first.wait_for(state="visible", timeout=3000)
            print("[안내] 저장 확인창이 떴습니다. '확인'은 자동으로 누르지 않았습니다.")
        except PlaywrightTimeoutError:
            print(
                "[안내] 저장 버튼은 클릭했습니다. "
                "(확인창이 늦게 뜨거나 없을 수 있습니다. 필요하면 화면에서 직접 확인해 주세요.)"
            )


def run():
    """로그인 후 OMS 입고예정 등록(엑셀 업로드·저장)까지 수행합니다."""
    print_site_url_banner()
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_om_put_expect_list(page, CONFIG)
            click_inbound_register_button(page)
            select_depot_cd(page, CONFIG.get("depot_label", "구로센터"))
            select_vendor_cd(page)
            fill_put_request_info_fields(page)

            item_method = ask_inbound_item_method()
            if item_method == "1":
                run_item_add_flow(page, CONFIG)
            else:
                run_excel_upload_flow(page, CONFIG)

            click_save_button(page)
            done_msg = (
                "입고상품추가·저장"
                if item_method == "1"
                else "엑셀 업로드·저장"
            )
            try:
                input("확인창에서 직접 처리하신 뒤, 종료하려면 Enter를 누르세요...")
            except EOFError:
                pass
        except PlaywrightTimeoutError:
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
