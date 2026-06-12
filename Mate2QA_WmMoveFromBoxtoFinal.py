# QA WMS 출고작업 — 박스 → 피킹지시 이동
#
# 1) 로그인 상태 확인
# 2) 출고작업 목록 이동
# 3) 검색구분=출고차수 + 출고차수 번호 검색·행 선택
# 4) 출고지시 탭에서 박스추천 실행
# 5) 다음 단계 > 전체 다음단계 실행 후 alert OK 자동 클릭
# 6) 피킹지시 탭 클릭
# 7) 다음 단계 → 전체 다음단계 → alert OK 2회 → 포장지시 탭 클릭

from contextlib import contextmanager
from typing import Dict, Iterator

from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_order_step import (
    OUT_WK_ORD_PROCESSING_ERROR,
    OutWkOrdProcessingError,
    abort_popup_on_messages,
    click_popup_ok_if_visible,
    print_out_wk_ord_processing_error,
    wait_out_wk_ord_popups_after_next_step,
)
from Mate2QA_order_search import click_search_button, wait_order_search_form
from Mate2QA_site_config import (
    CONFIG,
    STATE_FILE_DOMESTIC,
    join_origin_path,
    print_site_url_banner,
    refresh_config_from_env,
)
from Mate2QA_wm_wave_search import (
    ALERT_OK_POLICY,
    click_all_picking_instrt,
    click_box_recommend_dropdown,
    click_out_wk_ord_instruction_tab,
    click_out_wk_ord_next_step_dropdown,
    click_out_wk_ord_search_button,
    click_total_box_recommend,
    wait_out_wk_ord_main_grid,
    wait_out_wk_ord_tab4_rows,
)

STATE_FILE = STATE_FILE_DOMESTIC
ORDER_MANAGE_LIST_PATH = "/om/order/manage/manageList.do"


def goto_out_wk_ord_list(page: Page, config: Dict) -> None:
    """WMS 출고작업 목록 화면으로 이동합니다."""
    url = config["out_wk_ord_list_url"]
    page.goto(url, wait_until="domcontentloaded")
    page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(500)


def select_out_tseq_search_column(page: Page) -> None:
    """출고작업 검색구분을 「출고차수」로 선택합니다."""
    page.locator("#srch_gubun").wait_for(state="visible", timeout=10_000)
    page.select_option("#srch_gubun", value="out_tseq")
    page.wait_for_timeout(300)


def input_out_tseq_sno() -> str:
    """사용자에게 출고차수 번호를 입력받습니다."""
    try:
        out_tseq_sno = input("출고차수 번호를 입력해 주세요: ").strip()
    except EOFError as exc:
        raise ValueError("출고차수 번호를 입력받지 못했습니다.") from exc

    if not out_tseq_sno:
        raise ValueError("출고차수 번호가 비어 있습니다. 출고차수 번호를 입력해 주세요.")
    return out_tseq_sno


def fill_out_wk_ord_tseq_sno(page: Page, out_tseq_sno: str) -> None:
    """출고작업 화면: 검색구분=출고차수 + #srch_txt에 번호 입력."""
    select_out_tseq_search_column(page)
    txt = page.locator("#srch_txt").first
    txt.wait_for(state="visible", timeout=10_000)
    txt.evaluate(
        """(el, v) => {
            el.value = v || '';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        out_tseq_sno,
    )


def search_and_select_out_tseq(page: Page, out_tseq_sno: str) -> None:
    """출고차수 번호로 검색한 뒤 해당 행을 선택합니다."""
    fill_out_wk_ord_tseq_sno(page, out_tseq_sno)
    click_out_wk_ord_search_button(page)
    wait_out_wk_ord_main_grid(page)
    click_out_wk_ord_row_by_sno(page, out_tseq_sno)


def click_out_wk_ord_row_by_sno(page: Page, out_tseq_sno: str) -> None:
    """출고차수(out_alloc_tseq_sno)가 일치하는 행을 클릭합니다."""
    target = (out_tseq_sno or "").strip()
    if not target:
        raise ValueError("선택할 출고차수(out_alloc_tseq_sno)가 비어 있습니다.")

    result = page.evaluate(
        """(sno) => {
            const grid = document.querySelector('#grid-table');
            if (!grid) return { found: false, tseq_sno: '' };
            for (const row of grid.querySelectorAll('.tabulator-row')) {
                const field = row.querySelector('[tabulator-field="out_alloc_tseq_sno"]');
                const text = field ? (field.innerText || '').trim() : '';
                if (text !== sno) continue;

                row.scrollIntoView({ block: 'center', inline: 'nearest' });
                row.click();

                const hidden = document.querySelector('#selected_out_alloc_tseq_sno');
                let tseq_sno = hidden ? (hidden.value || '').trim() : '';
                if (!tseq_sno) tseq_sno = text;
                return { found: true, tseq_sno };
            }
            return { found: false, tseq_sno: '' };
        }""",
        target,
    )
    page.wait_for_timeout(800)

    if not result.get("found"):
        raise ValueError(f"출고작업 목록에서 출고차수 '{target}' 행을 찾지 못했습니다.")

    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = str(result.get("tseq_sno") or target).strip()


@contextmanager
def auto_ok_for_all_next_step() -> Iterator[None]:
    """이번 스크립트에서만 전체 다음단계 alert OK를 자동 클릭하도록 설정합니다."""
    old_value = ALERT_OK_POLICY.get("all_picking_instrt", False)
    ALERT_OK_POLICY["all_picking_instrt"] = True
    try:
        yield
    finally:
        ALERT_OK_POLICY["all_picking_instrt"] = old_value


def run_box_recommend_and_move_next(page: Page) -> None:
    """출고지시 탭에서 박스추천 후 전체 다음단계까지 이동합니다."""
    click_box_recommend_dropdown(page)
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
        click_total_box_recommend(page)
    page.wait_for_timeout(2000)
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
        click_out_wk_ord_next_step_dropdown(page)
        with auto_ok_for_all_next_step():
            click_all_picking_instrt(page)
    page.wait_for_timeout(1000)


def click_alert_ok_before_picking_tab(page: Page) -> None:
    """피킹지시 탭 클릭 전에 남아 있는 alert OK를 모두 클릭합니다."""
    clicked_any = False
    for attempt in range(1, 4):
        if not click_popup_ok_if_visible(page, timeout_ms=5_000):
            break
        clicked_any = True
        page.wait_for_timeout(500)
    if not clicked_any:


        pass


def click_picking_instruction_tab(page: Page) -> None:
    """출고상세 그리드 「피킹지시」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "목록에서 출고차수명 행을 먼저 클릭해 주세요."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-4"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab4 === 'function') {
                grid_table_tab4(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)
    row_count = wait_out_wk_ord_tab4_rows(page, timeout_ms=30_000)
    if row_count == 0:
        raise ValueError(
            "피킹지시 탭에 데이터가 없습니다. "
            "출고지시에서 「전체 다음단계」 이동이 완료되지 않았을 수 있습니다. "
            "박스추천·alert 메시지를 화면에서 확인해 주세요."
        )


def click_product_picking_list(page: Page) -> None:
    """피킹 리스트 드롭다운에서 「상품별」을 클릭한 뒤 alert OK를 클릭합니다."""
    picking_btn = page.locator("#picking_btn_06").first
    picking_btn.wait_for(state="visible", timeout=10_000)
    picking_btn.click()
    page.wait_for_timeout(400)

    product_btn = page.locator("#sel_picking_list_by_prod_pick").first
    product_btn.wait_for(state="visible", timeout=10_000)
    product_btn.click()
    page.wait_for_timeout(800)

    if not click_popup_ok_if_visible(page, timeout_ms=15_000):
        raise ValueError("피킹 리스트 상품별 alert에서 OK/확인 버튼을 찾지 못했습니다.")


def select_all_out_confirm_rows(page: Page) -> None:
    """출고확정 탭의 전체 checkbox를 클릭합니다."""
    page.locator("#tab_borders_icons-8").wait_for(state="visible", timeout=15_000)
    result = page.evaluate(
        """() => {
            const tab = document.querySelector('#tab_borders_icons-8');
            if (!tab) return { clicked: false, checked: 0, total: 0, reason: 'tab_not_found' };

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const header = Array.from(
                tab.querySelectorAll(
                    '.tabulator-header input[type="checkbox"], '
                    + 'div.tabulator-col-title input[type="checkbox"]'
                )
            ).find(isVisible);
            if (header && !header.checked) {
                header.click();
            }

            const rows = Array.from(
                tab.querySelectorAll(
                    '.tabulator-row input[type="checkbox"][aria-label="Select Row"], '
                    + '.tabulator-row input[type="checkbox"]'
                )
            ).filter(isVisible);
            for (const cb of rows) {
                if (!cb.checked) cb.click();
            }

            const checked = rows.filter((cb) => cb.checked).length;
            return {
                clicked: !!header || checked > 0,
                checked,
                total: rows.length,
                reason: ''
            };
        }"""
    )
    if not result.get("clicked"):
        raise ValueError(
            "출고확정 탭에서 전체 checkbox를 찾지 못했습니다. "
            f"reason={result.get('reason')}"
        )


def click_confirm_product_picking_list(page: Page) -> None:
    """출고확정 탭에서 전체 선택 후 피킹 리스트 드롭다운의 「상품별」을 클릭합니다."""
    select_all_out_confirm_rows(page)

    picking_btn = page.locator("#picking_btn_08").first
    picking_btn.wait_for(state="visible", timeout=10_000)
    picking_btn.click()
    page.wait_for_timeout(400)

    product_btn = page.locator("#sel_picking_list_by_prod_confrm").first
    product_btn.wait_for(state="visible", timeout=10_000)
    product_btn.click()
    page.wait_for_timeout(800)

    if not click_popup_ok_if_visible(page, timeout_ms=15_000):
        raise ValueError("출고확정 피킹 리스트 상품별 alert에서 OK/확인 버튼을 찾지 못했습니다.")


def click_picking_next_step_to_packing(page: Page) -> None:
    """피킹지시에서 다음 단계 > 전체 다음단계를 클릭하고 alert OK를 2회 처리합니다."""
    page.wait_for_timeout(3000)
    page.bring_to_front()
    page.wait_for_timeout(500)

    clicked = page.evaluate(
        """() => {
            const menu = document.querySelector('#all_packing_instrt');
            if (!menu) return { clicked: false, reason: 'menu_not_found' };

            const containers = [];
            let current = menu.parentElement;
            while (current) {
                containers.push(current);
                current = current.parentElement;
            }

            const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            for (const container of containers) {
                const toggle = Array.from(
                    container.querySelectorAll('button.dropdown-toggle')
                ).find((btn) =>
                    isVisible(btn) && (btn.innerText || '').includes('다음 단계')
                );
                if (toggle) {
                    toggle.click();
                    return { clicked: true, reason: '' };
                }
            }

            return { clicked: false, reason: 'visible_toggle_not_found' };
        }"""
    )
    if not clicked.get("clicked"):
        raise ValueError(
            "피킹지시 화면에서 #all_packing_instrt와 연결된 "
            f"「다음 단계」 버튼을 찾지 못했습니다. reason={clicked.get('reason')}"
        )
    page.wait_for_timeout(400)

    all_next_btn = page.locator("#all_packing_instrt").first
    all_next_btn.wait_for(state="visible", timeout=10_000)
    all_next_btn.click()
    page.wait_for_timeout(800)

    for attempt in range(1, 3):
        timeout_ms = 15_000 if attempt == 1 else 5_000
        if not click_popup_ok_if_visible(page, timeout_ms=timeout_ms):
            if attempt == 1:
                raise ValueError(
                    "피킹지시 전체 다음단계 alert OK 1회차를 찾지 못했습니다."
                )
            break
        page.wait_for_timeout(500)


def click_packing_instruction_tab(page: Page) -> None:
    """「포장지시」 탭을 클릭합니다."""
    packing_tab = page.locator("#packing_tab").first
    packing_tab.wait_for(state="visible", timeout=10_000)
    packing_tab.click()
    page.wait_for_timeout(1000)


def click_packing_next_step_all(page: Page) -> None:
    """포장지시에서 다음 단계 > 전체 다음단계를 클릭하고 alert OK를 2회 처리합니다."""
    page.wait_for_timeout(1000)
    page.bring_to_front()
    page.wait_for_timeout(500)

    result = page.evaluate(
        """() => {
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const toggle = Array.from(
                document.querySelectorAll('button.dropdown-toggle')
            ).find((btn) =>
                isVisible(btn) && (btn.innerText || '').includes('다음 단계')
            );
            if (!toggle) {
                return { clickedToggle: false, clickedMenu: false, reason: 'toggle_not_found' };
            }

            toggle.click();

            const menus = Array.from(
                document.querySelectorAll(
                    'button.__state_change[data-exetype="next"][data-seltype="all"], '
                    + '.dropdown-item.__state_change[data-exetype="next"][data-seltype="all"]'
                )
            );
            const menu = menus.find((el) =>
                isVisible(el) && (el.innerText || '').includes('전체 다음단계')
            );
            if (!menu) {
                return { clickedToggle: true, clickedMenu: false, reason: 'menu_not_found' };
            }

            menu.click();
            return { clickedToggle: true, clickedMenu: true, reason: '' };
        }"""
    )
    if not result.get("clickedToggle"):
        raise ValueError(
            "포장지시 화면에서 보이는 「다음 단계」 버튼을 찾지 못했습니다. "
            f"reason={result.get('reason')}"
        )
    if not result.get("clickedMenu"):
        raise ValueError(
            "포장지시 화면에서 보이는 「전체 다음단계」 메뉴를 찾지 못했습니다. "
            f"reason={result.get('reason')}"
        )
    page.wait_for_timeout(800)

    for attempt in range(1, 3):
        timeout_ms = 15_000 if attempt == 1 else 5_000
        if not click_popup_ok_if_visible(page, timeout_ms=timeout_ms):
            if attempt == 1:
                raise ValueError(
                    "포장지시 전체 다음단계 alert OK 1회차를 찾지 못했습니다."
                )
            break
        page.wait_for_timeout(500)


def click_out_confirm_tab(page: Page) -> None:
    """「출고확정」 탭을 클릭하고 데이터를 로드합니다."""
    page.locator("#out_exec_view").wait_for(state="visible", timeout=15_000)
    tseq_sno = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if not tseq_sno:
        raise ValueError(
            "출고차수 행이 선택되지 않았습니다. "
            "출고확정 탭을 열 수 없습니다."
        )

    tab = page.locator('a.nav-link[href="#tab_borders_icons-8"]').first
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    page.wait_for_timeout(400)

    page.evaluate(
        """(sno) => {
            if (typeof grid_table_tab8 === 'function') {
                grid_table_tab8(sno, 'ck');
            }
        }""",
        tseq_sno,
    )
    page.wait_for_timeout(1000)


def open_sach_stock_tab(context, config: Dict) -> Page:
    """새 탭에서 화주별 재고 페이지를 엽니다."""
    stock_page = context.new_page()
    stock_page.goto(config["sach_stock_list_url"], wait_until="domcontentloaded")
    stock_page.locator("#searchColumn2").wait_for(state="visible", timeout=15_000)
    stock_page.wait_for_timeout(500)
    return stock_page


def select_stock_search_column_product_code(page: Page) -> None:
    """화주별 재고 검색조건을 상품코드로 선택합니다."""
    page.select_option("#searchColumn2", value="prod_cd")
    page.wait_for_timeout(300)


def open_order_manage_tab(context, config: Dict) -> Page:
    """새 탭에서 주문관리 목록 페이지를 엽니다."""
    manage_page = context.new_page()
    url = join_origin_path(config["login_url"], ORDER_MANAGE_LIST_PATH)
    manage_page.goto(url, wait_until="domcontentloaded")
    wait_order_search_form(manage_page)
    manage_page.wait_for_timeout(500)
    return manage_page


def search_order_by_mall_od_no(page: Page, search_text: str) -> None:
    """검색조건을 주문번호로 선택하고 검색어를 입력한 뒤 검색합니다."""
    page.select_option("#searchColumn", value="mall_od_no")
    page.wait_for_timeout(300)

    txt_loc = page.locator('input[name="searchTxt"], #searchTxt').first
    txt_loc.wait_for(state="visible", timeout=10_000)
    txt_loc.fill(search_text)
    page.wait_for_timeout(300)

    click_search_button(page)


def run_task(page, context, config, *, keep_browser: bool = False) -> None:
    """출고작업 검색 → 박스추천 → 포장지시 탭 이동."""
    from Mate2QA_browser_session import wait_enter_after_task

    goto_out_wk_ord_list(page, config)

    out_tseq_sno = input_out_tseq_sno()
    search_and_select_out_tseq(page, out_tseq_sno)
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

    wait_enter_after_task(keep_browser=keep_browser)


def run() -> None:
    """로그인 → 출고지시~출고확정 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    try:
        run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)
    except OutWkOrdProcessingError as exc:
        print_out_wk_ord_processing_error(exc)


if __name__ == "__main__":
    run()
