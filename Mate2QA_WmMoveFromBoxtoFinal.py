# QA WMS 출고작업 — 박스 → 피킹지시 이동
#
# 1) 로그인 상태 확인
# 2) 출고작업 목록 이동
# 3) 사용자가 입력한 출고차수명으로 검색
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
from Mate2QA_order_step import click_popup_ok_if_visible
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner
from Mate2QA_wm_wave_search import (
    ALERT_OK_POLICY,
    click_all_picking_instrt,
    click_box_recommend_dropdown,
    click_out_wk_ord_instruction_tab,
    click_out_wk_ord_next_step_dropdown,
    click_total_box_recommend,
    search_out_wk_ord_by_tseq_nm,
    select_out_wk_ord_row_by_tseq_nm,
)

STATE_FILE = STATE_FILE_DOMESTIC
OUT_WK_ORD_LIST_URL = "https://qa-oms.ourbox.co.kr/wm/out/wk/ord/outWkOrdList.do"
SACH_STOCK_LIST_URL = "https://qa-oms.ourbox.co.kr/wm/stock/sach/sachList.do"


def goto_out_wk_ord_list(page: Page, config: Dict) -> None:
    """WMS 출고작업 목록 화면으로 이동합니다."""
    url = config.get("out_wk_ord_list_url") or OUT_WK_ORD_LIST_URL
    page.goto(url, wait_until="domcontentloaded")
    page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(500)
    print(f"[안내] WMS 출고작업 목록으로 이동했습니다. 현재 URL: {page.url}")


def input_out_tseq_nm() -> str:
    """사용자에게 출고차수명을 직접 입력받습니다."""
    try:
        out_tseq_nm = input("출고차수명을 입력해 주세요: ").strip()
    except EOFError as exc:
        raise ValueError("출고차수명을 입력받지 못했습니다.") from exc

    if not out_tseq_nm:
        raise ValueError("출고차수명이 비어 있습니다. 출고차수명을 입력해 주세요.")
    return out_tseq_nm


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
    click_total_box_recommend(page)
    click_out_wk_ord_next_step_dropdown(page)
    with auto_ok_for_all_next_step():
        click_all_picking_instrt(page)
    page.wait_for_timeout(1000)
    print("[안내] 박스추천 후 「전체 다음단계」 alert OK까지 처리했습니다.")


def click_alert_ok_before_picking_tab(page: Page) -> None:
    """피킹지시 탭 클릭 전에 추가로 뜨는 alert OK를 클릭합니다."""
    if click_popup_ok_if_visible(page, timeout_ms=10_000):
        print("[안내] 피킹지시 탭 클릭 전 추가 alert OK를 클릭했습니다.")
    else:
        print("[안내] 피킹지시 탭 클릭 전 추가 alert이 없어 계속 진행합니다.")


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
    print(f"[안내] 「피킹지시」 탭 클릭 완료. out_alloc_tseq_sno={tseq_sno}")


def click_product_picking_list(page: Page) -> None:
    """피킹 리스트 드롭다운에서 「상품별」을 클릭한 뒤 alert OK를 클릭합니다."""
    picking_btn = page.locator("#picking_btn_06").first
    picking_btn.wait_for(state="visible", timeout=10_000)
    picking_btn.click()
    page.wait_for_timeout(400)
    print("[안내] 「피킹 리스트」(#picking_btn_06) 버튼 클릭.")

    product_btn = page.locator("#sel_picking_list_by_prod_pick").first
    product_btn.wait_for(state="visible", timeout=10_000)
    product_btn.click()
    page.wait_for_timeout(800)
    print("[안내] 「상품별」(#sel_picking_list_by_prod_pick) 버튼 클릭.")

    if not click_popup_ok_if_visible(page, timeout_ms=15_000):
        raise ValueError("피킹 리스트 상품별 alert에서 OK/확인 버튼을 찾지 못했습니다.")
    print("[안내] 피킹 리스트 상품별 alert OK를 클릭했습니다.")


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
    print(
        "[안내] 출고확정 전체 checkbox 선택 완료 "
        f"({int(result.get('checked') or 0)}/{int(result.get('total') or 0)}건)."
    )


def click_confirm_product_picking_list(page: Page) -> None:
    """출고확정 탭에서 전체 선택 후 피킹 리스트 드롭다운의 「상품별」을 클릭합니다."""
    select_all_out_confirm_rows(page)

    picking_btn = page.locator("#picking_btn_08").first
    picking_btn.wait_for(state="visible", timeout=10_000)
    picking_btn.click()
    page.wait_for_timeout(400)
    print("[안내] 출고확정 「피킹 리스트」(#picking_btn_08) 버튼 클릭.")

    product_btn = page.locator("#sel_picking_list_by_prod_confrm").first
    product_btn.wait_for(state="visible", timeout=10_000)
    product_btn.click()
    page.wait_for_timeout(800)
    print("[안내] 출고확정 「상품별」(#sel_picking_list_by_prod_confrm) 버튼 클릭.")

    if not click_popup_ok_if_visible(page, timeout_ms=15_000):
        raise ValueError("출고확정 피킹 리스트 상품별 alert에서 OK/확인 버튼을 찾지 못했습니다.")
    print("[안내] 출고확정 피킹 리스트 상품별 alert OK를 클릭했습니다.")


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
    print("[안내] 피킹지시 「다음 단계」 버튼 클릭.")

    all_next_btn = page.locator("#all_packing_instrt").first
    all_next_btn.wait_for(state="visible", timeout=10_000)
    all_next_btn.click()
    page.wait_for_timeout(800)
    print("[안내] 피킹지시 「전체 다음단계」(#all_packing_instrt) 클릭.")

    for attempt in range(1, 3):
        if not click_popup_ok_if_visible(page, timeout_ms=15_000):
            raise ValueError(
                f"피킹지시 전체 다음단계 alert OK {attempt}회차를 찾지 못했습니다."
            )
        print(f"[안내] 피킹지시 전체 다음단계 alert OK {attempt}회차 클릭.")


def click_packing_instruction_tab(page: Page) -> None:
    """「포장지시」 탭을 클릭합니다."""
    packing_tab = page.locator("#packing_tab").first
    packing_tab.wait_for(state="visible", timeout=10_000)
    packing_tab.click()
    page.wait_for_timeout(1000)
    print("[안내] 「포장지시」(#packing_tab) 탭 클릭 완료.")


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
    print("[안내] 포장지시 「다음 단계 > 전체 다음단계」 클릭.")

    for attempt in range(1, 3):
        if not click_popup_ok_if_visible(page, timeout_ms=15_000):
            raise ValueError(
                f"포장지시 전체 다음단계 alert OK {attempt}회차를 찾지 못했습니다."
            )
        print(f"[안내] 포장지시 전체 다음단계 alert OK {attempt}회차 클릭.")


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
    print(f"[안내] 「출고확정」 탭 클릭 완료. out_alloc_tseq_sno={tseq_sno}")


def open_sach_stock_tab(context) -> Page:
    """새 탭에서 화주별 재고 페이지를 엽니다."""
    stock_page = context.new_page()
    stock_page.goto(SACH_STOCK_LIST_URL, wait_until="domcontentloaded")
    stock_page.locator("#searchColumn2").wait_for(state="visible", timeout=15_000)
    stock_page.wait_for_timeout(500)
    print(f"[안내] 새 탭에서 화주별 재고 페이지를 열었습니다. 현재 URL: {stock_page.url}")
    return stock_page


def select_stock_search_column_product_code(page: Page) -> None:
    """화주별 재고 검색조건을 상품코드로 선택합니다."""
    page.select_option("#searchColumn2", value="prod_cd")
    page.wait_for_timeout(300)
    print("[안내] 화주별 재고 검색조건을 상품코드(prod_cd)로 선택했습니다.")


def run() -> None:
    """로그인 확인 → 출고작업 검색 → 박스추천 → 포장지시 탭 이동."""
    print_site_url_banner()
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_out_wk_ord_list(page, CONFIG)

            out_tseq_nm = input_out_tseq_nm()
            print(f"[안내] 입력한 출고차수명: {out_tseq_nm}")

            search_out_wk_ord_by_tseq_nm(page, out_tseq_nm)
            select_out_wk_ord_row_by_tseq_nm(page, out_tseq_nm)
            click_out_wk_ord_instruction_tab(page)
            run_box_recommend_and_move_next(page)
            click_alert_ok_before_picking_tab(page)
            click_picking_instruction_tab(page)
            click_picking_next_step_to_packing(page)
            click_packing_instruction_tab(page)
            click_packing_next_step_all(page)
            click_out_confirm_tab(page)
            stock_page = open_sach_stock_tab(context)
            select_stock_search_column_product_code(stock_page)
            page.bring_to_front()
            page.wait_for_timeout(500)
            click_out_confirm_tab(page)
            click_confirm_product_picking_list(page)

            try:
                input("출고확정/재고/피킹 리스트 확인 후 종료하려면 Enter를 누르세요...")
            except EOFError:
                print("[안내] 표준 입력이 없어 Enter 대기를 건너뜁니다.")
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
