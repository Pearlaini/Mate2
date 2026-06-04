# QA WMS 출고 수기등록 — 로그인 → 출고예정 → 수기등록 폼 입력 → 출고대상 품목
# 사이트 호스트는 Mate2QA_site_config.py 로그인 URL 기준, 경로는 상대 path 사용

from datetime import datetime
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
    OUT_EXPECT_LIST_PATH,
    STATE_FILE_DOMESTIC,
    join_origin_path,
    print_site_url_banner,
)

# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    **_SITE_CONFIG,
    "out_expect_list_path": OUT_EXPECT_LIST_PATH,
    "address_search_keyword": "지플러스타워",
    "sach_cd_value": "SACH0020",
    "target_product_search_keyword": "크래커",
}

STATE_FILE = STATE_FILE_DOMESTIC


def goto_out_expect_list(page, config: Dict) -> None:
    """WMS 출고예정 목록(/wm/out/reg/outExpectList.do)으로 이동합니다."""
    path = config.get("out_expect_list_path", OUT_EXPECT_LIST_PATH)
    url = join_origin_path(config["login_url"], path)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] WMS 출고예정 목록으로 이동했습니다. 현재 URL: {page.url}")


def click_out_expect_manual_register(page) -> None:
    """출고예정 목록에서 '출고 수기등록' 버튼을 클릭합니다."""
    btn_candidates = [
        "#outExpectRgstBtn",
        'button#outExpectRgstBtn:has-text("출고 수기등록")',
        'button:has-text("출고 수기등록")',
        'a:has-text("출고 수기등록")',
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'출고 수기등록' 버튼(#outExpectRgstBtn)을 찾지 못했습니다.")

    print(f"[디버그] 출고 수기등록 버튼 셀렉터: {btn_sel}")
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] '출고 수기등록' 버튼 클릭 완료. 현재 URL: {page.url}")


def fill_field(page, field_name: str, value: str, *, required: bool = True) -> None:
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
    safe_value = value.encode("cp949", errors="replace").decode("cp949")
    print(f"[안내] {field_name}='{safe_value}' 입력 완료 (selector: {sel})")


def select_sach_cd(page, option_value: str) -> None:
    """판매채널(sach_cd)을 value 기준으로 선택합니다."""
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
            const byLabel = opts.find(o => o.textContent && o.textContent.trim() === 'J채널');
            if (byLabel) {
                el.value = byLabel.value;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return byLabel.value;
            }
            return '';
        }""",
        option_value,
    )
    if not picked:
        raise ValueError(f"sach_cd에서 value={option_value}(J채널)을 선택하지 못했습니다.")
    print(f"[안내] sach_cd='{picked}'(J채널) 선택 완료")


def _root_wait_ms(root: Union[Page, Frame], ms: int) -> None:
    if isinstance(root, Page):
        root.wait_for_timeout(ms)
    else:
        root.page.wait_for_timeout(ms)


def _click_recvr_address_search_trigger(page: Page) -> bool:
    """수취인 주소 zipModal 검색 버튼을 클릭합니다."""
    candidates = [
        "#button-addon5",
        "button[onclick*=\"zipModal('recvr_zipcd'\"]",
        "button[onclick*='recvr_zipcd']",
        "button:has(i.fal.fa-search)",
        "span[onclick*='zipModal']",
        "button:has(i.fal.fa-search-location)",
        "span:has(i.fal.fa-search-location)",
        "i.fal.fa-search",
    ]
    loc, sel = first_visible_locator(page, candidates)
    if not loc:
        return False
    loc.click()
    print(f"[안내] 수취인 주소 검색 트리거 클릭 (selector: {sel})")
    return True


def _get_host_page(root: Union[Page, Frame]) -> Page:
    return root if isinstance(root, Page) else root.page


def _find_address_search_root(host: Page) -> Union[Page, Frame, None]:
    """region_name 입력란이 있는 Page/Frame을 찾습니다 (중첩 iframe·새 창 포함)."""
    region_sel = "input#region_name, input[name='region_name']"

    def _has_region(scope: Union[Page, Frame]) -> bool:
        try:
            if isinstance(scope, Frame) and scope.is_detached():
                return False
            return scope.locator(region_sel).first.count() > 0
        except PlaywrightTimeoutError:
            return False

    if _has_region(host):
        return host

    for fr in host.frames:
        if _has_region(fr):
            return fr
        for child in fr.child_frames:
            if _has_region(child):
                return child

    for pg in host.context.pages:
        if pg.is_closed() or pg == host:
            continue
        if _has_region(pg):
            return pg
        for fr in pg.frames:
            if _has_region(fr):
                return fr
            for child in fr.child_frames:
                if _has_region(child):
                    return child

    return None


def _locate_region_input(root: Union[Page, Frame]):
    for sel in (
        "input#region_name[title='주소 검색']",
        "input#region_name",
        'input[name="region_name"]',
    ):
        loc = root.locator(sel).first
        if loc.count() > 0:
            return loc
    return None


def _trigger_address_search(root: Union[Page, Frame], region) -> None:
    """Enter 키 전송 후, 실패 시 button.btn_search를 JS로 클릭합니다."""
    host_page = _get_host_page(root)

    region.evaluate(
        """(el) => {
            const opts = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
            el.dispatchEvent(new KeyboardEvent('keydown', opts));
            el.dispatchEvent(new KeyboardEvent('keypress', opts));
            el.dispatchEvent(new KeyboardEvent('keyup', opts));
        }"""
    )
    region.press("Enter")
    host_page.wait_for_timeout(600)

    clicked = root.evaluate(
        """() => {
            const btn = document.querySelector('button.btn_search');
            if (btn) { btn.click(); return 'button.btn_search'; }
            const icon = document.querySelector('span.img_post');
            const parent = icon && icon.closest('button');
            if (parent) { parent.click(); return 'span.img_post'; }
            return '';
        }"""
    )
    if clicked:
        print(f"[안내] 주소 검색 보조 클릭 ({clicked})")
    else:
        print("[안내] 주소 검색 Enter 키 전송 완료")
    host_page.wait_for_timeout(800)


def _submit_address_keyword(root: Union[Page, Frame], keyword: str) -> None:
    """region_name에 검색어 입력 후 Enter(및 btn_search fallback)로 검색합니다."""
    region = _locate_region_input(root)
    if region is None:
        raise ValueError("팝업에서 region_name(주소 검색) 입력칸을 찾지 못했습니다.")

    region.click(force=True)
    region.fill(keyword, force=True)
    print(f"[안내] 주소 검색어 입력: {keyword}")

    _trigger_address_search(root, region)
    _wait_address_search_results(root)


def _wait_address_search_results(root: Union[Page, Frame], timeout_ms: int = 10_000) -> None:
    """Enter 검색 후 첫 번째 주소 목록 항목이 보일 때까지 대기합니다."""
    first_item_selectors = [
        "ul.list_post li.list_post_item:first-child",
        "ul.list_addr li.list_addr_item:first-child",
        "ul.list_post li.list_post_item",
        "ul.list_addr li.list_addr_item",
        "button.link_post",
    ]
    for sel in first_item_selectors:
        try:
            root.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
            print(f"[안내] 주소 검색 결과(첫 항목) 표시 확인 ({sel})")
            return
        except PlaywrightTimeoutError:
            continue
    raise ValueError(
        "Enter 검색 후 주소 목록이 나타나지 않았습니다. 검색어·iframe을 확인해 주세요."
    )


def _get_recvr_address_values(page: Page) -> Dict[str, str]:
    """수취인 우편번호·기본주소 필드 값만 읽습니다."""
    return page.evaluate(
        """() => {
            const read = (selectors) => {
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    const value = el && String(el.value || '').trim();
                    if (value) return value;
                }
                return '';
            };
            return {
                zip: read(['#recvr_zipcd', '[name="recvr_zipcd"]']),
                addr: read(['#recvr_addr', '[name="recvr_addr"]']),
            };
        }"""
    )


def _has_recvr_base_address(page: Page) -> bool:
    values = _get_recvr_address_values(page)
    return bool(values.get("zip") and values.get("addr"))


def _wait_recvr_base_address_filled(page: Page, timeout_ms: int = 8000) -> None:
    """주소 팝업 선택 후 recvr_zipcd·recvr_addr가 실제로 채워졌는지 확인합니다."""
    try:
        page.wait_for_function(
            """() => {
                const zip = document.querySelector('#recvr_zipcd, [name="recvr_zipcd"]');
                const addr = document.querySelector('#recvr_addr, [name="recvr_addr"]');
                const z = zip && String(zip.value || '').trim();
                const a = addr && String(addr.value || '').trim();
                return Boolean(z && a);
            }""",
            timeout=timeout_ms,
        )
        values = _get_recvr_address_values(page)
        print(
            "[안내] 수취인 주소 반영 확인: "
            f"recvr_zipcd='{values.get('zip', '')}', recvr_addr='{values.get('addr', '')[:60]}'"
        )
    except PlaywrightTimeoutError as exc:
        values = _get_recvr_address_values(page)
        raise ValueError(
            "주소 검색 결과를 선택했지만 recvr_zipcd·recvr_addr 값이 채워지지 않았습니다. "
            f"현재값: {values}"
        ) from exc


def _click_first_address_via_js(scope: Union[Page, Frame]) -> str:
    """첫 번째 검색 결과에서 span.value 등 실제 주소 값 영역을 JS로 클릭합니다."""
    picked = scope.evaluate(
        """() => {
            const item = document.querySelector(
                'ul.list_post li.list_post_item, ul.list_addr li.list_addr_item'
            );
            if (!item) return '';
            const targets = [
                item.querySelector('span.value'),
                item.querySelector('.value'),
                item.querySelector('[value]'),
                item.querySelector('span.txt_addr'),
                item.querySelector('button.link_post'),
                item,
            ].filter(Boolean);
            for (const el of targets) {
                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                if (typeof el.click === 'function') el.click();
                const text = (el.textContent || '').trim().slice(0, 80);
                const cls = el.className ? '.' + String(el.className).trim().split(/\\s+/)[0] : el.tagName;
                return cls + (text ? ':' + text : '');
            }
            return '';
        }"""
    )
    return picked or ""


def _click_first_address_search_result(
    host_page: Page, search_root: Union[Page, Frame]
) -> None:
    """주소 검색 결과 첫 항목 — span.value(주소 값) 영역을 우선 클릭합니다."""
    scopes: list = []
    for scope in (search_root, host_page):
        if scope not in scopes:
            scopes.append(scope)

    # value(우편/주소 텍스트) → 실제 선택 버튼 → 주소 텍스트 순
    first_item_selectors = [
        "ul.list_post li.list_post_item:first-child span.value",
        "ul.list_post li.list_post_item:first-child .value",
        "ul.list_post li.list_post_item:first-child [value]",
        "ul.list_addr li.list_addr_item:first-child span.value",
        "li.list_post_item:first-child span.value",
        "ul.list_post li.list_post_item:first-child button.link_post",
        "ul.list_addr li.list_addr_item:first-child button.link_post",
        "ul.list_post li.list_post_item:first-child span.txt_addr",
        "ul.list_post li.list_post_item:first-child",
        "ul.list_addr li.list_addr_item:first-child",
    ]

    for scope in scopes:
        for sel in first_item_selectors:
            loc = scope.locator(sel).first
            try:
                if loc.count() == 0:
                    continue
                loc.wait_for(state="visible", timeout=5000)
                loc.click(timeout=8000, force=True)
                text = (loc.inner_text(timeout=2000) or "").strip()[:80]
                scope_name = "iframe" if isinstance(scope, Frame) else "page"
                print(
                    f"[안내] 주소 첫 항목 value 클릭 ({scope_name}, {sel}, text: {text!r})"
                )
                host_page.wait_for_timeout(800)
                if _has_recvr_base_address(host_page):
                    return
                print("[경고] 클릭 후 주소값이 아직 비어 있어 다음 후보를 시도합니다.")
            except PlaywrightTimeoutError:
                continue

        js_hint = _click_first_address_via_js(scope)
        if js_hint:
            scope_name = "iframe" if isinstance(scope, Frame) else "page"
            print(f"[안내] 주소 첫 항목 JS 클릭 ({scope_name}, {js_hint})")
            host_page.wait_for_timeout(800)
            if _has_recvr_base_address(host_page):
                return
            print("[경고] JS 클릭 후 주소값이 아직 비어 있어 다음 후보를 시도합니다.")

    # 키보드로 첫 항목 선택 (↓ + Enter)
    region = _locate_region_input(search_root)
    if region is not None:
        region.press("ArrowDown")
        host_page.wait_for_timeout(200)
        region.press("Enter")
        host_page.wait_for_timeout(800)
        print("[안내] 주소 첫 항목 키보드(↓+Enter) 선택 시도")
        if _has_recvr_base_address(host_page):
            return

    raise ValueError(
        "주소 검색 결과 첫 번째 항목을 클릭했지만 recvr_zipcd·recvr_addr 값이 채워지지 않았습니다."
    )


def _click_address_popup_close(page: Page) -> None:
    """첫 주소 선택 후 주소 팝업 '닫기' 버튼(#addrCloseBtn)을 클릭합니다."""
    modal = page.locator("#zip_layer.modal.show, #zip_layer[aria-modal='true']").first
    try:
        if modal.count() == 0 or not modal.is_visible():
            return
    except PlaywrightTimeoutError:
        return

    close_candidates = [
        "#addrCloseBtn",
        'button#addrCloseBtn[data-dismiss="modal"]',
        '#zip_layer #addrCloseBtn',
        'button:has-text("닫기")',
        "#zip_layer button[data-dismiss='modal']:has-text('닫기')",
        "#zip_layer button.close",
        "#zip_layer .close",
        '#zip_layer [aria-label="Close"]',
    ]
    btn, sel = first_visible_locator(page, close_candidates)
    if not btn:
        page.keyboard.press("Escape")
        print("[경고] #addrCloseBtn을 찾지 못해 Escape로 닫기 시도")
    else:
        btn.click(timeout=10_000)
        print(f"[안내] 주소 팝업 '닫기' 클릭 (selector: {sel})")

    try:
        page.locator("#zip_layer").first.wait_for(state="hidden", timeout=8000)
        print("[안내] 주소 팝업(#zip_layer) 닫힘 확인")
    except PlaywrightTimeoutError:
        page.evaluate(
            """() => {
                const m = document.querySelector('#zip_layer');
                if (!m) return;
                m.classList.remove('show');
                m.style.display = 'none';
                m.setAttribute('aria-hidden', 'true');
                document.body.classList.remove('modal-open');
                document.querySelectorAll('.modal-backdrop').forEach((el) => el.remove());
            }"""
        )
        print("[안내] 주소 팝업(#zip_layer) JS로 닫기 처리")
    page.wait_for_timeout(400)


def _close_zip_address_modal(page: Page) -> None:
    """주소 팝업이 남아 있으면 닫기 (#addrCloseBtn 우선)."""
    _click_address_popup_close(page)


def fill_recvr_address_via_popup(page: Page, config: Dict) -> None:
    """
    수취인 주소: zipModal → 주소 검색(iframe/새 창) → 첫 결과 선택.
    (Mate2QA_AddDomesticOrderForm.py 배송지 주소 팝업 흐름과 동일)
    """
    keyword = config.get("address_search_keyword", "지플러스타워")
    pages_before = len(page.context.pages)

    if not _click_recvr_address_search_trigger(page):
        raise ValueError("수취인 주소 검색 버튼(zipModal)을 찾지 못했습니다.")

    page.wait_for_timeout(1200)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    if len(page.context.pages) > pages_before:
        popup = page.context.pages[-1]
        print(f"[안내] 주소 검색 새 창 감지. URL: {popup.url}")
        search_host = popup
    else:
        search_host = page

    root = _find_address_search_root(search_host)
    if root is None:
        raise ValueError(
            "주소 검색 화면(iframe/새 창)에서 region_name 입력칸을 찾지 못했습니다."
        )

    _submit_address_keyword(root, keyword)
    _click_first_address_search_result(page, root)
    page.wait_for_timeout(800)

    if search_host is not page and not search_host.is_closed():
        try:
            search_host.close()
            page.bring_to_front()
        except Exception:
            pass

    _wait_recvr_base_address_filled(page)
    _click_address_popup_close(page)
    page.wait_for_timeout(300)


def _stamp_1mddhhmm(now: datetime) -> str:
    """월(선행 0 없음) + DDHHMM — 예: 6월 4일 14:30 → 6041430"""
    return f"{now.month}{now.strftime('%d%H%M')}"


def _build_recvr_detail_addr(stamp_mmddhhmm: str) -> str:
    """MMDD + 번지 + HH + 동 + MM + 호"""
    mmdd, hh, mm = stamp_mmddhhmm[0:4], stamp_mmddhhmm[4:6], stamp_mmddhhmm[6:8]
    return f"{mmdd}번지{hh}동{mm}호"


def fill_wm_manual_register_form(page, config: Dict, now: datetime) -> None:
    """출고 수기등록 폼 필드를 요청 순서대로 입력합니다."""
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yyyymmddhhmm = now.strftime("%Y%m%d%H%M")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")
    stamp_1mddhhmm = _stamp_1mddhhmm(now)
    mobile = f"010{stamp_1mddhhmm}"

    print(f"[안내] YYMMDDHHMM: {stamp_yymmddhhmm}")
    print(f"[안내] YYYYMMDDHHMM: {stamp_yyyymmddhhmm}")
    print(f"[안내] MMDDHHMM: {stamp_mmddhhmm}")
    print(f"[안내] 1MDDHHMM(전화): {stamp_1mddhhmm}")

    page.wait_for_timeout(500)

    fill_field(page, "od_user_nm", f"J주문{stamp_yymmddhhmm}")
    fill_field(page, "od_user_tel_no_enc", mobile)
    fill_field(page, "recvr_nm", f"J수취{stamp_yymmddhhmm}")
    fill_field(page, "recvr_mobile_no_enc", mobile)

    fill_recvr_address_via_popup(page, config)
    fill_field(page, "recvr_detail_addr", _build_recvr_detail_addr(stamp_mmddhhmm))

    fill_field(page, "mall_od_no", f"J{stamp_yyyymmddhhmm}", required=False)
    select_sach_cd(page, config.get("sach_cd_value", "SACH0020"))
    fill_field(page, "dlvr_msg", "WM수기등록", required=False)
    fill_field(page, "remark_ct", "WMWM수기등록", required=False)


def click_add_outbound_item_button(page) -> None:
    """'출고대상 품목' 버튼(#addBtn)을 클릭하고 팝업 표시까지만 확인합니다."""
    btn_candidates = [
        "#addBtn",
        'button:has-text("출고대상 품목")',
        "button.btn-info:has-text('출고대상 품목')",
    ]
    btn, btn_sel = first_visible_locator(page, btn_candidates)
    if not btn:
        raise ValueError("'출고대상 품목' 버튼(#addBtn)을 찾지 못했습니다.")

    print(f"[디버그] 출고대상 품목 버튼 셀렉터: {btn_sel}")
    _close_zip_address_modal(page)
    try:
        btn.click(timeout=10_000)
    except PlaywrightTimeoutError:
        btn.click(timeout=10_000, force=True)
    popup_candidates = [
        ".modal.show:has-text('출고대상 품목')",
        "#itemModal.modal.show",
        ".modal.show",
    ]
    popup, popup_sel = first_visible_locator(page, popup_candidates)
    if not popup:
        page.wait_for_timeout(1000)
        popup, popup_sel = first_visible_locator(page, popup_candidates)
    if popup:
        print(f"[안내] 출고대상 품목 팝업 표시 확인 (selector: {popup_sel})")
    else:
        print("[경고] 출고대상 품목 버튼은 클릭했지만 팝업 표시를 확인하지 못했습니다.")


def search_outbound_item_popup(page, keyword: str) -> None:
    """출고대상 품목 팝업에서 검색어를 입력하고 검색 버튼을 클릭합니다."""
    popup = page.locator(".modal.show:has-text('출고대상 품목'), #commModal.modal.show").first
    popup.wait_for(state="visible", timeout=10_000)

    search_input = page.locator("#commModal #target_srch_txt").first
    if search_input.count() == 0:
        search_input = popup.locator("#target_srch_txt").first
    if search_input.count() == 0:
        search_input = popup.locator('input[name="srch_txt"]').first
    if search_input.count() == 0:
        raise ValueError("출고대상 품목 팝업에서 검색어 입력칸(#target_srch_txt)을 찾지 못했습니다.")

    search_input.fill(keyword)
    print(f"[안내] 출고대상 품목 검색어 입력: {keyword}")

    search_btn = page.locator("#commModal #targetSearchBtn").first
    if search_btn.count() == 0:
        search_btn = popup.locator("#targetSearchBtn").first
    if search_btn.count() == 0:
        search_btn = popup.locator('button:has-text("검색")').first
    if search_btn.count() == 0:
        raise ValueError("출고대상 품목 팝업에서 검색 버튼(#targetSearchBtn)을 찾지 못했습니다.")

    search_btn.click(timeout=10_000)
    page.wait_for_timeout(1000)
    print("[안내] 출고대상 품목 팝업 검색 버튼 클릭 완료")


def run() -> None:
    """로그인 → 출고 수기등록 폼 입력 → 출고대상 품목 팝업 검색까지만 수행."""
    print_site_url_banner()
    creds = load_env_credentials()
    now = datetime.now()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_out_expect_list(page, CONFIG)
            click_out_expect_manual_register(page)
            fill_wm_manual_register_form(page, CONFIG, now)
            click_add_outbound_item_button(page)
            search_outbound_item_popup(
                page, CONFIG.get("target_product_search_keyword", "크래커")
            )
            print(
                "[안내] 출고대상 품목 팝업에서 검색까지만 완료했습니다. 이후 자동 처리는 하지 않습니다."
            )
            try:
                input("팝업창을 확인한 뒤 종료하려면 Enter를 누르세요...")
            except EOFError:
                print("[안내] 표준 입력이 없어 10분 동안 팝업창을 유지합니다.")
                page.wait_for_timeout(600_000)
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
