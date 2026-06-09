# QA WMS 입고요청 목록 — 로그인·화주 선택·입고요청 목록 이동
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    PROJECT_DIR,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
)
from Mate2QA_order_search import load_search_filter, select_shipper_if_configured
from Mate2QA_order_step import click_popup_ok_if_visible

# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    **_SITE_CONFIG,
    # 화주 선택 이름 (search_filter_domestic.json shipper_label이 있으면 그 값 우선)
    "shipper_label": "아이니",
    # 입고등록 화면 공급사 option value (없거나 비어 있으면 목록 첫 번째 선택)
    "vendor_cd_value": "VEN00012",
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


def goto_wm_put_req_list(page, config: Dict):
    """WMS 입고요청 목록 화면으로 이동한 뒤 화주를 선택합니다."""
    page.goto(config["wm_put_req_list_url"], wait_until="domcontentloaded")
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


def select_vendor_cd(page, vendor_cd_value: Optional[str] = None):
    """입고등록 화면에서 공급사(vendor_cd)를 선택합니다."""
    selector = 'select[name="vendor_cd"]'
    select_loc = page.locator(selector).first
    if select_loc.count() == 0:
        raise ValueError("select[name='vendor_cd'] 요소를 찾지 못했습니다.")

    value = (vendor_cd_value or "").strip()
    if value:
        page.select_option(selector, value=value)
        return

    picked = select_loc.evaluate(
        """(el) => {
            const opts = Array.from(el.options || []);
            const first = opts.find(o => o.value && o.value.trim() !== '');
            if (!first) return '';
            el.value = first.value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return first.value;
        }"""
    )
    if not picked:
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
    car_drv_nm = f"김{yyyymmdd}"
    car_drv_tel_no = f"010-{yyyy}-{mmdd}"
    sub_shipg_no = f"A{yymmddhhmm}"
    remark = "J"


    fill_field(page, "put_car_no", put_car_no)
    fill_field(page, "car_drv_nm", car_drv_nm)
    fill_field(page, "car_drv_tel_no", car_drv_tel_no)
    fill_field(page, "sub_shipg_no", sub_shipg_no)
    fill_field(page, "remark_ct", remark)


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


def attach_excel_upload_file(page, file_path: str):
    """엑셀 업로드 팝업에서 지정한 xlsx 파일을 첨부합니다."""
    path = Path(file_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.is_file():
        raise FileNotFoundError(f"엑셀 첨부 파일을 찾지 못했습니다: {path}")

    modal = page.locator("#excelUploadModal")
    modal.wait_for(state="visible", timeout=10000)

    file_input = page.locator('#excelUploadModal input#odFormFile').first
    if file_input.count() == 0:
        file_input = page.locator('#excelUploadModal input[name="odFormFile"]').first
    if file_input.count() == 0:
        raise ValueError(
            "엑셀 업로드 팝업에서 첨부파일(odFormFile) 요소를 찾지 못했습니다."
        )

    file_input.set_input_files(str(path.resolve()))
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
    """로그인 후 WMS 입고요청 등록(엑셀 업로드·저장)까지 수행합니다."""
    print_site_url_banner()
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_wm_put_req_list(page, CONFIG)
            click_inbound_register_button(page)
            select_vendor_cd(page, CONFIG.get("vendor_cd_value"))
            fill_put_request_info_fields(page)
            click_excel_upload_button(page)
            attach_excel_upload_file(page, CONFIG["excel_upload_file_path"])
            click_excel_upload_confirm_button(page)
            click_save_button(page)
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
