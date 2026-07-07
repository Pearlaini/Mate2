# QA WMS — 시작 단계(From)~목표 단계(To) 선택 이동
#
# 시작·목표 단계 번호를 입력하면, 시작 번호에 해당하는 URL로 먼저 이동한 뒤
# 목표 단계까지 자동 진행합니다.
#
# 단계 번호:
#   1 출고예정  2 웨이브  3 출고차수할당  4 출고작업(목록)
#   5 출고지시  6 피킹지시  7 포장지시  8 출고확정(수동)

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from Mate2QA_order_step import (
    OUT_WK_ORD_PROCESSING_ERROR,
    OutWkOrdProcessingError,
    abort_popup_on_messages,
    print_out_wk_ord_processing_error,
)
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, refresh_config_from_env
from Mate2QA_WmMoveFromBoxtoFinal import (
    click_alert_ok_before_picking_tab,
    click_confirm_product_picking_list,
    click_out_confirm_tab,
    click_packing_instruction_tab,
    click_packing_next_step_all,
    click_picking_instruction_tab,
    click_picking_next_step_to_packing,
    input_out_tseq_sno,
    open_order_manage_tab,
    open_sach_stock_tab,
    run_box_recommend_and_move_next,
    search_and_select_out_tseq,
    search_order_by_mall_od_no,
    select_stock_search_column_product_code,
)
from Mate2QA_WmMoveFromRegtoBox import (
    goto_out_expect_list,
    goto_out_wave_list,
    goto_out_wk_ord_list,
    select_depot_cd_if_needed,
    wait_for_out_wk_ord_after_alloc,
)
from Mate2QA_wm_wave_search import (
    OutAllocRgstSearchEmptyError,
    OutWkOrdSearchEmptyError,
    apply_wm_wave_search,
    capture_out_tseq_nm_from_alloc_page,
    capture_wave_selected_row_context,
    capture_wm_wave_filter_from_page,
    click_address_refine,
    click_out_alloc_assign,
    click_out_alloc_rgst_button,
    click_out_wk_ord_instruction_tab,
    fill_out_alloc_rgst_form,
    is_dlvr_div_empty,
    load_wm_wave_filter,
    print_out_alloc_rgst_no_results,
    print_out_wk_ord_no_results,
    run_wave_process_on_expect_list,
    save_wm_wave_filter,
    search_out_wk_ord_by_tseq_nm,
    select_all_alloc_rgst_targets,
    select_out_wk_ord_row_by_tseq_nm,
)

STATE_FILE = STATE_FILE_DOMESTIC

# (번호, 화면 이름)
WM_STAGES: List[Tuple[str, str]] = [
    ("1", "출고예정"),
    ("2", "웨이브"),
    ("3", "출고차수할당"),
    ("4", "출고작업(목록)"),
    ("5", "출고지시"),
    ("6", "피킹지시"),
    ("7", "포장지시"),
    ("8", "출고확정(수동)"),
]

_STAGE_BY_ID = {stage_id: label for stage_id, label in WM_STAGES}


def stage_label(stage_id: int) -> str:
    """단계 번호에 해당하는 화면 이름을 반환합니다."""
    return _STAGE_BY_ID.get(str(stage_id), f"단계{stage_id}")


def build_stage_menu_text() -> str:
    """단계 선택 안내 문구를 만듭니다."""
    lines = [
        "  WMS 출고 단계 — 시작·목표 번호를 한 번에 입력해 주세요.",
        "  입력 예: 2 5   2-5   2~5   25  (2 웨이브 → 5 출고지시)",
        "",
    ]
    for stage_id, label in WM_STAGES:
        lines.append(f"    {stage_id}  {label}")
    return "\n".join(lines)


def parse_stage_range_input(raw: str) -> Tuple[int, int]:
    """시작·목표 단계 번호 한 줄 입력을 (from, to)로 변환합니다."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("시작·목표 단계를 입력해 주세요.")

    parts = [part for part in re.split(r"[\s,~\-]+", text) if part]
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        from_stage, to_stage = int(parts[0]), int(parts[1])
    elif len(text) == 2 and text.isdigit():
        from_stage, to_stage = int(text[0]), int(text[1])
    else:
        raise ValueError(
            "입력 형식이 올바르지 않습니다. "
            "예: 2 5 / 2-5 / 2~5 / 25"
        )

    valid = set(range(1, 9))
    if from_stage not in valid or to_stage not in valid:
        raise ValueError("단계 번호는 1~8 사이여야 합니다.")
    if to_stage <= from_stage:
        raise ValueError(
            f"목표 단계({to_stage})는 시작 단계({from_stage})보다 커야 합니다."
        )
    return from_stage, to_stage


def prompt_stage_range() -> Tuple[int, int]:
    """시작·목표 단계를 한 번에 입력받습니다."""
    print(build_stage_menu_text(), flush=True)
    print(
        "\n[안내] 시작·목표를 입력하면 시작 번호 화면 URL로 이동합니다.",
        flush=True,
    )

    while True:
        try:
            raw = input("시작·목표 단계 (예: 2 5): ").strip()
        except EOFError as exc:
            raise ValueError("입력이 중단되었습니다.") from exc
        try:
            from_stage, to_stage = parse_stage_range_input(raw)
            print(
                f"[선택] {from_stage} {stage_label(from_stage)} "
                f"→ {to_stage} {stage_label(to_stage)}",
                flush=True,
            )
            return from_stage, to_stage
        except ValueError as exc:
            print(f"[경고] {exc}", flush=True)


def detect_current_wm_stage(page: Page) -> Optional[int]:
    """현재 브라우저 URL·활성 탭으로 WMS 출고 단계를 추정합니다."""
    url = (page.url or "").lower()

    if "outexpectlist.do" in url:
        return 1
    if "outwavelist.do" in url:
        return 2
    if "outallocrgst.do" in url:
        return 3
    if "outwkordlist.do" not in url:
        return None

    tab_stage = page.evaluate(
        """() => {
            const execView = document.querySelector('#out_exec_view');
            if (!execView) return 4;

            const style = window.getComputedStyle(execView);
            const rect = execView.getBoundingClientRect();
            const execVisible = style.display !== 'none'
                && style.visibility !== 'hidden'
                && rect.width > 0
                && rect.height > 0;
            if (!execVisible) return 4;

            const active = document.querySelector(
                '#out_exec_view a.nav-link.active, #out_exec_view .nav-link.active'
            );
            if (!active) return 4;

            const href = (active.getAttribute('href') || '').trim();
            const tabId = (active.id || '').trim();
            if (href.includes('tab_borders_icons-3')) return 5;
            if (href.includes('tab_borders_icons-4')) return 6;
            if (href.includes('tab_borders_icons-8')) return 8;
            if (tabId === 'packing_tab' || href.includes('packing_tab')) return 7;
            return 4;
        }"""
    )
    if isinstance(tab_stage, int) and 4 <= tab_stage <= 8:
        return tab_stage
    return 4


def _merge_filter_data(filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """기존 JSON과 병합해 단계 이동에 필요한 값을 유지합니다."""
    saved = load_wm_wave_filter() or {}
    merged = {**saved, **filter_data}
    if saved.get("out_tseq_nm") and not merged.get("out_tseq_nm"):
        merged["out_tseq_nm"] = saved["out_tseq_nm"]
    return merged


def _ensure_wave_filter_data(page: Page, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """웨이브·할당 단계에 필요한 검색 조건을 확보합니다."""
    filter_data = _merge_filter_data(filter_data)
    if filter_data.get("selected_od_snos"):
        return filter_data

    current = detect_current_wm_stage(page)
    if current == 1:
        print(
            "[안내] 출고예정 화면에서 주문을 체크한 뒤 Enter를 눌러 주세요.",
            flush=True,
        )
        try:
            input()
        except EOFError:
            pass
        filter_data = capture_wm_wave_filter_from_page(page)
    else:
        saved = load_wm_wave_filter()
        if saved:
            filter_data = _merge_filter_data(saved)
        else:
            raise ValueError(
                "search_filter_wm_wave.json이 없습니다. "
                "출고예정·웨이브에서 검색·주문 선택 후 진행하거나 "
                "23·25번을 먼저 실행해 주세요."
            )

    if not filter_data.get("selected_od_snos"):
        raise ValueError(
            "선택된 주문(od_sno)이 없습니다. "
            "출고예정·웨이브 목록에서 주문을 체크해 주세요."
        )
    save_wm_wave_filter(filter_data)
    return filter_data


def _ensure_out_wk_ord_row_selected(page: Page, filter_data: Dict[str, Any]) -> None:
    """출고작업 목록에서 행이 선택되어 있는지 확인하고, 없으면 검색합니다."""
    selected = page.locator("#selected_out_alloc_tseq_sno").input_value().strip()
    if selected:
        return

    out_tseq_nm = (filter_data.get("out_tseq_nm") or "").strip()
    if out_tseq_nm:
        search_out_wk_ord_by_tseq_nm(page, out_tseq_nm)
        select_out_wk_ord_row_by_tseq_nm(page, out_tseq_nm)
        return

    print(
        "[안내] 출고작업 목록에서 출고차수를 검색합니다.",
        flush=True,
    )
    out_tseq_sno = input_out_tseq_sno()
    search_and_select_out_tseq(page, out_tseq_sno)


def goto_out_alloc_rgst(page: Page, config: Dict) -> None:
    """WMS 출고차수할당 화면으로 이동합니다."""
    page.goto(config["out_alloc_rgst_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


def goto_wm_stage(
    page: Page,
    config: Dict,
    filter_data: Dict[str, Any],
    stage_id: int,
) -> Dict[str, Any]:
    """선택한 단계 번호에 해당하는 URL·탭으로 이동합니다."""
    data = _merge_filter_data(filter_data)
    label = stage_label(stage_id)
    print(f"[이동] {stage_id} {label} 화면으로 이동합니다...", flush=True)

    if stage_id == 1:
        goto_out_expect_list(page, config)
    elif stage_id == 2:
        goto_out_wave_list(page, config)
    elif stage_id == 3:
        goto_out_alloc_rgst(page, config)
    elif stage_id == 4:
        goto_out_wk_ord_list(page, config)
    else:
        goto_out_wk_ord_list(page, config)
        _ensure_out_wk_ord_row_selected(page, data)
        if stage_id == 5:
            click_out_wk_ord_instruction_tab(page)
        elif stage_id == 6:
            click_picking_instruction_tab(page)
        elif stage_id == 7:
            click_packing_instruction_tab(page)
        elif stage_id == 8:
            click_out_confirm_tab(page)

    print(f"[이동] 완료 — {page.url}", flush=True)
    return data


def _transition_to_2(page: Page, config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """출고예정 → 웨이브."""
    filter_data = _ensure_wave_filter_data(page, filter_data)
    print(
        "[안내] 3초 이내 WAVE 미변경 시 '화주 합포장 기준'으로 진행됩니다.",
        flush=True,
    )
    run_wave_process_on_expect_list(page, filter_data)
    if "outWaveList.do" not in page.url:
        goto_out_wave_list(page, config)
    return filter_data


def _transition_to_3(page: Page, config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """웨이브 → 출고차수할당."""
    filter_data = _ensure_wave_filter_data(page, filter_data)
    if "outWaveList.do" not in page.url:
        goto_out_wave_list(page, config)

    apply_wm_wave_search(page, filter_data, select_orders=True)
    filter_data = capture_wave_selected_row_context(page, filter_data)
    save_wm_wave_filter(filter_data)

    if not is_dlvr_div_empty(filter_data):
        click_address_refine(page)

    click_out_alloc_assign(page, config["out_alloc_rgst_url"])
    select_depot_cd_if_needed(page)
    fill_out_alloc_rgst_form(page, filter_data)
    return filter_data


def _transition_to_4(page: Page, config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """출고차수할당 → 출고작업 목록."""
    try:
        select_all_alloc_rgst_targets(page)
    except OutAllocRgstSearchEmptyError:
        print_out_alloc_rgst_no_results()
        raise

    out_tseq_nm = capture_out_tseq_nm_from_alloc_page(page)
    if out_tseq_nm:
        filter_data["out_tseq_nm"] = out_tseq_nm
        save_wm_wave_filter(filter_data)

    click_out_alloc_rgst_button(page)
    wait_for_out_wk_ord_after_alloc(page, config)
    return filter_data


def _transition_to_5(page: Page, config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """출고작업 목록 → 출고지시 탭."""
    if "outwkordlist.do" not in (page.url or "").lower():
        goto_out_wk_ord_list(page, config)

    filter_data = _merge_filter_data(filter_data)
    _ensure_out_wk_ord_row_selected(page, filter_data)

    try:
        print("[안내] 출고지시 탭 로드 중...", flush=True)
        click_out_wk_ord_instruction_tab(page)
    except OutWkOrdSearchEmptyError:
        print_out_wk_ord_no_results()
        raise
    except PlaywrightTimeoutError as exc:
        if "grid-table-tab3" in str(exc):
            print(
                "[경고] 출고지시 그리드 로딩이 지연되었습니다. "
                "화면에서 직접 확인해 주세요.",
                flush=True,
            )
        else:
            raise
    return filter_data


def _transition_to_6(page: Page, _config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """출고지시 → 피킹지시."""
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
        run_box_recommend_and_move_next(page)
        click_alert_ok_before_picking_tab(page)
        click_picking_instruction_tab(page)
    return filter_data


def _transition_to_7(page: Page, _config: Dict, filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """피킹지시 → 포장지시."""
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
        click_picking_next_step_to_packing(page)
        click_packing_instruction_tab(page)
    return filter_data


def _transition_to_8(
    page: Page, context, config: Dict, filter_data: Dict[str, Any]
) -> Dict[str, Any]:
    """포장지시 → 출고확정(수동)."""
    with abort_popup_on_messages(OUT_WK_ORD_PROCESSING_ERROR):
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
    return filter_data


_TRANSITIONS: Dict[int, Callable[..., Dict[str, Any]]] = {
    2: _transition_to_2,
    3: _transition_to_3,
    4: _transition_to_4,
    5: _transition_to_5,
    6: _transition_to_6,
    7: _transition_to_7,
    8: _transition_to_8,
}


def run_stage_range(
    page: Page,
    context,
    config: Dict,
    from_stage: int,
    to_stage: int,
    filter_data: Optional[Dict[str, Any]] = None,
) -> None:
    """from_stage 다음부터 to_stage까지 순서대로 이동합니다."""
    if to_stage <= from_stage:
        raise ValueError("목표 단계는 시작 단계보다 뒤여야 합니다.")

    data = _merge_filter_data(filter_data or {})
    for target in range(from_stage + 1, to_stage + 1):
        print(
            f"\n[진행] → {target} {stage_label(target)}",
            flush=True,
        )
        transition = _TRANSITIONS.get(target)
        if transition is None:
            raise ValueError(f"지원하지 않는 목표 단계입니다: {target}")
        if target == 8:
            data = transition(page, context, config, data)
        else:
            data = transition(page, config, data)


def run_task(page, context, config, *, keep_browser: bool = False) -> None:
    """선택한 시작·목표 단계 사이를 자동 이동합니다."""
    from Mate2QA_browser_session import wait_enter_after_task

    from_stage, to_stage = prompt_stage_range()

    print(
        f"\n[안내] {from_stage} {stage_label(from_stage)} "
        f"→ {to_stage} {stage_label(to_stage)} 이동을 시작합니다.",
        flush=True,
    )

    filter_data = load_wm_wave_filter() or {}
    filter_data = goto_wm_stage(page, config, filter_data, from_stage)

    try:
        input(
            f"{from_stage} {stage_label(from_stage)} 화면에서 "
            "준비가 끝나면 Enter를 눌러 주세요..."
        )
    except EOFError:
        pass

    run_stage_range(page, context, config, from_stage, to_stage, filter_data)

    print(
        f"\n[완료] {to_stage} {stage_label(to_stage)} 까지 이동했습니다.",
        flush=True,
    )
    wait_enter_after_task(keep_browser=keep_browser)


def run() -> None:
    """로그인 → From-To 선택 이동 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    try:
        run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)
    except OutWkOrdProcessingError as exc:
        print_out_wk_ord_processing_error(exc)
    except OutAllocRgstSearchEmptyError:
        return
    except OutWkOrdSearchEmptyError:
        return
    except PlaywrightTimeoutError as exc:
        if "grid-table-tab3" in str(exc):
            return
        raise


if __name__ == "__main__":
    run()
