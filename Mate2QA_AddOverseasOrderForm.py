# QA site — 해외 주문서 추가 (메뉴 12번)
from datetime import datetime
from typing import Dict

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from Mate2QA_AddOmDomesticOrderForm import (
    _is_selectable_sach_option,
    _list_selectable_sach_options,
    _read_selected_sach_cd,
    _resolve_sach_cd_locator,
    _select_sach_cd_with_prefs,
    _wait_sach_cd_options_ready,
    click_orderer_info_title,
    click_save_button,
    click_section_title,
    ensure_shipper_selected_on_page,
    fill_field,
    fill_field_by_candidates,
    search_and_select_product_in_popup,
    wait_until_derived_field_nonempty,
)
from Mate2QA_login import first_visible_locator
from Mate2QA_shipper_select import PAGE_READY_OM_ORDER_LIST, select_shipper_on_page
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DEFAULT,
    refresh_config_from_env,
)

# =========================
# 사용자 설정 영역 (URL은 Mate2QA_site_config.py)
# =========================
CONFIG = {
    **_SITE_CONFIG,
    # 판매 국가·판매채널 (해외 수기 화면 label 기준)
    "sach_country_label": "일본",
    "sach_cd_label": "J채널(해외)B2C",
    "sach_cd_value": "",
    # 상품코드 (비우거나 목록에 없으면 검색 팝업 첫 번째 상품 선택)
    "sample_product_cd": "P000000000005754",
    "headless": False,
    "slow_mo": 150,
    "page_zoom": 1.0,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "selectors": {
        "login_id_input": 'input[name="loginId"]',
        "login_pw_input": 'input[name="password"]',
        "login_button": 'button:has-text("로그인")',
    },
}

# 국내용 storage_state_domestic.json과 분리 (해외 주문 세션)
STATE_FILE = STATE_FILE_DEFAULT


def resolve_overseas_sample_product_cd(config: Dict) -> str:
    """해외 주문용 상품코드. 비우면 검색 팝업에서 첫 번째 상품을 선택합니다."""
    return (config.get("sample_product_cd") or "").strip()


def select_overseas_sach_cd(page, config: Dict) -> None:
    """해외 수기 화면에서 판매채널(sach_cd)을 선택합니다 (국내와 동일한 폴백 순서)."""
    preferred_label = (config.get("sach_cd_label") or "").strip()
    preferred_value = (config.get("sach_cd_value") or "").strip()

    page.wait_for_load_state("domcontentloaded")
    select_loc = _resolve_sach_cd_locator(page)
    if select_loc is None:
        raise ValueError(
            "판매채널(sach_cd) 요소(#sach_cd)를 찾지 못했습니다. "
            "해외 주문서추가 화면인지 확인해 주세요."
        )

    try:
        _wait_sach_cd_options_ready(page, select_loc)
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "판매채널(sach_cd) 목록이 비어 있거나 로드되지 않았습니다.\n"
            "  · 해외 주문목록에서 화주가 선택됐는지 확인해 주세요 (메뉴 0번).\n"
            "  · 화주를 바꾼 뒤 12번을 다시 실행해 주세요."
        ) from exc

    selectable = _list_selectable_sach_options(select_loc)
    if not selectable:
        raise ValueError("sach_cd에서 선택 가능한 판매채널이 없습니다.")

    # 1) CONFIG label → 2) CONFIG/env value → 3) 첫 항목 (JS 즉시 선택)
    picked = _select_sach_cd_with_prefs(
        select_loc,
        value=preferred_value,
        label=preferred_label,
        fallback_label="",
    )
    if picked:
        return

    picked_value, picked_label = _read_selected_sach_cd(select_loc)
    if _is_selectable_sach_option(picked_value, picked_label):
        return

    raise ValueError(
        f"sach_cd 선택에 실패했습니다. 현재값='{picked_label}'({picked_value!r})\n"
        f"  · 후보: {selectable[:8]}"
    )


def open_overseas_order_add_page(page, config: Dict) -> None:
    """해외 주문목록으로 이동 후 '주문서추가' 버튼을 클릭합니다."""
    intl_list_url = (config.get("intl_order_list_url") or "").strip()
    if not intl_list_url:
        raise ValueError("intl_order_list_url이 설정되지 않았습니다.")

    page.goto(intl_list_url, wait_until="domcontentloaded")
    _, _ = first_visible_locator(page, PAGE_READY_OM_ORDER_LIST)

    select_shipper_on_page(
        page, config, page_ready_selectors=PAGE_READY_OM_ORDER_LIST
    )
    ensure_shipper_selected_on_page(page, step="해외 주문목록")

    add_btn_candidates = [
        'button:has-text("주문서추가")',
        'a:has-text("주문서추가")',
        'button:has-text("등록")',
        'a:has-text("등록")',
    ]
    add_btn, _btn_sel = first_visible_locator(page, add_btn_candidates)
    if not add_btn:
        raise ValueError("'주문서추가' 버튼을 찾지 못했습니다. selector를 확인해 주세요.")

    add_btn.click()
    page.wait_for_load_state("domcontentloaded")
    select_loc = _resolve_sach_cd_locator(page)
    if select_loc:
        try:
            select_loc.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(300)


def select_dropdown_value(page, field_name: str, target_label: str) -> None:
    """드롭다운 필드에서 원하는 값을 선택합니다."""
    select_selector = f'select[name="{field_name}"]'
    if page.locator(select_selector).count() > 0:
        page.select_option(select_selector, label=target_label)
        return

    trigger_candidates = [
        f"#{field_name}",
        f'[name="{field_name}"]',
        f'button[data-target="{field_name}"]',
        f'span[data-target="{field_name}"]',
    ]
    trigger_loc, _trigger_sel = first_visible_locator(page, trigger_candidates)
    if trigger_loc:
        trigger_loc.click()
        option_candidates = [
            f'li:has-text("{target_label}")',
            f'a:has-text("{target_label}")',
            f'span:has-text("{target_label}")',
            f'text="{target_label}"',
        ]
        option_loc, _option_sel = first_visible_locator(page, option_candidates)
        if option_loc:
            option_loc.click()
            return

    raise ValueError(
        f"{field_name}에서 '{target_label}' 값을 찾지 못했습니다. selector를 확인해 주세요."
    )


def select_overseas_order_form_values(page, config: Dict) -> None:
    """주문 등록 페이지에서 판매 국가, 판매채널 값을 선택합니다."""
    country = (config.get("sach_country_label") or "일본").strip()
    page.wait_for_timeout(1000)
    select_dropdown_value(page, "sach_country_cd", country)
    page.wait_for_timeout(300)
    select_overseas_sach_cd(page, config)


def click_info_card_title(page) -> None:
    """섹션 전환을 위해 카드 타이틀을 클릭합니다."""
    title_candidates = [
        ".card-title.fs-xl.text-info",
        "h3.card-title.fs-xl.text-info",
        "div.card-title.fs-xl.text-info",
    ]
    title_loc, _title_sel = first_visible_locator(page, title_candidates)
    if not title_loc:
        raise ValueError("card-title(fs-xl text-info) 요소를 찾지 못했습니다.")
    title_loc.click()
    page.wait_for_timeout(300)


def select_dest_country_with_fallback(page) -> None:
    """dest_country_cd 선택 실패 시 data-dial='81'을 대체 선택합니다."""
    for section_name in ["수취인 정보", "배송 정보", "배송지 정보", "최종 수취인 정보"]:
        try:
            click_section_title(page, section_name)
            break
        except Exception:
            continue

    try:
        select_dropdown_value(page, "dest_country_cd", "일본")
        return
    except Exception as err:
        print(f"[경고] dest_country_cd 선택 실패: {err}", flush=True)

    dial_open_candidates = [
        '[name="final_recvr_mobile_no_enc"] + .iti__selected-flag',
        '[name="final_recvr_mobile_no_enc"] ~ .iti .iti__selected-flag',
        ".iti__selected-flag",
    ]
    dial_open_loc, _dial_open_sel = first_visible_locator(page, dial_open_candidates)
    if dial_open_loc:
        dial_open_loc.click()
        page.wait_for_timeout(300)

    fallback_candidates = [
        '[data-dial="81"]',
        'li[data-dial="81"]',
        'a[data-dial="81"]',
        'span[data-dial="81"]',
    ]

    fallback_loc, _fallback_sel = first_visible_locator(page, fallback_candidates)
    if not fallback_loc:
        for frame in page.frames:
            frame_loc, frame_sel = first_visible_locator(frame, fallback_candidates)
            if frame_loc:
                fallback_loc, _fallback_sel = frame_loc, frame_sel
                break

    if not fallback_loc:
        raise ValueError("dest_country_cd 대체 선택(data-dial='81') 요소를 찾지 못했습니다.")

    fallback_loc.click()
    page.wait_for_timeout(500)


def select_intl_delivery_company_with_fallback(page) -> None:
    """intl_dlvr_base_cd를 보이게 한 뒤 일본 국제배송사를 선택합니다."""
    for section_name in ["국제배송 정보", "국제 배송 정보", "배송 정보", "배송사 정보"]:
        try:
            click_section_title(page, section_name)
            break
        except Exception:
            continue

    select_loc = page.locator('select[name="intl_dlvr_base_cd"]').first
    if select_loc.count() == 0:
        raise ValueError("intl_dlvr_base_cd select 요소를 찾지 못했습니다.")

    selected_value = select_loc.evaluate(
        """(el) => {
            const target = "IEXP0010";
            const options = Array.from(el.options || []);
            const hasTarget = options.some(opt => opt.value === target);
            const firstValid = options.find(opt => opt.value && opt.value.trim() !== "");
            const picked = hasTarget ? target : (firstValid ? firstValid.value : "");
            if (!picked) return "";
            el.value = picked;
            el.dispatchEvent(new Event("change", { bubbles: true }));
            return picked;
        }"""
    )
    if selected_value:
        return

    open_candidates = [
        'select[name="intl_dlvr_base_cd"]',
        "#intl_dlvr_base_cd",
        '[name="intl_dlvr_base_cd"]',
    ]
    open_loc, _open_sel = first_visible_locator(page, open_candidates)
    if open_loc:
        open_loc.click()
        page.wait_for_timeout(300)

    option_candidates = [
        'option:has-text("J국제배송사(일본)")',
        'li:has-text("J국제배송사(일본)")',
        'a:has-text("J국제배송사(일본)")',
        'span:has-text("J국제배송사(일본)")',
        'text="J국제배송사(일본)"',
    ]
    option_loc, _option_sel = first_visible_locator(page, option_candidates)
    if not option_loc:
        raise ValueError("intl_dlvr_base_cd 대체 선택 요소를 찾지 못했습니다.")
    option_loc.click()
    page.wait_for_timeout(500)


def fill_overseas_order_detail_fields(
    page,
    stamp_mmddhhmm: str,
    stamp_yymmddhhmm: str,
    stamp_yymmddhh: str,
) -> None:
    """해외 주문 상세 필드를 자동 입력합니다."""
    fill_field(page, "od_qty", "3", trigger_derived_calc=True)
    fill_field(page, "sach_sale_price", "300", trigger_derived_calc=True)
    wait_until_derived_field_nonempty(page, "pymt_price")
    fill_field(page, "mall_prod_url", "https://www.qoo10.jp")
    click_section_title(page, "주문 상세")
    fill_field(page, "mall_od_no", f"JJ{stamp_yymmddhhmm}", required=False)
    click_orderer_info_title(page)
    fill_field(page, "od_user_nm", f"주문{stamp_mmddhhmm}")
    fill_field(page, "od_user_tel_no_enc", f"+81 090{stamp_yymmddhh}")
    fill_field(page, "od_user_mobile_no_enc", f"+81 02{stamp_yymmddhh}")

    click_info_card_title(page)
    select_dest_country_with_fallback(page)
    fill_field(page, "final_recvr_nm", f"수취{stamp_mmddhhmm}")
    fill_field(page, "final_recvr_initial_nm", "キム-スチュィ")
    fill_field(page, "final_recvr_mobile_no_enc", f"090{stamp_yymmddhh}")
    fill_field(page, "final_recvr_tel_no_enc", f"03{stamp_yymmddhh}")

    for section_name in ["배송지 정보", "최종 배송지 정보", "배송 정보", "수취인 정보"]:
        try:
            click_section_title(page, section_name)
            break
        except Exception:
            continue

    fill_field_by_candidates(
        page, ["final_dlvr_zipcd", "dlvr_zipcd", "zipcd"], "1600023", required=False
    )
    fill_field_by_candidates(
        page,
        ["final_dlvr_total_addr", "dlvr_total_addr", "total_addr", "dlvr_addr"],
        "東京都新宿区西新宿6-6-2",
        required=False,
    )
    fill_field(page, "dlvr_msg", f"도착보장 {stamp_mmddhhmm} 입니다.")
    click_info_card_title(page)
    select_intl_delivery_company_with_fallback(page)


def run_task(page, context, config, *, keep_browser: bool = False):
    """해외 주문서 추가 자동화를 수행합니다."""
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")

    open_overseas_order_add_page(page, config)
    select_overseas_order_form_values(page, config)
    product_cd = resolve_overseas_sample_product_cd(config)
    search_and_select_product_in_popup(page, product_cd)
    fill_overseas_order_detail_fields(
        page, stamp_mmddhhmm, stamp_yymmddhhmm, stamp_yymmddhh
    )
    # 저장 후 SweetAlert/알림은 자동으로 누르지 않음 (수동 확인)
    click_save_button(page, confirm_swal=False, quiet=True)
    from Mate2QA_browser_session import (
        MSG_KEEP_BROWSER_AFTER_SAVE,
        wait_enter_after_task,
    )

    wait_enter_after_task(
        keep_browser=keep_browser,
        message=MSG_KEEP_BROWSER_AFTER_SAVE if keep_browser else None,
    )


def run():
    """로그인 후 해외 주문서 추가 자동화를 수행합니다 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
