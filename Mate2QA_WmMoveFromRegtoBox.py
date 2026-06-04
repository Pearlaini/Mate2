# QA WMS 전체 플로우 — 출고예정 → WAVE → 할당 → 출고작업 → 박스추천 → 다음단계
#
# 1) 출고예정: 날짜·채널·주문 선택 후 Enter → WAVE
# 2) 웨이브 목록: 저장 조건 검색 → 주소정제(필요 시)
# 3) 출고차수할당 → 출고차수명 JSON 저장
# 4) 출고작업: 출고차수명 검색 → 출고지시 → 박스추천 → 전체 다음단계
#
# 사이트 URL: Mate2QA_site_config.py (상대 path)

from typing import Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner
from Mate2QA_wm_wave_search import (
    apply_wm_wave_search,
    capture_wave_selected_row_context,
    capture_wm_wave_filter_from_page,
    click_address_refine,
    click_out_alloc_assign,
    click_out_alloc_rgst_button,
    click_out_wk_ord_instruction_tab,
    fill_out_alloc_rgst_form,
    is_dlvr_div_empty,
    load_out_tseq_nm,
    run_out_wk_ord_box_recommend_and_next_step,
    run_wave_process_on_expect_list,
    search_out_wk_ord_by_tseq_nm,
    select_all_alloc_rgst_targets,
    select_out_wk_ord_row_by_tseq_nm,
)

STATE_FILE = STATE_FILE_DOMESTIC


def goto_out_expect_list(page, config: Dict):
    """WMS 출고예정 목록 화면으로 이동합니다."""
    page.goto(config["out_expect_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] WMS 출고예정 목록으로 이동했습니다. 현재 URL: {page.url}")


def goto_out_wave_list(page, config: Dict):
    """WMS 웨이브 목록 화면으로 이동합니다."""
    page.goto(config["out_wave_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] WMS 웨이브 목록으로 이동했습니다. 현재 URL: {page.url}")


def goto_out_wk_ord_list(page, config: Dict):
    """WMS 출고작업 목록 화면으로 이동합니다."""
    page.goto(config["out_wk_ord_list_url"], wait_until="domcontentloaded")
    page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(500)
    print(f"[안내] WMS 출고작업 목록으로 이동했습니다. 현재 URL: {page.url}")


def wait_for_out_wk_ord_after_alloc(page, config: Dict) -> None:
    """출고차수 할당 alert OK 후 출고작업 목록 화면 이동을 기다립니다."""
    try:
        page.wait_for_url("**/wm/out/wk/ord/outWkOrdList.do", timeout=60_000)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#srch_gubun").wait_for(state="visible", timeout=15_000)
        page.wait_for_timeout(500)
        print(f"[안내] 출고작업 목록 화면 이동 확인. 현재 URL: {page.url}")
    except PlaywrightTimeoutError:
        print(
            "[안내] 출고작업 목록 자동 이동을 확인하지 못해 "
            "출고작업 목록으로 직접 이동합니다."
        )
        goto_out_wk_ord_list(page, config)


def run():
    """로그인 → 출고예정~할당 → 출고작업 박스추천·다음단계."""
    print_site_url_banner()
    creds = load_env_credentials()

    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG, state_file=STATE_FILE)
        page = context.new_page()

        try:
            ensure_login_only(page, context, CONFIG, creds, state_file=STATE_FILE)
            goto_out_expect_list(page, CONFIG)

            print(
                "[안내] 출고예정: #searchDateRange 날짜 · #sach_cd 채널 · "
                "#searchColumn · #srch_txt 설정 → "
                "「검색」 → 이동할 주문 체크 후 Enter..."
            )
            try:
                input("준비되면 Enter...")
            except EOFError:
                print("[안내] 표준 입력 없음 - 현재 화면 기준으로 진행합니다.")

            filter_data = capture_wm_wave_filter_from_page(page)
            if not filter_data.get("selected_od_snos"):
                raise ValueError(
                    "선택된 주문(od_sno)이 없습니다. "
                    "출고예정 목록에서 주문을 체크한 뒤 Enter를 눌러 주세요."
                )

            run_wave_process_on_expect_list(page, filter_data)

            if "outWaveList.do" not in page.url:
                goto_out_wave_list(page, CONFIG)

            apply_wm_wave_search(page, filter_data, select_orders=True)
            filter_data = capture_wave_selected_row_context(page, filter_data)

            if is_dlvr_div_empty(filter_data):
                print("[안내] 배송구분이 비어 있어 주소 정제 단계를 건너뜁니다.")
            else:
                click_address_refine(page)

            click_out_alloc_assign(page, CONFIG["out_alloc_rgst_url"])
            fill_out_alloc_rgst_form(page, filter_data)
            select_all_alloc_rgst_targets(page)
            click_out_alloc_rgst_button(page)
            wait_for_out_wk_ord_after_alloc(page, CONFIG)

            out_tseq_nm = load_out_tseq_nm()
            if not out_tseq_nm:
                raise ValueError(
                    "출고차수명(out_tseq_nm)이 JSON에 없습니다. "
                    "출고차수할당 단계(fill_out_alloc_rgst_form)를 확인해 주세요."
                )
            print(f"[안내] 출고작업에 사용할 출고차수명: {out_tseq_nm}")

            search_out_wk_ord_by_tseq_nm(page, out_tseq_nm)
            select_out_wk_ord_row_by_tseq_nm(page, out_tseq_nm)
            click_out_wk_ord_instruction_tab(page)
            run_out_wk_ord_box_recommend_and_next_step(page)

            try:
                input(
                    "화면에서 alert OK 확인 후, 작업을 마치고 종료하려면 Enter..."
                )
            except EOFError:
                print("[안내] 표준 입력이 없어 Enter 대기를 건너뜁니다.")
        except PlaywrightTimeoutError as exc:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            if "grid-table-tab3" in str(exc):
                print(
                    "[안내] 출고지시 그리드가 비어 있거나 아직 로딩 중일 수 있습니다. "
                    "출고차수 행 선택·출고지시 탭 상태를 화면에서 확인해 주세요."
                )
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
