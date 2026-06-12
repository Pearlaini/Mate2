# QA WMS 전체 플로우 — 웨이브 → 할당 → 출고작업 → 출고확정
#
# 1) 웨이브 목록: 검색 조건·주문 선택 후 Enter
# 2) 주소정제(필요 시) → 출고차수할당
# 3) 출고작업: 저장된 출고차수명(#srch_txt) 검색 → 출고지시~출고확정
#
# 사이트 URL: Mate2QA_site_config.py (상대 path)

from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_order_step import (
    OUT_WK_ORD_PROCESSING_ERROR,
    OutWkOrdProcessingError,
    abort_popup_on_messages,
    print_out_wk_ord_processing_error,
)
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner, refresh_config_from_env
from Mate2QA_WmMoveFromBoxtoFinal import (
    click_alert_ok_before_picking_tab,
    click_confirm_product_picking_list,
    click_out_confirm_tab,
    click_packing_instruction_tab,
    click_packing_next_step_all,
    click_picking_instruction_tab,
    click_picking_next_step_to_packing,
    open_order_manage_tab,
    open_sach_stock_tab,
    run_box_recommend_and_move_next,
    search_order_by_mall_od_no,
    select_stock_search_column_product_code,
)
from Mate2QA_wm_wave_search import (
    apply_wm_wave_search,
    capture_wave_selected_row_context,
    click_address_refine,
    click_out_alloc_assign,
    click_out_alloc_rgst_button,
    click_out_wk_ord_instruction_tab,
    fill_out_alloc_rgst_form,
    is_dlvr_div_empty,
    load_out_tseq_nm,
    load_wm_wave_filter,
    search_out_wk_ord_by_tseq_nm,
    select_all_alloc_rgst_targets,
    select_out_wk_ord_row_by_tseq_nm,
)

STATE_FILE = STATE_FILE_DOMESTIC


def goto_out_wave_list(page, config: Dict) -> None:
    """WMS 웨이브 목록 화면으로 이동합니다."""
    page.goto(config["out_wave_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


def goto_out_wk_ord_list(page, config: Dict) -> None:
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



def run_out_wk_ord_to_final(page, context, config, filter_data: Dict) -> None:
    """출고작업 목록에서 저장된 출고차수명으로 검색 후 출고지시~출고확정까지 진행합니다."""
    out_tseq_nm = (filter_data.get("out_tseq_nm") or "").strip() or load_out_tseq_nm()
    if not out_tseq_nm:
        raise ValueError(
            "출고차수명(out_tseq_nm)이 없습니다. "
            "출고차수할당 단계(#out_tseq_nm)에서 저장된 값을 확인해 주세요."
        )
    search_out_wk_ord_by_tseq_nm(page, out_tseq_nm)
    select_out_wk_ord_row_by_tseq_nm(page, out_tseq_nm)
    click_out_wk_ord_instruction_tab(page)
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
        run_box_recommend_and_move_next(page)
        click_alert_ok_before_picking_tab(page)
        click_picking_instruction_tab(page)
        click_picking_next_step_to_packing(page)
        click_packing_instruction_tab(page)
        click_packing_next_step_all(page)
    click_out_confirm_tab(page)
    stock_page = open_sach_stock_tab(context, config)
    select_stock_search_column_product_code(stock_page)
    manage_page = open_order_manage_tab(context, config)
    search_order_by_mall_od_no(manage_page, "J")
    page.bring_to_front()
    page.wait_for_timeout(500)
    click_out_confirm_tab(page)
    click_confirm_product_picking_list(page)


def run_task(page, context, config, *, keep_browser: bool = False) -> None:
    """웨이브~할당 → 출고작업 출고확정까지."""
    from Mate2QA_browser_session import wait_enter_after_task

    goto_out_wave_list(page, config)

    try:
        input("준비되면 Enter...")
    except EOFError:
        pass

    filter_data = load_wm_wave_filter()
    if not filter_data:
        raise ValueError(
            "search_filter_wm_wave.json이 없습니다. "
            "웨이브 목록에서 검색·주문 선택 후 진행하거나 "
            "23번(출고등록~출고할당)을 먼저 실행해 주세요."
        )

    apply_wm_wave_search(page, filter_data, select_orders=True)
    filter_data = capture_wave_selected_row_context(page, filter_data)

    if is_dlvr_div_empty(filter_data):
        pass
    else:
        click_address_refine(page)

    click_out_alloc_assign(page, config["out_alloc_rgst_url"])
    select_depot_cd_if_needed(page)
    fill_out_alloc_rgst_form(page, filter_data)
    select_all_alloc_rgst_targets(page)
    click_out_alloc_rgst_button(page)
    wait_for_out_wk_ord_after_alloc(page, config)

    run_out_wk_ord_to_final(page, context, config, filter_data)

    wait_enter_after_task(keep_browser=keep_browser)


def run() -> None:
    """로그인 → Wave~출고확정 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    try:
        run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)
    except OutWkOrdProcessingError as exc:
        print_out_wk_ord_processing_error(exc)
    except PlaywrightTimeoutError as exc:
        if "grid-table-tab3" in str(exc):
            return
        raise


if __name__ == "__main__":
    run()
