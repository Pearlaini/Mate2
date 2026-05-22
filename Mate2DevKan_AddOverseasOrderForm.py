# 칸다슈 개발사이트

import os
from datetime import datetime
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    "login_url": "https://dev-kdash-oms.shopeasy.co.kr:8443",
    "order_list_url": "https://dev-kdash-oms.shopeasy.co.kr:8443/om/intlOrder/order/orderList.do",
    "headless": False,
    "slow_mo": 150,
    # Playwright 기본(1280×720)보다 넓게: 자동화 시 표·모달이 가로로 잘리는 현상 완화
    "viewport_width": 1920,
    "viewport_height": 1080,
    "selectors": {
        "login_id_input": 'input[name="loginId"]',
        "login_pw_input": 'input[name="password"]',
        "login_button": 'button:has-text("로그인")',
    },
}

STATE_FILE = Path("storage_state.json")


def load_env_credentials() -> Dict[str, str]:
    """환경변수에서 로그인 정보를 읽습니다."""
    load_dotenv("Mate2QA_login.env")
    user_id = os.getenv("ID", "").strip()
    user_pw = os.getenv("PW", "").strip()

    if not user_id or not user_pw:
        raise ValueError("`matelogin.env`에 ID, PW를 설정해 주세요.")
    return {"id": user_id, "pw": user_pw}

def create_context(p, config: Dict):
    """저장된 세션이 있으면 재사용하고, 없으면 새 컨텍스트를 만듭니다."""
    browser = p.chromium.launch(
        headless=config["headless"],
        slow_mo=config["slow_mo"],
    )

    vw = int(config.get("viewport_width", 1920))
    vh = int(config.get("viewport_height", 1080))
    ctx_kw: Dict = {"viewport": {"width": vw, "height": vh}}

    if STATE_FILE.exists():
        ctx_kw["storage_state"] = str(STATE_FILE)

    context = browser.new_context(**ctx_kw)

    return browser, context


def is_login_page(page, login_url: str) -> bool:
    """현재 페이지가 로그인 페이지인지 확인합니다."""
    current = page.url.lower()
    return "login.do" in current


def first_visible_locator(page, candidates):
    """후보 셀렉터 중 화면에 보이는 첫 요소를 찾습니다."""
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            return loc, sel
    return None, None


def do_login(page, config: Dict, creds: Dict[str, str]):
    """로그인을 수행합니다."""
    page.goto(config["login_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    print(f"[디버그] 현재 URL: {page.url}")
    print(f"[디버그] 페이지 제목: {page.title()}")

    id_candidates = [
        'input[name="loginId"]',
        'input[name="id"]',
        'input[name="userId"]',
        'input[id="loginId"]',
        'input[id="id"]',
        'input[type="text"]',
    ]
    pw_candidates = [
        'input[name="password"]',
        'input[name="pw"]',
        'input[id="password"]',
        'input[id="pw"]',
        'input[type="password"]',
    ]
    btn_candidates = [
        'button:has-text("로그인")',
        'input[type="submit"]',
        'button[type="submit"]',
        '.btn_login',
    ]

    id_loc, id_sel = first_visible_locator(page, id_candidates)
    pw_loc, pw_sel = first_visible_locator(page, pw_candidates)
    btn_loc, btn_sel = first_visible_locator(page, btn_candidates)

    if not id_loc or not pw_loc or not btn_loc:
        raise ValueError(
            f"로그인 요소를 찾지 못했습니다. id={id_sel}, pw={pw_sel}, btn={btn_sel}. "
            "F12로 실제 input/button selector를 확인해 주세요."
        )

    print(f"[디버그] ID 셀렉터: {id_sel}")
    print(f"[디버그] PW 셀렉터: {pw_sel}")
    print(f"[디버그] BTN 셀렉터: {btn_sel}")

    id_loc.fill(creds["id"])
    pw_loc.fill(creds["pw"])
    btn_loc.click()
    handle_duplicate_login_popup(page)
    page.wait_for_load_state("networkidle")


def handle_duplicate_login_popup(page):
    """중복 로그인 팝업이 뜨면 확인 버튼을 눌러 로그인 진행을 계속합니다."""
    popup = page.locator(".swal2-popup.swal2-show")
    try:
        popup.first.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeoutError:
        return

    title = popup.locator("#swal2-title")
    if title.count() > 0 and "중복 로그인" in title.first.inner_text():
        confirm_btn = popup.locator("button.swal2-confirm.swal2-styled").first
        confirm_btn.click()
        page.wait_for_timeout(800)
        print("[안내] 중복 로그인 팝업에서 '확인'을 클릭했습니다.")


def ensure_login_only(page, context, config: Dict, creds: Dict[str, str]):
    """주문 페이지 없이 로그인 상태만 확인/보장합니다."""
    page.goto(config["login_url"], wait_until="domcontentloaded")

    if is_login_page(page, config["login_url"]):
        print("[안내] 로그인되지 않은 상태입니다. 자동 로그인합니다.")
        do_login(page, config, creds)
        context.storage_state(path=str(STATE_FILE))
        print("[안내] 로그인 완료, 세션을 storage_state.json에 저장했습니다.")
    else:
        print(f"[안내] 이미 로그인되어 있습니다. 현재 URL: {page.url}")


def select_company_value(page):
    """pwn_header_change에서 '광동생활건강' 값을 선택합니다."""
    selector = 'select[name="pwn_header_change"]'
    target_label = "광동생활건강"

    if page.locator(selector).count() > 0:
        page.select_option(selector, label=target_label)
        print(f"[안내] '{target_label}' 값을 선택했습니다.")
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
        print(f"[안내] '{target_label}' 값을 선택했습니다.")
        return

    # 회사가 이미 고정된 계정 등: 전환 UI가 없으면 건너뜁니다.
    print(
        "[경고] pwn_header_change 요소를 찾지 못했습니다. "
        "회사가 이미 선택된 환경으로 보고 회사 전환 단계를 건너뜁니다."
    )


def open_order_add_page(page, config: Dict):
    """주문목록으로 이동 후 '주문서추가' 버튼을 클릭합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 주문목록 페이지로 이동했습니다. 현재 URL: {page.url}")

    select_company_value(page)

    add_btn_candidates = [
        'button:has-text("주문서추가")',
        'a:has-text("주문서추가")',
        'button:has-text("등록")',
        'a:has-text("등록")',
    ]
    add_btn, btn_sel = first_visible_locator(page, add_btn_candidates)
    if not add_btn:
        raise ValueError("'주문서추가' 버튼을 찾지 못했습니다. selector를 확인해 주세요.")

    print(f"[디버그] 주문서추가 버튼 셀렉터: {btn_sel}")
    add_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1200)
    print(f"[안내] 주문서추가 버튼 클릭 완료. 현재 URL: {page.url}")


def select_dropdown_value(page, field_name: str, target_label: str):
    """드롭다운 필드에서 원하는 값을 선택합니다."""
    select_selector = f'select[name="{field_name}"]'
    if page.locator(select_selector).count() > 0:
        page.select_option(select_selector, label=target_label)
        print(f"[안내] {field_name}에서 '{target_label}'을(를) 선택했습니다.")
        return

    trigger_candidates = [
        f'#{field_name}',
        f'[name="{field_name}"]',
        f'button[data-target="{field_name}"]',
        f'span[data-target="{field_name}"]',
    ]
    trigger_loc, trigger_sel = first_visible_locator(page, trigger_candidates)
    if trigger_loc:
        trigger_loc.click()
        option_candidates = [
            f'li:has-text("{target_label}")',
            f'a:has-text("{target_label}")',
            f'span:has-text("{target_label}")',
            f'text="{target_label}"',
        ]
        option_loc, option_sel = first_visible_locator(page, option_candidates)
        if option_loc:
            option_loc.click()
            print(f"[안내] {field_name}에서 '{target_label}'을(를) 선택했습니다.")
            print(f"[디버그] 트리거 셀렉터: {trigger_sel}, 옵션 셀렉터: {option_sel}")
            return

    raise ValueError(f"{field_name}에서 '{target_label}' 값을 찾지 못했습니다. selector를 확인해 주세요.")


def select_order_form_values(page):
    """주문 등록 페이지에서 판매 국가, 판매채널 값을 선택합니다."""
    page.wait_for_timeout(1000)
    select_dropdown_value(page, "sach_country_cd", "일본")
    page.wait_for_timeout(300)
    select_dropdown_value(page, "sach_cd", "j해외b2c")


def search_product_in_popup(page, product_code: str):
    """상품 검색 팝업에서 상품코드로 조회를 실행합니다."""
    search_btn_candidates = [
        'button.btn.btn-secondary.btn-sm.p-2.ml-2.waves-effect.waves-themed',
        'button:has-text("상품 검색")',
        'a:has-text("상품 검색")',
    ]
    search_btn, btn_sel = first_visible_locator(page, search_btn_candidates)
    if not search_btn:
        raise ValueError("'상품 검색' 버튼을 찾지 못했습니다. selector를 확인해 주세요.")

    print(f"[디버그] 상품 검색 버튼 셀렉터: {btn_sel}")
    search_btn.click()
    page.wait_for_timeout(1200)

    # searchColumn 을 prod_cd로 선택
    if page.locator('select[name="searchColumn"]').count() > 0:
        page.select_option('select[name="searchColumn"]', value="prod_cd")
    else:
        dropdown_candidates = [
            '#searchColumn',
            '[name="searchColumn"]',
        ]
        dropdown, _ = first_visible_locator(page, dropdown_candidates)
        if not dropdown:
            raise ValueError("searchColumn 요소를 찾지 못했습니다.")
        dropdown.click()
        page.locator('text="prod_cd"').first.click()

    # searchTxt 입력
    txt_candidates = [
        'input[name="searchTxt"]',
        '#searchTxt',
    ]
    txt_input, txt_sel = first_visible_locator(page, txt_candidates)
    if not txt_input:
        raise ValueError("searchTxt 입력 요소를 찾지 못했습니다.")
    txt_input.fill(product_code)
    print(f"[디버그] searchTxt 셀렉터: {txt_sel}")

    # prodSearchBtn 클릭
    search_candidates = [
        '#prodSearchBtn',
        '[name="prodSearchBtn"]',
        'button:has-text("검색")',
    ]
    prod_search_btn, prod_btn_sel = first_visible_locator(page, search_candidates)
    if not prod_search_btn:
        raise ValueError("prodSearchBtn 버튼을 찾지 못했습니다.")
    print(f"[디버그] prodSearchBtn 셀렉터: {prod_btn_sel}")
    prod_search_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 상품 검색 실행 완료. 검색코드: {product_code}")


def click_select_button(page):
    """검색 결과의 '선택' 버튼을 클릭합니다."""
    select_btn_candidates = [
        'button.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1',
        'a.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1',
        'button:has-text("선택")',
        'a:has-text("선택")',
    ]
    select_btn, btn_sel = first_visible_locator(page, select_btn_candidates)
    if not select_btn:
        raise ValueError("'선택' 버튼을 찾지 못했습니다. selector를 확인해 주세요.")

    print(f"[디버그] 선택 버튼 셀렉터: {btn_sel}")
    select_btn.click()
    page.wait_for_timeout(1000)
    print("[안내] '선택' 버튼 클릭을 완료했습니다.")


def fill_field(
    page,
    field_name: str,
    value: str,
    required: bool = True,
    *,
    trigger_derived_calc: bool = False,
):
    """
    입력 필드 하나를 찾아 값을 채웁니다.
    trigger_derived_calc=True이면 입력 후 input·change 등 DOM 이벤트를 발생시켜,
    페이지 스크립트가 연관 필드(예: sach_sale_price → pymt_price)를 재계산하도록 합니다.
    """
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
    if trigger_derived_calc:
        field.evaluate(
            """(el) => {
                el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                el.blur();
            }"""
        )
        page.wait_for_timeout(150)
    safe_value = value.encode("cp949", errors="replace").decode("cp949")
    print(f"[안내] {field_name}='{safe_value}' 입력 완료 (selector: {sel})")


def wait_until_derived_field_nonempty(page, field_name: str, timeout_ms: int = 10000):
    """
    자동 계산으로 채워지는 표시 영역이 비어 있지 않을 때까지 대기합니다.
    readonly input(값은 value), 또는 name/id가 지정된 비입력 요소(text 표시) 모두 지원합니다.
    """
    js_has_content = """(name) => {
        const el = document.querySelector('[name="' + name + '"]')
            || document.querySelector('#' + name);
        if (!el) return false;
        const t = el.tagName;
        let s = '';
        if (t === 'INPUT' || t === 'TEXTAREA') {
            s = String(el.value ?? '');
        } else if (t === 'SELECT') {
            s = String(el.value ?? '');
        } else {
            s = String(el.textContent ?? '');
        }
        return s.trim() !== '';
    }"""

    js_read_display = """(name) => {
        const el = document.querySelector('[name="' + name + '"]')
            || document.querySelector('#' + name);
        if (!el) return '';
        const t = el.tagName;
        if (t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') {
            return String(el.value ?? '').trim();
        }
        return String(el.textContent ?? '').trim();
    }"""

    try:
        page.wait_for_function(js_has_content, arg=field_name, timeout=timeout_ms)
        display_val = page.evaluate(js_read_display, field_name)
        safe = display_val.encode("cp949", errors="replace").decode("cp949")
        print(f"[안내] {field_name}(자동계산 표시) 반영 확인: '{safe}'")
    except PlaywrightTimeoutError:
        print(
            f"[경고] {field_name} 표시가 {timeout_ms}ms 내 채워지지 않았습니다. "
            "화면에서 수동으로 확인해 주세요."
        )


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


def click_info_card_title(page):
    """섹션 전환을 위해 카드 타이틀을 클릭합니다."""
    title_candidates = [
        ".card-title.fs-xl.text-info",
        'h3.card-title.fs-xl.text-info',
        'div.card-title.fs-xl.text-info',
    ]
    title_loc, title_sel = first_visible_locator(page, title_candidates)
    if not title_loc:
        raise ValueError("card-title(fs-xl text-info) 요소를 찾지 못했습니다.")
    title_loc.click()
    page.wait_for_timeout(300)
    print(f"[안내] 카드 타이틀 클릭 완료 (selector: {title_sel})")


def click_orderer_info_title(page):
    """주문자 정보 섹션 제목(collapseThree)을 클릭합니다."""
    title_candidates = [
        'a.card-title.fs-xl.text-info[data-target="#collapseThree"]',
        'a[data-target="#collapseThree"]',
        'a.card-title.fs-xl.text-info:has-text("주문자 정보")',
    ]
    title_loc, title_sel = first_visible_locator(page, title_candidates)
    if not title_loc:
        raise ValueError("주문자 정보 제목(collapseThree) 요소를 찾지 못했습니다.")
    title_loc.click()
    page.wait_for_timeout(300)
    print(f"[안내] 주문자 정보 제목 클릭 완료 (selector: {title_sel})")


def click_section_title(page, section_text: str):
    """지정한 섹션 제목(card-title)을 찾아 클릭합니다."""
    title_candidates = [
        f'a.card-title.fs-xl.text-info:has-text("{section_text}")',
        f'a[data-toggle="collapse"]:has-text("{section_text}")',
        f'text="{section_text}"',
    ]
    title_loc, title_sel = first_visible_locator(page, title_candidates)
    if not title_loc:
        raise ValueError(f"'{section_text}' 섹션 제목을 찾지 못했습니다.")
    title_loc.click()
    page.wait_for_timeout(300)
    print(f"[안내] '{section_text}' 섹션 클릭 완료 (selector: {title_sel})")


def select_dest_country_with_fallback(page):
    """dest_country_cd 선택 실패 시 data-dial='81'을 대체 선택합니다."""
    # 수취인/배송 관련 섹션을 먼저 펼쳐서 요소가 보이도록 만듭니다.
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
        print(f"[경고] dest_country_cd 선택 실패: {err}")

    # 전화번호 국가 선택 UI가 닫혀 있으면 먼저 열어줍니다.
    dial_open_candidates = [
        '[name="final_recvr_mobile_no_enc"] + .iti__selected-flag',
        '[name="final_recvr_mobile_no_enc"] ~ .iti .iti__selected-flag',
        '.iti__selected-flag',
    ]
    dial_open_loc, dial_open_sel = first_visible_locator(page, dial_open_candidates)
    if dial_open_loc:
        dial_open_loc.click()
        page.wait_for_timeout(300)
        print(f"[안내] 국가코드 목록 열기 클릭 (selector: {dial_open_sel})")

    fallback_candidates = [
        '[data-dial="81"]',
        'li[data-dial="81"]',
        'a[data-dial="81"]',
        'span[data-dial="81"]',
    ]

    # 현재 페이지 + 모든 프레임 범위에서 탐색합니다.
    fallback_loc, fallback_sel = first_visible_locator(page, fallback_candidates)
    if not fallback_loc:
        for frame in page.frames:
            frame_loc, frame_sel = first_visible_locator(frame, fallback_candidates)
            if frame_loc:
                fallback_loc, fallback_sel = frame_loc, frame_sel
                break

    if not fallback_loc:
        raise ValueError("dest_country_cd 대체 선택(data-dial='81') 요소를 찾지 못했습니다.")

    fallback_loc.click()
    page.wait_for_timeout(500)
    print(f"[안내] data-dial='81' 대체 선택 완료 (selector: {fallback_sel})")


def select_intl_delivery_company_with_fallback(page):
    """intl_dlvr_base_cd를 보이게 한 뒤 일본 국제배송사를 선택합니다."""
    for section_name in ["국제배송 정보", "국제 배송 정보", "배송 정보", "배송사 정보"]:
        try:
            click_section_title(page, section_name)
            break
        except Exception:
            continue

    # 요소가 숨김 상태여도 JS로 값을 설정하고 change 이벤트를 발생시킵니다.
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
        print(f"[안내] intl_dlvr_base_cd='{selected_value}' 선택 완료")
        return

    # 드롭다운을 수동으로 열어 텍스트 기반으로 선택합니다.
    open_candidates = [
        'select[name="intl_dlvr_base_cd"]',
        '#intl_dlvr_base_cd',
        '[name="intl_dlvr_base_cd"]',
    ]
    open_loc, open_sel = first_visible_locator(page, open_candidates)
    if open_loc:
        open_loc.click()
        page.wait_for_timeout(300)
        print(f"[안내] 국제배송사 목록 열기 클릭 (selector: {open_sel})")

    option_candidates = [
        'option:has-text("J국제배송사(일본)")',
        'li:has-text("J국제배송사(일본)")',
        'a:has-text("J국제배송사(일본)")',
        'span:has-text("J국제배송사(일본)")',
        'text="J국제배송사(일본)"',
    ]
    option_loc, option_sel = first_visible_locator(page, option_candidates)
    if not option_loc:
        raise ValueError("intl_dlvr_base_cd 대체 선택 요소를 찾지 못했습니다.")
    option_loc.click()
    page.wait_for_timeout(500)
    print(f"[안내] 국제배송사 대체 선택 완료 (selector: {option_sel})")


def click_save_button(page, *, confirm_swal: bool = False):
    """
    저장 버튼(#saveBtn 등)만 클릭합니다.
    기본(confirm_swal=False): SweetAlert·알림 확인은 자동으로 누르지 않습니다.
    confirm_swal=True: 첫 번째 저장 확인창만 자동 클릭합니다(후속 알림은 여전히 수동).
    """
    save_btn_candidates = [
        'button:has-text("저장")',
        'a:has-text("저장")',
        '#saveBtn',
        '[name="saveBtn"]',
        '.btn.btn-primary:has-text("저장")',
    ]
    save_btn, save_sel = first_visible_locator(page, save_btn_candidates)
    if not save_btn:
        raise ValueError("'저장' 버튼을 찾지 못했습니다.")

    print(f"[디버그] 저장 버튼 셀렉터: {save_sel}")
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
            print("[안내] 저장 확인창에서 '확인'을 클릭했습니다.")
            page.wait_for_timeout(400)
            print(
                "[안내] 후속 알림 창이 있으면 자동으로 누르지 않습니다. "
                "화면에서 최종 확인 후 직접 처리해 주세요."
            )
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


def fill_order_detail_fields(
    page,
    stamp_mmddhhmm: str,
    stamp_yymmddhhmm: str,
    stamp_yymmddhh: str,
):
    """
    요청한 주문 상세 필드를 자동 입력합니다.
    - stamp_mmddhhmm: 월일시분 (%m%d%H%M)
    - stamp_yymmddhhmm: 연월일시분 (%y%m%d%H%M)
    - stamp_yymmddhh: 연월일시 분 생략 (%y%m%d%H)
    """
    # 수량·판매단가는 보통 pymt_price 등 결제금앨 자동계산 트리거가 붙습니다.
    fill_field(page, "od_qty", "3", trigger_derived_calc=True)
    fill_field(page, "sach_sale_price", "300", trigger_derived_calc=True)
    wait_until_derived_field_nonempty(page, "pymt_price")
    fill_field(page, "mall_prod_url", "https://www.qoo10.jp")
    click_section_title(page, "주문 상세")  # mall_prod_url 이후 주문 상세 클릭
    fill_field(page, "mall_od_no", f"JJ{stamp_yymmddhhmm}", required=False)
    click_orderer_info_title(page)  # 쇼핑몰 주문번호 입력 후 주문자 정보 클릭
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

    fill_field_by_candidates(page, ["final_dlvr_zipcd", "dlvr_zipcd", "zipcd"], "1600023", required=False)
    fill_field_by_candidates(
        page,
        ["final_dlvr_total_addr", "dlvr_total_addr", "total_addr", "dlvr_addr"],
        "東京都新宿区西新宿6-6-2",
        required=False,
    )
    fill_field(page, "dlvr_msg", f"도착보장 {stamp_mmddhhmm} 입니다.")
    click_info_card_title(page)
    select_intl_delivery_company_with_fallback(page)


def run():
    """로그인 상태 확인 후 세션을 유지합니다."""
    creds = load_env_credentials()
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")
    print(f"[안내] 시간값 YYMMDDHHMM: {stamp_yymmddhhmm}")
    print(f"[안내] 시간값 YYMMDDHH: {stamp_yymmddhh}")
    print(f"[안내] 시간값 MMDDHHMM: {stamp_mmddhhmm}")

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds)
            open_order_add_page(page, CONFIG)
            select_order_form_values(page)
            search_product_in_popup(page, "P000000000071918")
            click_select_button(page)
            fill_order_detail_fields(page, stamp_mmddhhmm, stamp_yymmddhhmm, stamp_yymmddhh)
            # 저장 후 alert/SweetAlert는 자동 클릭하지 않음 (수동 확인)
            click_save_button(page, confirm_swal=False)
            print(
                "[안내] 자동화 및 저장 버튼 클릭까지 완료했습니다. "
                "확인창은 직접 처리해 주세요."
            )
            try:
                input("확인창에서 직접 처리하신 뒤, 종료하려면 Enter를 누르세요...")
            except EOFError:
                print(
                    "[안내] 표준 입력이 없거나 닫혀 있어 Enter 대기를 건너뜁니다. "
                    "브라우저·확인창을 확인해 주세요."
                )
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
