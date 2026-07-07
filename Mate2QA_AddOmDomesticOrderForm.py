# QA site 샘플화주사
from datetime import datetime
from pathlib import Path
from typing import Dict, Union

from playwright.sync_api import Frame, Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    _is_ably_login_url,
    click_opens_popup_or_same_tab,
    create_context,
    ensure_login_only,
    first_visible_locator,
    load_env_credentials,
    popup_page_zoom,
)
from Mate2QA_shipper_select import (
    PAGE_READY_OM_ORDER_LIST,
    read_current_shipper_label,
    select_shipper_on_page,
)
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)


# =========================
# 사용자 설정 영역 (URL은 Mate2QA_site_config.py _DEFAULT_LOGIN_URL)
# =========================
CONFIG = {
    **_SITE_CONFIG,
    # 화주 (search_filter_domestic.json shipper_label 우선, 없으면 아래 값·사이트 기본)
    "shipper_label": "",
    "shipper_label_ably_default": "아이니",
    "shipper_label_default": "",
    # 국내 수기 화면의 판매채널 option value (없으면 목록 첫 번째)
    "sach_cd_value": "SACH0020",
    # 상품코드 (비우면 Ably/기본 사이트별 기본값 사용)
    "sample_product_cd": "",
    # 배송지 우편번호 팝업 검색어
    "address_search_keyword": "지플러스타워",
    "headless": False,
    "slow_mo": 150,
    "page_zoom": 1.0,
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


def resolve_sample_product_cd(config: Dict) -> str:
    """상품코드: CONFIG 지정값 → 사이트 기본 순."""
    configured = (config.get("sample_product_cd") or "").strip()
    if configured:
        return configured
    login_url = (config.get("login_url") or "").strip()
    if _is_ably_login_url(login_url):
        return "P000000000000055"
    return "P000000000005754"


def ensure_shipper_selected_on_page(page, *, step: str = "") -> str:
    """주문목록 등에서 화주가 선택됐는지 확인합니다. 미선택이면 판매채널 단계 전에 안내합니다."""
    label = (read_current_shipper_label(page) or "").strip()
    if label:
        return label
    where = f" ({step})" if step else ""
    raise ValueError(
        f"화주가 선택되지 않았습니다{where}.\n"
        "  · 메뉴 0번(세션 화주 변경)으로 화주를 먼저 선택해 주세요.\n"
        "  · 또는 주문목록 상단 화주 드롭다운에서 직접 선택해 주세요.\n"
        "화주가 없으면 판매채널(sach_cd) 목록이 비어 있어 주문서 등록을 진행할 수 없습니다."
    )


def _is_domestic_order_register_page(page, register_url: str) -> bool:
    """현재 탭이 국내 수기등록 화면인지 확인합니다."""
    current = (page.url or "").lower()
    if "orderrgst.do" in current:
        return True
    target = (register_url or "").lower()
    return bool(target and target in current)


def open_domestic_order_register_page(page, config: Dict) -> Page:
    """국내 주문목록에서 화주를 확인한 뒤 수기등록 화면으로 이동합니다."""
    register_url = (config.get("order_register_url") or "").strip()
    if not register_url:
        raise ValueError("order_register_url이 설정되지 않았습니다.")

    on_register_page = _is_domestic_order_register_page(page, register_url)
    if not on_register_page:
        page.goto(config["order_list_url"], wait_until="domcontentloaded")
        _, _ = first_visible_locator(page, PAGE_READY_OM_ORDER_LIST)
        select_shipper_on_page(
            page, config, page_ready_selectors=PAGE_READY_OM_ORDER_LIST
        )
        ensure_shipper_selected_on_page(page, step="주문목록")
        page.goto(register_url, wait_until="domcontentloaded")

    select_loc = _resolve_sach_cd_locator(page)
    if select_loc:
        try:
            select_loc.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(300)
    return page


def _resolve_sach_cd_locator(page):
    """판매채널 select 요소를 찾습니다 (#sach_cd 우선)."""
    for sel in ("#sach_cd", 'select[name="sach_cd"]'):
        loc = page.locator(sel).first
        if loc.count() > 0:
            return loc
    return None


def _wait_sach_cd_options_ready(page, select_loc, *, timeout_ms: int = 15_000) -> None:
    """판매채널 select가 보이고 선택 가능한 option이 채워질 때까지 대기합니다."""
    handle = select_loc.element_handle(timeout=timeout_ms)
    if handle is None:
        raise ValueError("판매채널(sach_cd) 요소를 찾지 못했습니다.")
    page.wait_for_function(
        """(el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const placeholders = new Set(['선택하세요', '선택']);
            return Array.from(el.options || []).some((o) => {
                const val = (o.value || '').trim();
                const text = (o.textContent || '').trim();
                return val && !o.disabled && !placeholders.has(text);
            });
        }""",
        arg=handle,
        timeout=timeout_ms,
    )


_SACH_CD_PLACEHOLDER_LABELS = frozenset({"선택하세요", "선택"})


def _is_selectable_sach_option(value: str, label: str) -> bool:
    """placeholder·빈 value 옵션은 제외합니다."""
    val = (value or "").strip()
    text = (label or "").strip()
    if not val:
        return False
    return text not in _SACH_CD_PLACEHOLDER_LABELS


def _list_selectable_sach_options(select_loc) -> list[dict]:
    """선택 가능한 판매채널 option 목록을 반환합니다."""
    raw = select_loc.evaluate(
        """(el) => Array.from(el.options || []).map((o, index) => ({
            index,
            value: (o.value || '').trim(),
            label: (o.textContent || '').trim(),
            disabled: !!o.disabled,
        }))"""
    )
    return [
        opt
        for opt in raw
        if not opt.get("disabled")
        and _is_selectable_sach_option(opt.get("value", ""), opt.get("label", ""))
    ]


def _read_selected_sach_cd(select_loc) -> tuple[str, str]:
    """현재 선택된 판매채널 (value, label)"""
    data = select_loc.evaluate(
        """(el) => {
            const opt = el.options[el.selectedIndex];
            return {
                value: (el.value || '').trim(),
                label: opt ? (opt.textContent || '').trim() : '',
            };
        }"""
    )
    return (data.get("value") or "").strip(), (data.get("label") or "").strip()


def _select_sach_cd_with_prefs(
    select_loc,
    *,
    value: str = "",
    label: str = "",
    fallback_label: str = "J채널",
) -> str:
    """JS로 판매채널을 즉시 선택합니다. 성공 시 선택된 value, 실패 시 빈 문자열."""
    return (select_loc.evaluate(
        """(el, prefs) => {
            const placeholders = new Set(['선택하세요', '선택']);
            const isSelectable = (o) => {
                const val = (o.value || '').trim();
                const text = (o.textContent || '').trim();
                return !o.disabled && val && !placeholders.has(text);
            };
            const apply = (opt) => {
                if (!isSelectable(opt)) return '';
                const val = opt.value.trim();
                el.value = val;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                if (window.jQuery) window.jQuery(el).val(val).trigger('change');
                return val;
            };
            const opts = Array.from(el.options || []);
            const targetValue = (prefs.value || '').trim();
            const targetLabel = (prefs.label || '').trim();
            const fbLabel = (prefs.fallbackLabel || '').trim();
            if (targetValue) {
                const byValue = opts.find((o) => o.value === targetValue);
                if (byValue) {
                    const picked = apply(byValue);
                    if (picked) return picked;
                }
            }
            if (targetLabel) {
                const byLabel = opts.find(
                    (o) => (o.textContent || '').trim() === targetLabel
                );
                if (byLabel) {
                    const picked = apply(byLabel);
                    if (picked) return picked;
                }
            }
            if (fbLabel) {
                const byFb = opts.find(
                    (o) => (o.textContent || '').trim() === fbLabel
                );
                if (byFb) {
                    const picked = apply(byFb);
                    if (picked) return picked;
                }
            }
            const firstOpt = opts.find(isSelectable);
            return firstOpt ? apply(firstOpt) : '';
        }""",
        {
            "value": (value or "").strip(),
            "label": (label or "").strip(),
            "fallbackLabel": (fallback_label or "").strip(),
        },
    ) or "").strip()


def _apply_sach_cd_selection(select_loc, *, value: str = "", label: str = "", index: int | None = None) -> bool:
    """Playwright select_option 폴백 (select2 등 JS 선택이 실패할 때만 사용)."""
    try:
        if index is not None:
            select_loc.select_option(index=index, timeout=2_000)
        elif value:
            select_loc.select_option(value=value, timeout=2_000)
        elif label:
            select_loc.select_option(label=label, timeout=2_000)
        else:
            return False
    except Exception:
        return False

    picked_value, picked_label = _read_selected_sach_cd(select_loc)
    return _is_selectable_sach_option(picked_value, picked_label)


def select_domestic_sach_cd(page, sach_cd_value: str):
    """국내 수기 화면에서 판매채널(sach_cd)을 value 기준으로 선택합니다."""
    page.wait_for_load_state("domcontentloaded")
    select_loc = _resolve_sach_cd_locator(page)
    if select_loc is None:
        raise ValueError(
            "판매채널(sach_cd) 요소(#sach_cd)를 찾지 못했습니다. "
            "수기등록 페이지(orderRgst.do)인지 확인해 주세요."
        )

    try:
        _wait_sach_cd_options_ready(page, select_loc)
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            "판매채널(sach_cd) 목록이 비어 있거나 로드되지 않았습니다.\n"
            "  · 주문목록에서 화주가 선택됐는지 확인해 주세요 (메뉴 0번).\n"
            "  · 화주를 바꾼 뒤 11번을 다시 실행해 주세요."
        ) from exc

    selectable = _list_selectable_sach_options(select_loc)
    if not selectable:
        raise ValueError("sach_cd에서 선택 가능한 판매채널이 없습니다.")

    # 1) CONFIG/env value → 2) J채널 → 3) 첫 항목 (JS 즉시 선택)
    picked = _select_sach_cd_with_prefs(
        select_loc,
        value=sach_cd_value,
        fallback_label="J채널",
    )
    if picked:
        return

    # select2 등 JS 폴백이 실패한 경우에만 Playwright select_option 시도
    if _apply_sach_cd_selection(select_loc, value=sach_cd_value):
        return
    if _apply_sach_cd_selection(select_loc, label="J채널"):
        return
    first = selectable[0]
    if _apply_sach_cd_selection(select_loc, index=int(first["index"])):
        return

    picked_value, picked_label = _read_selected_sach_cd(select_loc)
    raise ValueError(
        f"sach_cd 선택에 실패했습니다. 현재값='{picked_label}'({picked_value!r})\n"
        f"  · 후보: {selectable[:8]}"
    )


def _get_product_search_scope(page):
    """상품 검색 팝업(모달) 범위를 반환합니다. 없으면 페이지 전체를 사용합니다."""
    modal = page.locator(".modal.show").filter(
        has=page.locator('input[name="searchTxt"], input#searchTxt')
    ).first
    if modal.count() > 0 and modal.is_visible():
        return modal
    return page.locator("body")


def _open_product_search_popup(page) -> None:
    """주문서 등록 화면에서 상품 검색 팝업을 엽니다."""
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

    search_btn.click()
    page.wait_for_timeout(1200)
    scope = _get_product_search_scope(page)
    scope.locator('input[name="searchTxt"], input#searchTxt').first.wait_for(
        state="visible", timeout=10_000
    )


def _run_product_search_in_popup(page, product_code: str) -> None:
    """상품 검색 팝업에서 검색조건·검색어를 넣고 조회합니다."""
    scope = _get_product_search_scope(page)

    col_loc = scope.locator('select[name="searchColumn"], select#searchColumn').first
    if col_loc.count() > 0 and col_loc.is_visible():
        try:
            col_loc.select_option(value="prod_cd")
        except Exception:
            col_loc.select_option(label="prod_cd")
    else:
        dropdown, _ = first_visible_locator(
            page,
            ["#searchColumn", '[name="searchColumn"]'],
        )
        if not dropdown:
            raise ValueError("searchColumn 요소를 찾지 못했습니다.")
        dropdown.click()
        page.locator('text="prod_cd"').first.click()

    txt_input, txt_sel = first_visible_locator(
        page,
        ['input[name="searchTxt"]', "#searchTxt"],
    )
    if not txt_input:
        raise ValueError("searchTxt 입력 요소를 찾지 못했습니다.")
    txt_input.fill(product_code or "")

    prod_search_btn, prod_btn_sel = first_visible_locator(
        page,
        ["#prodSearchBtn", '[name="prodSearchBtn"]', 'button:has-text("검색")'],
    )
    if not prod_search_btn:
        raise ValueError("prodSearchBtn 버튼을 찾지 못했습니다.")
    prod_search_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)


def _grid_contains_product_code(scope, product_code: str) -> bool:
    """검색 그리드에 지정 상품코드가 있는지 확인합니다."""
    code = (product_code or "").strip()
    if not code:
        return False
    try:
        return bool(
            scope.evaluate(
                """(root, target) => {
                    const rows = root.querySelectorAll('.tabulator-row');
                    for (const row of rows) {
                        const cell = row.querySelector('[tabulator-field="prod_cd"]');
                        const text = ((cell && cell.innerText) || '').trim();
                        if (text === target) return true;
                    }
                    return false;
                }""",
                code,
            )
        )
    except Exception:
        return False


def _click_first_product_select_button(scope) -> None:
    """검색 결과 그리드 첫 번째 행의 '선택' 버튼을 클릭합니다."""
    row = scope.locator(".tabulator-row").first
    row.wait_for(state="visible", timeout=10_000)

    select_btn_candidates = [
        row.locator("button.btn-info").first,
        row.locator('button:has-text("선택")').first,
        row.locator('a:has-text("선택")').first,
        scope.locator(".tabulator-row .btn-info").first,
        scope.locator('button:has-text("선택")').first,
    ]
    for btn in select_btn_candidates:
        if btn.count() > 0 and btn.is_visible():
            btn.click()
            page_wait = scope.page
            page_wait.wait_for_timeout(1000)
            return

    raise ValueError("상품 검색 결과에서 '선택' 버튼을 찾지 못했습니다.")


def search_and_select_product_in_popup(page, product_code: str) -> None:
    """
    상품 검색 팝업에서 상품코드로 조회 후 선택합니다.
    해당 코드가 없으면 전체 조회로 바꿔 첫 번째 상품을 선택합니다.
    """
    _open_product_search_popup(page)
    _run_product_search_in_popup(page, product_code)

    scope = _get_product_search_scope(page)
    if _grid_contains_product_code(scope, product_code):
        _click_first_product_select_button(scope)
        return

    _run_product_search_in_popup(page, "")
    scope = _get_product_search_scope(page)
    _click_first_product_select_button(scope)


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
        return
    try:
        blocked = field.evaluate("(el) => !!(el.readOnly || el.disabled)")
    except Exception:
        blocked = False
    if blocked:
        if required:
            raise ValueError(f"{field_name} 입력 요소가 읽기 전용·비활성입니다.")
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
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            f"{field_name} 자동 계산 값이 비어 있습니다. "
            "단가·수량 입력 후 결제금액이 채워지는지 화면에서 확인해 주세요."
        ) from exc


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
                continue
            field.fill(value)
            safe_value = value.encode("cp949", errors="replace").decode("cp949")
            return

    if required:
        joined = ", ".join(field_names)
        raise ValueError(f"입력 요소를 찾지 못했습니다. 후보: {joined}")


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

    search_btn = root.locator(".btn_search").first
    if search_btn.count() == 0:
        search_btn = root.locator("button.btn_search").first
    if search_btn.count() == 0:
        raise ValueError("팝업에서 btn_search 버튼을 찾지 못했습니다.")
    search_btn.click()


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
                    .map((el) => ({
                        key: `${el.name || ''} ${el.id || ''}`.trim(),
                        value: String(el.value || '').trim(),
                    }))
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
        raise ValueError(
            "주소 검색 결과를 클릭했지만 우편번호·기본주소 반영을 확인하지 못했습니다. "
            "화면의 배송지 우편번호·기본주소 필드 name/id를 확인해 주세요."
        ) from exc

    first = values[0]
    safe_key = str(first.get("key", "")).encode("cp949", errors="replace").decode("cp949")
    safe_value = str(first.get("value", "")).encode("cp949", errors="replace").decode("cp949")


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

    with popup_page_zoom(page, config):
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


        pass


def click_save_button(page, *, confirm_swal: bool = True, quiet: bool = False):
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
            print("[주의] 자동으로 '저장'하지 않습니다.")
        except PlaywrightTimeoutError:
            if not quiet:
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
        rv_mobile,
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


def run_task(page, context, config, *, keep_browser: bool = False):
    """국내 수기 주문 등록 자동화를 수행합니다."""
    product_cd = resolve_sample_product_cd(config)
    now = datetime.now()
    stamp_yymmddhhmm = now.strftime("%y%m%d%H%M")
    stamp_yymmddhh = now.strftime("%y%m%d%H")
    stamp_mmddhhmm = now.strftime("%m%d%H%M")

    page = open_domestic_order_register_page(page, config)
    select_domestic_sach_cd(page, config["sach_cd_value"])
    search_and_select_product_in_popup(page, product_cd)
    fill_domestic_order_detail_fields(
        page,
        config,
        stamp_mmddhhmm,
        stamp_yymmddhhmm,
        stamp_yymmddhh,
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
    """로그인 후 국내 수기 주문 등록 자동화를 수행합니다 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
