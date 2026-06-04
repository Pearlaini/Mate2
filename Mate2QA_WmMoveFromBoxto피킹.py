# QA WMS 출고작업 — 박스 → 피킹지시 이동
#
# 1) 로그인 상태 확인
# 2) 출고작업 목록 이동
# 3) 사용자가 입력한 출고차수명으로 검색
# 4) 출고지시 탭에서 박스추천 실행
# 5) 다음 단계 > 전체 다음단계 실행 후 alert OK 자동 클릭
# 6) 피킹지시 탭 클릭
# 7) 피킹지시 전체 선택 → 피킹 리스트 → 상품별 → alert OK

from contextlib import contextmanager
from typing import Dict, Iterator

from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import create_context, ensure_login_only, load_env_credentials
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


def select_all_picking_instruction_rows(page: Page) -> None:
    """피킹지시(#grid-table-tab4) 그리드의 전체 checkbox를 선택합니다."""
    page.locator("#grid-table-tab4 .tabulator-row").first.wait_for(
        state="visible", timeout=30_000
    )
    result = page.evaluate(
        """() => {
            const grid = document.querySelector('#grid-table-tab4');
            if (!grid) return { total: 0, checked: 0, reason: 'grid_not_found' };

            const rows = Array.from(
                grid.querySelectorAll(
                    '.tabulator-row input[type="checkbox"][aria-label="Select Row"], '
                    + '.tabulator-row input[type="checkbox"]'
                )
            );
            if (rows.length === 0) {
                return { total: 0, checked: 0, reason: 'row_checkbox_not_found' };
            }

            const header = grid.querySelector(
                '.tabulator-header input[type="checkbox"], '
                + 'div.tabulator-col-title input[type="checkbox"]'
            );
            if (header && !header.checked) {
                header.click();
            }

            for (const cb of rows) {
                if (!cb.checked) cb.click();
            }

            const checked = rows.filter((cb) => cb.checked).length;
            return { total: rows.length, checked, reason: '' };
        }"""
    )
    total = int(result.get("total") or 0)
    checked = int(result.get("checked") or 0)
    if total == 0:
        raise ValueError(
            "피킹지시 그리드에서 선택 가능한 checkbox를 찾지 못했습니다. "
            f"reason={result.get('reason')}"
        )
    if checked == 0:
        raise ValueError("피킹지시 그리드 전체 선택이 반영되지 않았습니다.")
    print(f"[안내] 피킹지시 전체 checkbox 선택 완료 ({checked}/{total}건).")


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


def run() -> None:
    """로그인 확인 → 출고작업 검색 → 박스추천 → 피킹 리스트 상품별 출력."""
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
            select_all_picking_instruction_rows(page)
            click_product_picking_list(page)

            try:
                input("피킹지시 탭 확인 후 종료하려면 Enter를 누르세요...")
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
