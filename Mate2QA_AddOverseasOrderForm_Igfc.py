# QA site — igfc 해외 주문서 추가 (메뉴 12번, igfc 전용)
#
# igfc는 국내/해외 화면이 물리적으로 분리돼 있고, 해외 주문 상세 화면의 필드 구성이
# Q10/Ably 기준으로 만들어진 Mate2QA_AddOverseasOrderForm.py와 다르다
# (예전 Selenium 스크립트 I수기주문서등록_IGFCQa.py에서 확인된 필드 id 기준으로 작성).
# 판매국가/판매채널 선택·상품 검색까지는 공용 화면이라 기존 코드를 그대로 재사용한다.
from datetime import datetime
from typing import Dict

from Mate2QA_AddOmDomesticOrderForm import (
    click_orderer_info_title,
    click_save_button,
    click_section_title,
    fill_field,
    search_and_select_product_in_popup,
    wait_until_derived_field_nonempty,
)
from Mate2QA_AddOverseasOrderForm import (
    CONFIG as _OVERSEAS_CONFIG,
    STATE_FILE,
    open_overseas_order_add_page,
    resolve_overseas_sample_product_cd,
    select_overseas_order_form_values,
)

# 국가/채널/상품 검색은 공용 CONFIG를 그대로 씁니다.
CONFIG: Dict = {**_OVERSEAS_CONFIG}


def _set_select_value_js(page, field_id: str, value: str, *, required: bool = True) -> None:
    """select 요소에 JS로 값을 설정하고 change 이벤트를 발생시킵니다 (레거시 스크립트와 동일 방식)."""
    loc = page.locator(f"#{field_id}").first
    if loc.count() == 0:
        if required:
            raise ValueError(f"{field_id} 요소를 찾지 못했습니다.")
        return
    loc.evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }",
        value,
    )


def _click_radio_js(page, field_id: str, *, required: bool = True) -> None:
    """라디오 버튼을 JS로 클릭합니다 (커스텀 스타일로 일반 클릭이 가로채이는 경우 대비)."""
    loc = page.locator(f"#{field_id}").first
    if loc.count() == 0:
        if required:
            raise ValueError(f"{field_id} 요소를 찾지 못했습니다.")
        return
    loc.evaluate("(el) => el.click()")


def fill_overseas_order_detail_fields_igfc(
    page,
    stamp_mmddhhmm: str,
    stamp_yymmddhhmm: str,
    stamp_yymmddhh: str,
) -> None:
    """igfc 해외 주문 상세 필드를 자동 입력합니다 (consignee_* / jp_* 필드 기준)."""
    fill_field(page, "od_qty", "3", trigger_derived_calc=True)
    fill_field(page, "sach_sale_price", "300", trigger_derived_calc=True)
    wait_until_derived_field_nonempty(page, "pymt_price")
    # mall_prod_url(쇼핑몰 URL) 필드는 igfc 화면에 없으므로 채우지 않습니다.
    click_section_title(page, "주문 상세")
    fill_field(page, "mall_od_no", f"J{stamp_yymmddhhmm}", required=False)

    click_orderer_info_title(page)
    fill_field(page, "od_user_nm", f"주문{stamp_mmddhhmm}")
    fill_field(page, "od_user_tel_no_enc", f"+81 090{stamp_yymmddhh}")

    click_section_title(page, "수취인 정보")
    fill_field(page, "consignee_nm_loc", f"수취{stamp_mmddhhmm}")
    fill_field(page, "consignee_nm", "KimReciver")
    fill_field(page, "consignee_nm_init", "K.R.", required=False)
    fill_field(page, "consignee_mobile", f"090{stamp_yymmddhh}")
    fill_field(page, "consignee_tel", f"03{stamp_yymmddhh}", required=False)
    fill_field(page, "consignee_email_loc", f"{stamp_yymmddhh}@test.com", required=False)

    click_section_title(page, "배송 정보")
    _set_select_value_js(page, "dest_country_cd", "JP")
    # 기본주소(dlvr_addr)·상세주소(dlvr_detail_addr) 모두 개발자도구로 확인된 실제 id
    fill_field(page, "dlvr_addr", "トウキョウト シンジュクク ニシシンジュク")
    fill_field(page, "dlvr_detail_addr", "6-6-2 ヒルトントウキョウ", required=False)
    fill_field(page, "consignee_zipcode", "1600023", required=False)
    _click_radio_js(page, "jp_notice_type_y", required=False)
    _click_radio_js(page, "jp_receive_type_phone", required=False)
    try:
        page.select_option("#jp_dlvr_time_type", value="AM")
    except Exception:
        pass
    fill_field(page, "dlvr_msg", f"도착전 전화 {stamp_mmddhhmm}", required=False)

    click_section_title(page, "기타")
    fill_field(page, "remark_info", f"해외배송{stamp_mmddhhmm}", required=False)


def run_task(page, context, config, *, keep_browser: bool = False):
    """igfc 해외 주문서 추가 자동화를 수행합니다."""
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")

    open_overseas_order_add_page(page, config)
    select_overseas_order_form_values(page, config)
    product_cd = resolve_overseas_sample_product_cd(config)
    search_and_select_product_in_popup(page, product_cd)
    fill_overseas_order_detail_fields_igfc(
        page, stamp_mmddhhmm, stamp_yymmddhhmm, stamp_yymmddhh
    )
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
    """로그인 후 igfc 해외 주문서 추가 자동화를 수행합니다 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
