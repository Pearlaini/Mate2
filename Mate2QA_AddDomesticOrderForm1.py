# QA site 샘플화주사
from datetime import datetime
from pathlib import Path
from typing import Dict, Union

from playwright.sync_api import Frame, Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
)


# =========================
# 사용자 설정 영역 (URL은 Mate2QA_site_config.py _DEFAULT_LOGIN_URL)
# =========================
CONFIG = {
    **_SITE_CONFIG,
    # 국내 수기 화면의 판매채널 option value (환경에 맞게 변경)
    "sach_cd_value": "SACH0020",
    "sample_product_cd": "P000000000005754",
    # 배송지 우편번호 팝업 검색어
    "address_search_keyword": "지플러스타워",
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

# 해외용 storage_state.json과 덮어쓰기 충돌을 피합니다.
STATE_FILE = STATE_FILE_DOMESTIC


def select_company_value(page):
    """pwn_header_change에서 화주사 선택합니다."""
    selector = 'select[name="pwn_header_change"]'
    target_label = "★샘플 화주사"

    if page.locator(selector).count() > 0:
        page.select_option(selector, label=target_label)
        print(f"[안내] '{target_label}' 값을 선택했습니다.")
        return

    trigger_candidates = [
        "#pwn_header_change",
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

    print(
        "[경고] pwn_header_change 요소를 찾지 못했습니다. "
        "회사가 이미 선택된 환경으로 보고 회사 전환 단계를 건너뜁니다."
    )


def open_domestic_order_register_page(page, config: Dict):
    """국내 주문목록으로 이동한 뒤 주문서 추가 화면으로 진입합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 국내 주문목록으로 이동했습니다. 현재 URL: {page.url}")

    select_company_value(page)

    add_btn_candidates = [
        'button:has-text("주문서추가")',
        'a:has-text("주문서추가")',
        'button:has-text("등록")',
        'a:has-text("등록")',
    ]
    add_btn, btn_sel = first_visible_locator(page, add_btn_candidates)
    if add_btn:
        print(f"[디버그] 주문서추가 버튼 셀렉터: {btn_sel}")
        add_btn.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        print(f"[안내] 주문서추가 클릭 완료. 현재 URL: {page.url}")
        return

    print(
        "[안내] 주문서추가 버튼을 찾지 못해 수기등록 URL로 직접 이동합니다. "
        f"(대상: {config['order_register_url']})"
    )
    page.goto(config["order_register_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    select_company_value(page)
    print(f"[안내] 수기등록 페이지 로드 완료. 현재 URL: {page.url}")


def select_domestic_sach_cd(page, sach_cd_value: str):
    """국내 수기 화면에서 판매채널(sach_cd)을 value 기준으로 선택합니다."""
    page.wait_for_timeout(1000)
    select_loc = page.locator('select[name="sach_cd"]').first
    if select_loc.count() == 0:
        raise ValueError("select[name='sach_cd'] 요소를 찾지 못했습니다.")

    picked = select_loc.evaluate(
        """(el, target) => {
            const opts = Array.from(el.options || []);
            if (opts.some(o => o.value === target)) {
                el.value = target;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return target;
            }
            const first = opts.find(o => o.value && o.value.trim() !== '');
            if (first) {
                el.value = first.value;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return first.value;
            }
            return '';
        }""",
        sach_cd_value,
    )
    if not picked:
        raise ValueError("sach_cd에서 선택 가능한 option value가 없습니다.")
    print(f"[안내] sach_cd='{picked}' 선택 완료 (요청 value: {sach_cd_value})")


def search_product_in_popup(page, product_code: str):
    """상품 검색 팝업에서 상품코드로 조회를 실행합니다. (국내: searchProdBtn 우선)"""
    search_btn_candidates = [
        "#searchProdBtn",
        '[id="searchProdBtn"]',
        'button.btn.btn-secondary.btn-sm.p-2.ml-2.waves-effect.waves-themed',
        'button:has-text("상품 검색")',
        'a:has-text("상품 검색")',
    ]
    search_btn, btn_sel = first_visible_locator(page, search_btn_candidates)
    if not search_btn:
        raise ValueError("'상품 검색' 또는 searchProdBtn을 찾지 못했습니다. selector를 확인해 주세요.")

    print(f"[디버그] 상품 검색 버튼 셀렉터: {btn_sel}")
    search_btn.click()
    page.wait_for_timeout(1200)

    if page.locator('select[name="searchColumn"]').count() > 0:
        page.select_option('select[name="searchColumn"]', value="prod_cd")
    else:
        dropdown_candidates = [
            "#searchColumn",
            '[name="searchColumn"]',
        ]
        dropdown, _ = first_visible_locator(page, dropdown_candidates)
        if not dropdown:
            raise ValueError("searchColumn 요소를 찾지 못했습니다.")
        dropdown.click()
        page.locator('text="prod_cd"').first.click()

    txt_candidates = [
        'input[name="searchTxt"]',
        "#searchTxt",
    ]
    txt_input, txt_sel = first_visible_locator(page, txt_candidates)
    if not txt_input:
        raise ValueError("searchTxt 입력 요소를 찾지 못했습니다.")
    txt_input.fill(product_code)
    print(f"[디버그] searchTxt 셀렉터: {txt_sel}")

    search_candidates = [
        "#prodSearchBtn",
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
        ".tabulator-row .btn-info",
        "button.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1",
        "a.btn.btn-xs.btn-info.waves-effect.waves-themed.mt-1",
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
        f"#{field_name}",
    ]
    field, sel = first_visible_locator(page, candidates)
    if not field:
        if required:
            raise ValueError(f"{field_name} 입력 요소를 찾지 못했습니다.")
        print(f"[경고] {field_name} 입력 요소를 찾지 못해 건너뜁니다.")
        return
    try:
        blocked = field.evaluate("(el) => !!(el.readOnly || el.disabled)")
    except Exception:
        blocked = False
    if blocked:
        if required:
            raise ValueError(f"{field_name} 입력 요소가 읽기 전용·비활성입니다.")
        print(f"[경고] {field_name}이(가) 읽기 전용·비활성이라 건너뜁니다.")
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
    """자동 계산으로 채워지는 필드가 비어 있지 않을 때까지 대기합니다."""
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
    """여러 필드명 후보 중 먼저 찾은 편집 가능한 필드에 값을 입력합니다."""
    for name in field_names:
        candidates = [
            f'input[name="{name}"]',
            f'textarea[name="{name}"]',
            f"#{name}",
        ]
        field, sel = first_visible_locator(page, candidates)
        if field:
            # 국내 배송: 우편번호·기본주소는 readonly + zipModal 전용인 경우가 많음
            try:
                blocked = field.evaluate(
                    "(el) => !!(el.readOnly || el.disabled)"
                )
            except Exception:
                blocked = False
            if blocked:
                print(
                    f"[안내] {name}은(는) 읽기 전용·비활성입니다. "
                    "우편번호 검색으로만 채워지는 필드일 수 있어 다음 후보로 넘어갑니다."
                )
                continue
            field.fill(value)
            safe_value = value.encode("cp949", errors="replace").decode("cp949")
            print(f"[안내] {name}='{safe_value}' 입력 완료 (selector: {sel})")
            return

    if required:
        joined = ", ".join(field_names)
        raise ValueError(f"입력 요소를 찾지 못했습니다. 후보: {joined}")
    print(f"[경고] 입력 요소를 찾지 못해 건너뜁니다. 후보: {', '.join(field_names)}")


def click_orderer_info_title(page):
    """주문자 정보 섹션 제목을 클릭합니다."""
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


def _root_wait_ms(root: Union[Page, Frame], ms: int) -> None:
    """Page 또는 Frame 기준으로 대기합니다."""
    if isinstance(root, Page):
        root.wait_for_timeout(ms)
    else:
        root.page.wait_for_timeout(ms)


def _click_domestic_address_search_trigger(page: Page) -> bool:
    """배송지 검색(아이콘 fa-search-location 또는 zipModal) 버튼을 클릭합니다."""
    candidates = [
        "button:has(i.fal.fa-search-location)",
        "span:has(i.fal.fa-search-location)",
        "a:has(i.fal.fa-search-location)",
        "i.fal.fa-search-location",
        "i[class*='fa-search-location']",
        "span[onclick*='zipModal']",
    ]
    loc, sel = first_visible_locator(page, candidates)
    if not loc:
        return False
    loc.click()
    print(f"[안내] 배송지 주소 검색 트리거 클릭 (selector: {sel})")
    return True


def _find_frame_with_region_input(host_page: Page) -> Union[Frame, None]:
    """input#region_name(또는 name=region_name)이 있는 프레임을 찾습니다."""
    for fr in host_page.frames:
        if fr.is_detached():
            continue
        try:
            if fr.locator("input#region_name").count() > 0:
                return fr
            if fr.locator('input[name="region_name"]').count() > 0:
                return fr
        except PlaywrightTimeoutError:
            continue
    return None


def _submit_address_keyword(root: Union[Page, Frame], keyword: str) -> None:
    """region_name에 키워드 입력 후 btn_search 클릭."""
    region = root.locator("input#region_name[title='주소 검색']").first
    if region.count() == 0:
        region = root.locator("input#region_name").first
    if region.count() == 0:
        region = root.locator('input[name="region_name"]').first
    if region.count() == 0:
        raise ValueError("팝업에서 region_name(주소 검색) 입력칸을 찾지 못했습니다.")
    # placeholder span이 포인터 이벤트를 가로채는 UI → 강제 입력
    region.fill(keyword, force=True)
    print(f"[안내] 주소 검색어 입력: {keyword}")

    search_btn = root.locator(".btn_search").first
    if search_btn.count() == 0:
        search_btn = root.locator("button.btn_search").first
    if search_btn.count() == 0:
        raise ValueError("팝업에서 btn_search 버튼을 찾지 못했습니다.")
    search_btn.click()
    print("[안내] 주소 검색(btn_search) 클릭 완료")


def _wait_domestic_base_address_filled(page: Page, timeout_ms: int = 8000) -> None:
    """주소 팝업 선택 후 우편·기본주소(readonly)가 채워졌는지 확인합니다."""
    # 사이트별로 우편번호·기본주소 name이 달라서, addr/zip/post 계열 값을 통합 검사합니다.
    js_collect_address_values = """() => {
        const include = /(addr|zip|post)/i;
        const exclude = /(detail|msg|message|search|region)/i;
        const elements = Array.from(
            document.querySelectorAll('input, textarea, select')
        );
        return elements
            .map((el) => {
                const key = `${el.name || ''} ${el.id || ''}`.trim();
                const value = String(el.value || '').trim();
                return { key, value };
            })
            .filter((item) => item.key && include.test(item.key))
            .filter((item) => !exclude.test(item.key))
            .filter((item) => item.value);
    }"""

    try:
        page.wait_for_function(
            """() => {
                const include = /(addr|zip|post)/i;
                const exclude = /(detail|msg|message|search|region)/i;
                const elements = Array.from(
                    document.querySelectorAll('input, textarea, select')
                );
                return elements
                    .map((el) => {
                        const key = `${el.name || ''} ${el.id || ''}`.trim();
                        const value = String(el.value || '').trim();
                        return { key, value };
                    })
                    .filter((item) => item.key && include.test(item.key))
                    .filter((item) => !exclude.test(item.key))
                    .filter((item) => item.value)
                    .length > 0;
            }""",
            timeout=timeout_ms,
        )
        values = page.evaluate(js_collect_address_values)
    except PlaywrightTimeoutError as exc:
        debug_values = page.evaluate(
            """() => Array.from(document.querySelectorAll('input, textarea, select'))
                .map((el) => ({
                    key: `${el.name || ''} ${el.id || ''}`.trim(),
                    value: String(el.value || '').trim()
                }))
                .filter((item) => item.key && /(addr|zip|post)/i.test(item.key))
                .slice(0, 20)"""
        )
        print(f"[디버그] 주소 관련 필드 후보: {debug_values}")
        raise ValueError(
            "주소 검색 결과를 클릭했지만 우편번호·기본주소 반영을 확인하지 못했습니다. "
            "화면의 배송지 우편번호·기본주소 필드 name/id를 확인해 주세요."
        ) from exc

    first = values[0]
    safe_key = str(first.get("key", "")).encode("cp949", errors="replace").decode("cp949")
    safe_value = str(first.get("value", "")).encode("cp949", errors="replace").decode("cp949")
    print(f"[안내] 주소 선택 반영 확인: {safe_key}='{safe_value[:60]}'")


def _click_first_address_search_result(root: Union[Page, Frame]) -> None:
    """
    검색 결과 목록의 첫 번째 항목을 클릭합니다.
    Daum 우편번호 팝업: ul.list_post > li.list_post_item > button.link_post
    (지번 결과는 ul.list_addr / li.list_addr_item 동일 패턴)
    """
    result_container_selectors = [
        "ul.list_post",
        "ul.list_addr",
    ]
    for container_sel in result_container_selectors:
        try:
            root.locator(container_sel).first.wait_for(
                state="visible", timeout=5000
            )
            break
        except PlaywrightTimeoutError:
            continue
    else:
        _root_wait_ms(root, 1500)

    # F12 기준: 실제 선택은 li가 아니라 button.link_post
    click_selectors = [
        "ul.list_post li.list_post_item button.link_post",
        "li.list_post_item button.link_post",
        "ul.list_post button.link_post",
        "ul.list_addr li.list_addr_item button.link_post",
        "li.list_addr_item button.link_post",
        "ul.list_addr button.link_post",
        "ul.list_post li.list_post_item",
        "ul.list_addr li.list_addr_item",
    ]
    for sel in click_selectors:
        loc = root.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.click(timeout=8000)
            addr_span = loc.locator("span.txt_addr").first
            if addr_span.count() > 0:
                text = (addr_span.inner_text(timeout=2000) or "").strip()[:80]
            else:
                text = (loc.inner_text(timeout=2000) or "").strip()[:80]
            print(
                f"[안내] 주소 검색 첫 번째 결과 클릭 (selector: {sel}, text: {text!r})"
            )
            return
        except PlaywrightTimeoutError:
            continue
    raise ValueError("주소 검색 결과에서 첫 번째 항목을 클릭하지 못했습니다.")


def fill_domestic_delivery_address_via_popup(
    page: Page,
    config: Dict,
    stamp_yymmddhhmm: str,
) -> None:
    """
    배송지: fa-search-location(또는 zipModal) → 같은 탭 내 iframe에서 region_name 검색
    → btn_search → 첫 번째 결과 선택 → 본 화면 dlvr_detail_addr에 '주소'+stamp_yymmddhhmm 입력.
    """
    keyword = config.get("address_search_keyword", "지플러스타워")

    if not _click_domestic_address_search_trigger(page):
        raise ValueError(
            "배송지 주소 검색 버튼(i.fal.fa-search-location 등)을 찾지 못했습니다."
        )

    # 새 창은 열리지 않음 — 현재 페이지의 iframe 안에서만 주소 UI를 찾습니다.
    page.wait_for_timeout(800)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    root = _find_frame_with_region_input(page)
    if root is None:
        raise ValueError(
            "주소 검색 iframe에서 region_name 입력칸을 찾지 못했습니다. "
            "iframe 구조를 확인해 주세요."
        )

    _submit_address_keyword(root, keyword)
    _click_first_address_search_result(root)
    _wait_domestic_base_address_filled(page)

    page.wait_for_timeout(300)

    detail = f"주소{stamp_yymmddhhmm}"
    fill_field(page, "dlvr_detail_addr", detail, required=False)


def try_select_domestic_dlvr_company(page):
    """국내 택배사 셀렉트가 있으면 첫 유효 option을 고릅니다. 없으면 무시합니다."""
    select_loc = page.locator('select[name="dlvr_base_cd"]').first
    if select_loc.count() == 0:
        print("[안내] dlvr_base_cd 가 없어 택배사 자동 선택을 건너뜁니다.")
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
    if picked:
        print(f"[안내] dlvr_base_cd='{picked}' 자동 선택")


def click_save_button(page, *, confirm_swal: bool = True):
    """저장 버튼을 클릭합니다."""
    save_btn_candidates = [
        'button:has-text("저장")',
        'a:has-text("저장")',
        "#saveBtn",
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
            if click_swal_confirm_if_visible(3000):
                print("[안내] 후속 알림 창에서 '확인'을 클릭했습니다.")
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


def fill_domestic_order_detail_fields(
    page,
    config: Dict,
    stamp_mmddhhmm: str,
    stamp_yymmddhhmm: str,
    stamp_yymmddhh: str,
):
    """
    국내 수기 주문 상세 필드를 입력합니다.
    배송지는 주소 검색 팝업(지플러스타워 등)으로 우편·기본주소를 채운 뒤,
    dlvr_detail_addr에 '주소'+stamp_yymmddhhmm 을 입력합니다.
    """
    fill_field(page, "od_qty", "3", trigger_derived_calc=True)
    # 레거시 국내 수기 스크립트와 동일하게 단가 1000
    fill_field(page, "sach_sale_price", "1000", trigger_derived_calc=True)
    wait_until_derived_field_nonempty(page, "pymt_price")
    fill_field(page, "mall_prod_url", "https://example.com", required=False)

    click_section_title(page, "주문 상세")
    # 국내 테스트용 쇼핑몰 주문번호
    fill_field(page, "mall_od_no", f"J{stamp_yymmddhhmm}", required=False)

    click_orderer_info_title(page)
    fill_field(page, "od_user_nm", f"국내주문{stamp_mmddhhmm}")
    od_tel = f"02-{stamp_yymmddhhmm[0:4]}-{stamp_yymmddhhmm[4:8]}"
    od_mobile = f"010-{stamp_yymmddhhmm[0:4]}-{stamp_yymmddhhmm[4:8]}"
    fill_field(page, "od_user_tel_no_enc", od_mobile)
    fill_field(page, "od_user_mobile_no_enc", od_tel, required=False)

    click_section_title(page, "수취인 정보")
    fill_field_by_candidates(
        page,
        ["recvr_nm", "final_recvr_nm"],
        f"국내수취{stamp_mmddhhmm}",
    )
    rv_tel = f"02-{stamp_yymmddhhmm[0:4]}-{stamp_yymmddhhmm[4:8]}"
    rv_mobile = f"010-{stamp_yymmddhhmm[0:4]}-{stamp_yymmddhhmm[4:8]}"
    fill_field_by_candidates(
        page,
        ["recvr_mobile_no_enc", "final_recvr_mobile_no_enc"],
        rv_tel,
    )
    fill_field_by_candidates(
        page,
        ["recvr_tel_no_enc", "final_recvr_tel_no_enc"],
        rv_tel,
        required=False,
    )

    click_section_title(page, "배송 정보")
    fill_domestic_delivery_address_via_popup(page, config, stamp_yymmddhhmm)
    fill_field(page, "dlvr_msg", f"Thanks {stamp_mmddhhmm}", required=False)

    try_select_domestic_dlvr_company(page)


def run():
    """로그인 후 국내 수기 주문 등록 자동화를 수행합니다."""
    print_site_url_banner()
    creds = load_env_credentials()
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")
    print(f"[안내] 시간값 YYMMDDHHMM: {stamp_yymmddhhmm}")
    print(f"[안내] 시간값 YYMMDDHH: {stamp_yymmddhh}")
    print(f"[안내] 시간값 MMDDHHMM: {stamp_mmddhhmm}")

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            open_domestic_order_register_page(page, CONFIG)
            select_domestic_sach_cd(page, CONFIG["sach_cd_value"])
            search_product_in_popup(page, CONFIG["sample_product_cd"])
            click_select_button(page)
            fill_domestic_order_detail_fields(
                page,
                CONFIG,
                stamp_mmddhhmm,
                stamp_yymmddhhmm,
                stamp_yymmddhh,
            )
            # 저장 후 SweetAlert/알림은 자동으로 누르지 않음 (수동 확인)
            click_save_button(page, confirm_swal=False)
            print("[안내] 국내 수기등록 자동화 및 저장(확인창 포함)까지 완료했습니다.")
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
