# QA WMS 전체 플로우 — 출고예정 → WAVE → 할당 → 출고작업 → 전체박스 추천 실행
#
# 1) 출고예정: 날짜·채널·주문 선택 후 Enter → WAVE
# 2) 웨이브 목록: 저장 조건 검색 → 주소정제(필요 시)
# 3) 출고차수할당 → 출고차수명 JSON 저장
# 4) 출고작업: 출고차수명 검색 → 출고지시 → 박스추천 → 전체박스 추천 실행 후 종료
#
# 사이트 URL: Mate2QA_site_config.py (상대 path)

from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_shipper_select import PAGE_READY_WM_OUT_EXPECT, select_shipper_on_page
from Mate2QA_site_config import (
    CONFIG as _SITE_CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)
from Mate2QA_wm_wave_search import (
    OutAllocRgstSearchEmptyError,
    print_out_alloc_rgst_no_results,
    apply_wm_wave_search,
    capture_wave_selected_row_context,
    capture_wm_wave_filter_from_page,
    click_address_refine,
    click_out_alloc_assign,
    click_out_alloc_rgst_button,
    click_box_recommend_dropdown,
    click_out_wk_ord_instruction_tab,
    click_total_box_recommend_btn,
    fill_out_alloc_rgst_form,
    is_dlvr_div_empty,
    load_out_tseq_nm,
    run_wave_process_on_expect_list,
    search_out_wk_ord_by_tseq_nm,
    select_all_alloc_rgst_targets,
    select_out_wk_ord_row_by_tseq_nm,
)

CONFIG = {
    **_SITE_CONFIG,
    "shipper_label": "",
    "shipper_label_ably_default": "아이니",
    "shipper_label_default": "",
}

STATE_FILE = STATE_FILE_DOMESTIC


def goto_out_expect_list(page, config: Dict):
    """WMS 출고예정 목록으로 이동한 뒤 화주·검색 폼이 준비될 때까지 대기합니다."""
    page.goto(config["out_expect_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    select_shipper_on_page(
        page, config, page_ready_selectors=PAGE_READY_WM_OUT_EXPECT
    )
    page.locator("#searchForm").first.wait_for(state="visible", timeout=15_000)


def goto_out_wave_list(page, config: Dict):
    """WMS 웨이브 목록 화면으로 이동합니다."""
    page.goto(config["out_wave_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


def goto_out_wk_ord_list(page, config: Dict):
    """WMS 출고작업 목록 화면으로 이동합니다."""
    page.goto(config["out_wk_ord_list_url"], wait_until="domcontentloaded")
    page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(500)


def wait_for_out_wk_ord_after_alloc(page, config: Dict) -> None:
    """출고차수 할당 alert OK 후 출고작업 목록 화면 이동을 기다립니다."""
    try:
        page.wait_for_url("**/wm/out/wk/ord/outWkOrdList.do", timeout=60_000)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
        page.wait_for_timeout(500)
    except PlaywrightTimeoutError:
        goto_out_wk_ord_list(page, config)


def select_depot_cd_if_needed(page) -> None:
    """물류센터(depot_cd)가 비어 있을 때만 첫 번째 항목을 선택합니다."""
    sel = page.locator('select[name="depot_cd"], select#depot_cd').first
    if sel.count() == 0:
        return

    sel.wait_for(state="visible", timeout=10_000)

    if sel.evaluate("(el) => !!el.disabled"):
        return

    current_value = sel.evaluate("(el) => (el.value || '').trim()")
    if current_value:
        return

    picked = sel.evaluate(
        """(el) => {
            const opts = Array.from(el.options || []);
            const first = opts.find(
                (o) => (o.value || '').trim() !== '' && !o.disabled
            );
            if (!first) return { value: '', text: '' };
            el.value = first.value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return {
                value: (first.value || '').trim(),
                text: (first.textContent || '').trim(),
            };
        }"""
    )
    if not picked.get("value"):
        return



def run_task(page, context, config, *, keep_browser: bool = False):
    """출고예정~할당 → 출고작업 전체박스 추천 실행까지."""
    from Mate2QA_browser_session import wait_enter_after_task

    goto_out_expect_list(page, config)

    try:
        input("이동할 주문서를 선택 후 Enter...")
    except EOFError:
        pass

    filter_data = capture_wm_wave_filter_from_page(page)
    if not filter_data.get("selected_od_snos"):
        raise ValueError(
            "선택된 주문(od_sno)이 없습니다. "
            "출고예정 목록에서 주문을 체크한 뒤 Enter를 눌러 주세요."
        )

    run_wave_process_on_expect_list(page, filter_data)

    if "outWaveList.do" not in page.url:
        goto_out_wave_list(page, config)

    apply_wm_wave_search(page, filter_data, select_orders=True)
    filter_data = capture_wave_selected_row_context(page, filter_data)

    if is_dlvr_div_empty(filter_data):
        pass
    else:
        click_address_refine(page)

    click_out_alloc_assign(page, config["out_alloc_rgst_url"])
    select_depot_cd_if_needed(page)
    fill_out_alloc_rgst_form(page, filter_data)
    try:
        select_all_alloc_rgst_targets(page)
    except OutAllocRgstSearchEmptyError:
        print_out_alloc_rgst_no_results()
        return
    except PlaywrightTimeoutError as exc:
        if "outallocrgst.do" not in (page.url or "").lower():
            raise
        print_out_alloc_rgst_no_results()
        return

    click_out_alloc_rgst_button(page)
    wait_for_out_wk_ord_after_alloc(page, config)

    out_tseq_nm = load_out_tseq_nm()
    if not out_tseq_nm:
        raise ValueError(
            "출고차수명(out_tseq_nm)이 JSON에 없습니다. "
            "출고차수할당 단계(fill_out_alloc_rgst_form)를 확인해 주세요."
        )

    search_out_wk_ord_by_tseq_nm(page, out_tseq_nm)
    select_out_wk_ord_row_by_tseq_nm(page, out_tseq_nm)
    try:
        click_out_wk_ord_instruction_tab(page)
        click_box_recommend_dropdown(page)
        click_total_box_recommend_btn(page)
    except PlaywrightTimeoutError as exc:
        if "grid-table-tab3" not in str(exc):
            raise
        print(
            "[경고] 출고지시 그리드(#grid-table-tab3) 로딩이 지연되어 "
            "박스추천 단계는 건너뜁니다. 화면에서 직접 확인해 주세요.",
            flush=True,
        )

    wait_enter_after_task(keep_browser=keep_browser)


def run():
    """로그인 → 출고등록~출고지시 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    try:
        run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)
    except OutAllocRgstSearchEmptyError:
        return
    except PlaywrightTimeoutError as exc:
        if "grid-table-tab3" in str(exc):
            return
        raise


if __name__ == "__main__":
    run()
