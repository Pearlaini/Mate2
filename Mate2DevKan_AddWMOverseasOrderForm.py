from datetime import datetime
from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    STATE_FILE,
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
)


# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    "login_url": "https://dev-kdash-oms.shopeasy.co.kr:8443",
    "order_list_url": "https://dev-kdash-oms.shopeasy.co.kr:8443/wm/out/reg/outExpectList.do",
    "headless": False,
    "slow_mo": 150,
    # Playwright 기본(1280×720)보다 넓게: 자동화 시 모달 표가 가로로 잘리는 현상 완화
    "viewport_width": 1920,
    "viewport_height": 1080,
    "selectors": {
        "login_id_input": 'input[name="loginId"]',
        "login_pw_input": 'input[name="password"]',
        "login_button": 'button:has-text("로그인")',
    },
    # 출고 수기등록 목적 화면: 구역 유형. '해외' 선택 시 이하 입력 영역 구성이 바뀝니다.
    "zone_type_id": "zone_type",
    "zone_type_label": "해외",
    # 수취인 국가(라벨), 국제배송사·판매채널 option value
    "dest_country_label": "일본",
    "intl_dlvr_base_cd_value": "IEXP0010",
    "sach_cd_value": "SACH0458",
}

def first_visible_locator_in(scope, candidates):
    """Page 또는 Frame(scope) 안에서 후보 중 보이는 첫 요소를 찾습니다."""
    for sel in candidates:
        loc = scope.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            return loc, sel
    return None, None


def select_company_value(page):
    """상단 헤더(pwn_header_change)에서 화주로 '광동생활건강'을 선택합니다."""
    selector = 'select[name="pwn_header_change"]'
    target_label = "광동생활건강"

    if page.locator(selector).count() > 0:
        page.select_option(selector, label=target_label)
        print(f"[안내] 화주 헤더—'{target_label}' 값을 선택했습니다.")
        return

    # select 요소가 아닌 커스텀 UI일 때를 대비해 텍스트 클릭으로 시도합니다.
    trigger_candidates = [
        '#pwn_header_change',
        '[name="pwn_header_change"]',
        'button:has-text("선택하세요")',
        'span:has-text("선택하세요")',
    ]
    trigger_loc, _ = first_visible_locator(page, trigger_candidates)
    if trigger_loc:
        trigger_loc.click()
        page.locator(f'text="{target_label}"').first.click()
        print(f"[안내] 화주 헤더—'{target_label}' 값을 선택했습니다.")
        return

    # 회사가 이미 고정된 계정 등: 전환 UI가 없으면 건너뜁니다.
    print(
        "[경고] pwn_header_change(화주 선택) 요소를 찾지 못했습니다. "
        "회사가 이미 선택된 환경으로 보고 회사 전환 단계를 건너뜁니다."
    )


def open_order_add_page(page, config: Dict):
    """출고등록으로 이동 후 '출고 수기등록' 버튼을 클릭합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    select_company_value(page)

    add_btn_candidates = [
        'button:has-text("출고 수기등록")',
        'a:has-text("출고 수기등록")',
    ]
    add_btn, btn_sel = first_visible_locator(page, add_btn_candidates)
    if not add_btn:
        raise ValueError("'출고 수기등록' 버튼을 찾지 못했습니다. selector를 확인해 주세요.")

    print(f"[디버그] 출고 수기등록 버튼 셀렉터: {btn_sel}")
    add_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    print("[안내] '출고 수기등록' 버튼 클릭을 완료했습니다.")


def click_add_outbound_item_button(page):
    """출고대상 품목 행 추가 버튼(id=addBtn)을 찾아 클릭합니다."""
    candidates = [
        "#addBtn",
        'button:has-text("출고대상 품목")',
        "button.btn-info:has-text('출고대상 품목')",
    ]
    btn, sel = first_visible_locator(page, candidates)
    if not btn:
        raise ValueError(
            "'출고대상 품목' 버튼(#addBtn)을 찾지 못했습니다. selector를 확인해 주세요."
        )
    print(f"[디버그] 출고대상 품목 버튼 셀렉터: {sel}")
    btn.click()
    page.wait_for_timeout(500)
    print("[안내] '출고대상 품목' 버튼 클릭을 완료했습니다.")


def select_zone_type_overseas(page, config: Dict):
    """
    목적 페이지 도착 후 id=zone_type에서 '해외'를 선택합니다.
    선택에 따라 아래쪽 입력 영역이 바뀌므로, 반영 시간을 위해 잠시 대기합니다.
    """
    elem_id = config.get("zone_type_id", "zone_type")
    target_label = config.get("zone_type_label", "해외")
    root = page.locator(f"#{elem_id}").first
    # 화면에 숨김 처리된 네이티브 select일 수 있어 attached 기준으로 둡니다.
    root.wait_for(state="attached", timeout=15000)

    tag = root.evaluate("el => el.tagName.toLowerCase()")
    if tag == "select":
        root.select_option(label=target_label, timeout=15000)
        print(f"[안내] #{elem_id}에서 '{target_label}'(label) 선택 완료")
        page.wait_for_timeout(800)
        return

    # 커스텀 UI: 클릭 후 옵션 텍스트로 선택
    try:
        root.click(timeout=5000)
    except PlaywrightTimeoutError:
        root.click(force=True, timeout=5000)
    page.wait_for_timeout(300)
    option_candidates = [
        f'#{elem_id} option:has-text("{target_label}")',
        f'li:has-text("{target_label}")',
        f'a:has-text("{target_label}")',
        f'span:has-text("{target_label}")',
        f'text="{target_label}"',
    ]
    opt_loc, opt_sel = first_visible_locator(page, option_candidates)
    if not opt_loc:
        raise ValueError(f"#{elem_id}을(를) 열었으나 '{target_label}' 옵션을 찾지 못했습니다.")
    opt_loc.click()
    print(f"[안내] #{elem_id} 커스텀 UI에서 '{target_label}' 선택 완료 (옵션: {opt_sel})")
    page.wait_for_timeout(800)


def select_dropdown_by_label(page, field_key: str, target_label: str):
    """id 또는 name 기준 네이티브 select에서 label 선택. 안 되면 커스텀 UI로 시도합니다."""
    for sel in (f'#{field_key}', f'select[name="{field_key}"]'):
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        if loc.evaluate("el => el.tagName.toLowerCase()") == "select":
            loc.select_option(label=target_label, timeout=15000)
            print(f"[안내] {field_key}에서 '{target_label}'(label) 선택 완료")
            page.wait_for_timeout(300)
            return

    trigger_candidates = [
        f"#{field_key}",
        f'[name="{field_key}"]',
        f'button[data-target="{field_key}"]',
        f'span[data-target="{field_key}"]',
    ]
    trigger_loc, trigger_sel = first_visible_locator(page, trigger_candidates)
    if trigger_loc:
        trigger_loc.click()
        page.wait_for_timeout(250)
        option_candidates = [
            f'li:has-text("{target_label}")',
            f'a:has-text("{target_label}")',
            f'span:has-text("{target_label}")',
            f'text="{target_label}"',
        ]
        option_loc, option_sel = first_visible_locator(page, option_candidates)
        if option_loc:
            option_loc.click()
            print(
                f"[안내] {field_key}에서 '{target_label}' 커스텀 선택 완료 "
                f"(트리거: {trigger_sel}, 옵션: {option_sel})"
            )
            page.wait_for_timeout(300)
            return

    raise ValueError(
        f"{field_key}에서 '{target_label}'을(를) 찾지 못했습니다. selector를 확인해 주세요."
    )


def select_native_select_value(page, element_id: str, option_value: str, *, root=None):
    """
    id(또는 동일 문자열의 name) select에 option value를 설정하고 change를 발생시킵니다.
    root: 메인 페이지가 아니라 팝업 iframe 등 다른 문서 트리를 쓸 때 locator 루트를 넘깁니다.
    """
    scope = root if root is not None else page
    candidates = (
        scope.locator(f"#{element_id}").first,
        scope.locator(f'select[name="{element_id}"]').first,
    )
    loc = None
    for cand in candidates:
        if cand.count() > 0:
            loc = cand
            break

    if loc is None:
        raise ValueError(f"{element_id} select 요소를 찾지 못했습니다.")

    loc.wait_for(state="attached", timeout=15000)
    picked = loc.evaluate(
        """(el, target) => {
            const opts = Array.from(el.options || []);
            if (!opts.some(o => o.value === target)) return "";
            el.value = target;
            el.dispatchEvent(new Event("change", { bubbles: true }));
            return target;
        }""",
        option_value,
    )
    if not picked:
        raise ValueError(f"{element_id}에서 value={option_value} 인 option을 찾지 못했습니다.")

    safe_v = picked.encode("cp949", errors="replace").decode("cp949")
    print(f"[안내] #{element_id}='{safe_v}'(value) 선택 완료")
    page.wait_for_timeout(350)


def fill_field(page, field_name: str, value: str, required: bool = True):
    """입력 필드 하나를 찾아 값을 채웁니다."""
    candidates = [
        f'input[name="{field_name}"]',
        f'textarea[name="{field_name}"]',
        f'#{field_name}',
    ]
    field, sel = first_visible_locator(page, candidates)
    if not field:
        if required:
            raise ValueError(f"{field_name} 입력 요소를 찾지 못했습니다.")
        print(f"[경고] {field_name} 입력 요소를 찾지 못해 건너뜁니다.")
        return
    field.fill(value)
    safe_value = value.encode("cp949", errors="replace").decode("cp949")
    print(f"[안내] {field_name}='{safe_value}' 입력 완료 (selector: {sel})")


def fill_field_by_candidates(page, field_names, value: str, required: bool = True):
    """여러 필드명 후보 중 먼저 찾은 필드에 값을 입력합니다."""
    for name in field_names:
        candidates = [
            f'input[name="{name}"]',
            f'textarea[name="{name}"]',
            f'#{name}',
        ]
        field, sel = first_visible_locator(page, candidates)
        if field:
            field.fill(value)
            safe_value = value.encode("cp949", errors="replace").decode("cp949")
            print(f"[안내] {name}='{safe_value}' 입력 완료 (selector: {sel})")
            return

    if required:
        joined = ", ".join(field_names)
        raise ValueError(f"입력 요소를 찾지 못했습니다. 후보: {joined}")
    print(f"[경고] 입력 요소를 찾지 못해 건너뜁니다. 후보: {', '.join(field_names)}")


def fill_orderer_name_and_contact(
    page, stamp_yymmddhhmm: str, stamp_yymmddhh: str
):
    """
    좌측 폼 순서 기준 — 배송지 유형 다음: 주문자 명, 주문자 연락처.
    (물류센터·출고유형은 화면별 id 미확인으로 생략)
    """
    page.wait_for_timeout(1000)
    fill_field(page, "od_user_nm", f"WM수기주문{stamp_yymmddhhmm}")
    fill_field(page, "od_user_tel_no_enc", f"+81090{stamp_yymmddhh}", required=False)


def fill_dest_country_and_recipient_contact(
    page,
    config: Dict,
    stamp_yyyymmddhhmm: str,
    stamp_yymmddhh: str,
):
    """도착국가, 수취인명, 수취인 전화·휴대전화 (배송지·국제배송사 보다 위)."""
    page.wait_for_timeout(500)
    select_dropdown_by_label(page, "dest_country_cd", config.get("dest_country_label", "일본"))
    fill_field(page, "final_recvr_nm", f"WM수기수취{stamp_yyyymmddhhmm}")
    fill_field(page, "final_recvr_tel_no_enc", f"02{stamp_yymmddhh}", required=False)
    fill_field(page, "final_recvr_mobile_no_enc", f"090{stamp_yymmddhh}", required=False)


def fill_delivery_zip_and_street_only(page):
    """배송지 우편번호·본문 주소만 (메시지·비고 보다 위)."""
    page.wait_for_timeout(500)
    fill_field_by_candidates(
        page,
        ["final_dlvr_zipcd", "dlvr_zipcd", "zipcd"],
        "1600023",
        required=False,
    )
    fill_field_by_candidates(
        page,
        ["final_dlvr_total_addr", "dlvr_total_addr", "total_addr", "dlvr_addr"],
        "東京都新宿区西新宿6-6-2",
        required=False,
    )


def fill_intl_default_carrier_select(page, config: Dict):
    """해외 배송 기본 수취인(국제배송사) — 배송지 주소 다음."""
    select_native_select_value(
        page,
        "intl_dlvr_base_cd",
        config.get("intl_dlvr_base_cd_value", "IEXP0010"),
    )


def fill_internal_order_no_and_sales_channel(
    page,
    config: Dict,
    stamp_yymmddhhmm: str,
):
    """자체 주문번호(mall_od_no), 판매채널(sach_cd). 출고 요청일·택배/배송구분 미구현 구간 이후 입력."""
    fill_field(page, "mall_od_no", f"JJ{stamp_yymmddhhmm}", required=False)
    select_native_select_value(page, "sach_cd", config.get("sach_cd_value", "SACH0458"))


def fill_delivery_message_and_remark(page, stamp_mmddhhmm: str):
    """배송 메시지, 비고 — 좌측 폼 마지막 입력란 순서."""
    fill_field(
        page,
        "dlvr_msg",
        f"도착보장{stamp_mmddhhmm}입니다.",
        required=False,
    )
    fill_field(
        page,
        "remark_ct",
        f"https://www.qoo10.jp/g/854993704",
        required=False,
    )


def run():
    """출고 수기등록 폼을 화면(좌측 패널) 위→아래 순으로 채운 뒤 출고대상 품목 버튼을 클릭합니다."""
    creds = load_env_credentials()
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yyyymmddhhmm = now.strftime("%Y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")
    print(f"[안내] 주문번호·주문자명용 YYMMDDHHMM: {stamp_yymmddhhmm}")
    print(f"[안내] 수취인명용 YYYYMMDDHHMM: {stamp_yyyymmddhhmm}")
    print(f"[안내] 수취인·주문자 전화 접미 YYMMDDHH: {stamp_yymmddhh}")
    print(f"[안내] 배송메시지용 MMDDHHMM: {stamp_mmddhhmm}")

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds)
            open_order_add_page(page, CONFIG)
            # 좌측 수기 출고등록 패널: 화면 위→아래 순서 (물류센터·출고유형 미구현)
            select_zone_type_overseas(page, CONFIG)
            fill_orderer_name_and_contact(
                page, stamp_yymmddhhmm, stamp_yymmddhh
            )
            fill_dest_country_and_recipient_contact(
                page, CONFIG, stamp_yyyymmddhhmm, stamp_yymmddhh
            )
            fill_delivery_zip_and_street_only(page)
            fill_intl_default_carrier_select(page, CONFIG)
            fill_internal_order_no_and_sales_channel(page, CONFIG, stamp_yymmddhhmm)
            # 출고 요청일·배송(택배/일반) 등 추가 필드는 id 확정 후 이 위치에 두면 됨
            fill_delivery_message_and_remark(page, stamp_mmddhhmm)
            click_add_outbound_item_button(page)
            print(
                "[안내] 로그인·출고 수기등록·해외(zone_type)·주문자·수취·배송지·국제배송·"
                "자체주문·판매채널·배송메시지·비고·출고대상 품목 버튼까지 완료했습니다."
            )
            try:
                input("브라우저를 확인한 뒤 종료하려면 Enter를 누르세요...")
            except EOFError:
                print("[안내] 표준 입력이 없거나 닫혀 있어 Enter 대기를 건너뜁니다.")
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
