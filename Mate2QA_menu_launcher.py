# Mate2QA — 작업 메뉴 런처 (브라우저 세션 유지·작업 연속 실행)
#
# 실행: python Mate2QA_menu_launcher.py

import importlib
import traceback
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError

from Mate2QA_browser_session import BrowserSession, apply_task_page_result
from Mate2QA_order_step import (
    OutWkOrdProcessingError,
    print_out_wk_ord_processing_error,
)
from Mate2QA_wm_wave_search import (
    OutAllocRgstSearchEmptyError,
    OutWkOrdSearchEmptyError,
    print_out_alloc_rgst_no_results,
    print_out_wk_ord_no_results,
)
from Mate2QA_shipper_select import (
    change_session_shipper_on_page,
    probe_session_shipper_label,
)
from Mate2QA_site_config import (
    IGFC_LOGIN_HOST,
    _resolve_login_url,
    refresh_config_from_env,
)
from Mate2QA_menu_nav import (
    LauncherExit,
    MAIN_MENU_EXIT,
    SUBMENU_BACK,
    resolve_submenu_choice,
    submenu_nav_footer,
)

# True: 메뉴 표시마다 세션 화주 조회 / False: 런처 시작 1회만 조회
_PROBE_SHIPPER_EACH_MENU = True

_MENU_BODY = f"""
 0  세션 화주 변경            /  7+  항목설정         /  {MAIN_MENU_EXIT}  종료


 11  추가: 국내 주문서               / 12  추가: 해외 주문서
 13  이동: 국내 주문발주 ~ 출고준비   / 14  이동: 해외 주문발주 ~ 출고준비(ing)
 15  추가: 화주입고

 21  추가: 국내 출고 수기등록         / 22  출고보류해제
 23  이동: 출고등록 ~ 출고지시
 24  이동: 출고지시 ~ 출고확정(수동)
 25  이동: Wave ~ 출고확정(수동)
 29  이동: From to 선택

 31  추가: 입고요청
 41  재고조회(로케이션조회/품목이동/재고조정요청)
============================================================
"""

_cached_session_shipper: str | None = None


def _shipper_display_config() -> dict:
    """11번(Mate2QA_AddOmDomesticOrderForm)과 동일한 CONFIG·env 기준입니다."""
    mod = importlib.import_module("Mate2QA_AddOmDomesticOrderForm")
    return refresh_config_from_env(mod.CONFIG)


def _fetch_session_shipper_label(session: Optional[BrowserSession]) -> str:
    """현재 세션 화주명을 읽습니다 (공유 브라우저 또는 별도 headless)."""
    global _cached_session_shipper
    if not _PROBE_SHIPPER_EACH_MENU and _cached_session_shipper is not None:
        return _cached_session_shipper

    config = _shipper_display_config()
    if session and session.page:
        try:
            session.restart_if_needed()
            session.ensure_logged_in(config)
            label = (
                probe_session_shipper_label(config, page=session.page) or ""
            ).strip()
        except Exception as exc:
            print(f"[경고] 세션 화주 확인 실패: {exc}", flush=True)
            label = (_cached_session_shipper or "").strip()
    else:
        print("[안내] 세션 화주를 확인하는 중...", flush=True)
        try:
            label = (probe_session_shipper_label(config) or "").strip()
        except Exception as exc:
            print(f"[경고] 세션 화주 확인 실패: {exc}", flush=True)
            label = (_cached_session_shipper or "").strip()

    _cached_session_shipper = label
    return label


def format_shipper_banner(session: Optional[BrowserSession] = None) -> str:
    """주문목록 세션에 연결된 화주명을 메뉴 문구로 반환합니다."""
    label = _fetch_session_shipper_label(session)
    if label:
        return f"(화주: {label})"
    return "(화주: 선택하세요)"


def build_menu_text(session: Optional[BrowserSession] = None) -> str:
    """화주 배너가 포함된 메뉴 문자열을 반환합니다."""
    shipper_banner = format_shipper_banner(session)
    return (
        "\n============================================================\n"
        f"어떤 작업을 진행할지 번호를 입력해 주세요. {shipper_banner}\n"
        f"{_MENU_BODY}"
    )


_PENDING_CHOICES: frozenset[str] = frozenset()

_ITEM_SETTINGS_SUBMENU = f"""
------------------------------------------------------------
항목설정 — 국내/해외/출고관리/재고현황
11+  국내 주문관리
21+  해외 주문관리
31+  출고관리
41+  재고현황
{submenu_nav_footer(back_label="메인메뉴 복귀")}
------------------------------------------------------------
"""

_OUTALL_ITEM_SETTINGS_SUBMENU = f"""
------------------------------------------------------------
항목설정 — 출고관리
310  포장지시 JSON 기준 → 출고지시·피킹지시·출고확정·출고완료 적용
311  출고지시: JSON 저장  /  312  출고지시: JSON 적용
321  피킹지시: JSON 저장  /  322  피킹지시: JSON 적용
331  포장지시: JSON 저장  /  332  포장지시: JSON 적용
371  출고확정: JSON 저장  /  372  출고확정: JSON 적용
381  출고완료: JSON 저장  /  382  출고완료: JSON 적용
391  출고통합관리: JSON 저장  /  392  출고통합관리: JSON 적용
{submenu_nav_footer(back_label="상위 메뉴 복귀")}
------------------------------------------------------------
"""

_STOCK_ITEM_SETTINGS_SUBMENU = f"""
------------------------------------------------------------
항목설정 — 재고관리>재고현황
411  상품재고: JSON 저장     /  412  상품재고: JSON 적용
421  상품그룹재고: JSON 저장  /  422  상품그룹재고: JSON 적용
431  로케이션재고: JSON 저장  /  432  로케이션재고: JSON 적용
{submenu_nav_footer(back_label="상위 메뉴 복귀")}
------------------------------------------------------------
"""

_ITEM_SETTINGS_TASKS = {
    "11": "item_settings.Mate2QA_setItemBtn",
    "21": "item_settings.Mate2QA_setItemBtnOverseas",
}

_COMMON_TASKS = {
    "11": "Mate2QA_AddOmDomesticOrderForm",
    "12": "Mate2QA_AddOverseasOrderForm",
    "13": "Mate2QA_OmMoveDomestic",
    "14": "Mate2QA_OmMoveOverseas",
    "15": "Mate2QA_AddOmInboundForm",
    "21": "Mate2QA_AddWmDomesticOrderForm",
    "22": "Mate2QA_WmReleaseHold",
    "23": "Mate2QA_WmMoveFromRegtoBox",
    "24": "Mate2QA_WmMoveFromBoxtoFinal",
    "25": "Mate2QA_WmMoveFromWavetoFinal",
    "29": "Mate2QA_WmMoveFromToSelect",
    "31": "Mate2Qa_AddWmInboundForm",
    "41": "Mate2QA_Stock",
}

_OUTALL_WMS_ITEM_SETTINGS: dict[str, tuple[str, str]] = {
    "310": ("item_settings.Mate2QA_setItemBtnOutPackingBaseApply", "apply"),
    "311": ("item_settings.Mate2QA_setItemBtnOutInstruction", "save"),
    "312": ("item_settings.Mate2QA_setItemBtnOutInstruction", "apply"),
    "321": ("item_settings.Mate2QA_setItemBtnOutPicking", "save"),
    "322": ("item_settings.Mate2QA_setItemBtnOutPicking", "apply"),
    "331": ("item_settings.Mate2QA_setItemBtnOutPacking", "save"),
    "332": ("item_settings.Mate2QA_setItemBtnOutPacking", "apply"),
    "371": ("item_settings.Mate2QA_setItemBtnOutConfirm", "save"),
    "372": ("item_settings.Mate2QA_setItemBtnOutConfirm", "apply"),
    "381": ("item_settings.Mate2QA_setItemBtnOutComplete", "save"),
    "382": ("item_settings.Mate2QA_setItemBtnOutComplete", "apply"),
    "391": ("item_settings.Mate2QA_setItemBtnOutall", "save"),
    "392": ("item_settings.Mate2QA_setItemBtnOutall", "apply"),
}

_STOCK_WMS_ITEM_SETTINGS: dict[str, tuple[str, str]] = {
    "411": ("item_settings.Mate2QA_setItemBtnStockProduct", "save"),
    "412": ("item_settings.Mate2QA_setItemBtnStockProduct", "apply"),
    "421": ("item_settings.Mate2QA_setItemBtnStockProductGroup", "save"),
    "422": ("item_settings.Mate2QA_setItemBtnStockProductGroup", "apply"),
    "431": ("item_settings.Mate2QA_setItemBtnStockLocation", "save"),
    "432": ("item_settings.Mate2QA_setItemBtnStockLocation", "apply"),
}

_WMS_ITEM_ACTION_CONFIG_KEYS: dict[str, str] = {
    "311": "outinstruction_item_action",
    "312": "outinstruction_item_action",
    "321": "outpicking_item_action",
    "322": "outpicking_item_action",
    "331": "outpacking_item_action",
    "332": "outpacking_item_action",
    "371": "outconfirm_item_action",
    "372": "outconfirm_item_action",
    "381": "outcomplete_item_action",
    "382": "outcomplete_item_action",
    "391": "outall_item_action",
    "392": "outall_item_action",
}

_STOCK_ITEM_ACTION_CONFIG_KEYS: dict[str, str] = {
    "411": "stock_item_action",
    "412": "stock_item_action",
    "421": "stock_item_action",
    "422": "stock_item_action",
    "431": "stock_item_action",
    "432": "stock_item_action",
}


def _handle_item_settings_task_error(
    session: BrowserSession,
    exc: Exception,
    *,
    return_hint: str,
) -> None:
    """항목설정·출고관리 서브메뉴 공통 오류 처리."""
    if isinstance(exc, PlaywrightError) and (
        "Target page, context or browser has been closed" in str(exc)
    ):
        print(
            "[경고] 브라우저 창이 닫혔습니다. "
            "서브메뉴 9로 나간 뒤 메인 7번을 다시 실행해 주세요.",
            flush=True,
        )
        session.restart_if_needed()
        return

    print(f"[오류] {exc}")
    traceback.print_exc()
    session.prepare_for_task()
    print(f"[안내] {return_hint}", flush=True)


def run_outall_item_settings_submenu(session: BrowserSession) -> None:
    """31번 — 출고관리 항목설정 서브메뉴 (311~392)."""
    while True:
        print(_OUTALL_ITEM_SETTINGS_SUBMENU, flush=True)
        try:
            choice = input("번호 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        nav = resolve_submenu_choice(choice)
        if nav == "exit":
            raise LauncherExit()
        if nav == "back":
            return

        module_action = _OUTALL_WMS_ITEM_SETTINGS.get(choice)
        if not module_action:
            print(f"[경고] 알 수 없는 번호입니다: {choice}", flush=True)
            continue

        module_name, _action = module_action
        try:
            run_task_module(
                module_name,
                session,
                menu_choice=choice,
            )
        except LauncherExit:
            raise
        except KeyboardInterrupt:
            pass
        except (PlaywrightError, Exception) as exc:
            _handle_item_settings_task_error(
                session,
                exc,
                return_hint=(
                    "출고관리 항목설정 서브메뉴로 돌아갑니다. "
                    "다른 번호를 선택해 주세요."
                ),
            )


def run_stock_item_settings_submenu(session: BrowserSession) -> None:
    """41번 — 재고현황 항목설정 서브메뉴 (411~432)."""
    while True:
        print(_STOCK_ITEM_SETTINGS_SUBMENU, flush=True)
        try:
            choice = input("번호 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        nav = resolve_submenu_choice(choice)
        if nav == "exit":
            raise LauncherExit()
        if nav == "back":
            return

        module_action = _STOCK_WMS_ITEM_SETTINGS.get(choice)
        if not module_action:
            print(f"[경고] 알 수 없는 번호입니다: {choice}", flush=True)
            continue

        module_name, _action = module_action
        try:
            run_task_module(
                module_name,
                session,
                menu_choice=choice,
            )
        except LauncherExit:
            raise
        except KeyboardInterrupt:
            pass
        except (PlaywrightError, Exception) as exc:
            _handle_item_settings_task_error(
                session,
                exc,
                return_hint=(
                    "재고현황 항목설정 서브메뉴로 돌아갑니다. "
                    "다른 번호를 선택해 주세요."
                ),
            )


def run_item_settings_submenu(session: BrowserSession) -> None:
    """메인 7번 — 항목설정 서브메뉴."""
    while True:
        print(_ITEM_SETTINGS_SUBMENU, flush=True)
        try:
            choice = input("번호 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        nav = resolve_submenu_choice(choice)
        if nav == "exit":
            raise LauncherExit()
        if nav == "back":
            return

        if choice == "31":
            try:
                run_outall_item_settings_submenu(session)
            except LauncherExit:
                raise
            except KeyboardInterrupt:
                pass
            continue

        if choice == "41":
            try:
                run_stock_item_settings_submenu(session)
            except LauncherExit:
                raise
            except KeyboardInterrupt:
                pass
            continue

        module_name = _ITEM_SETTINGS_TASKS.get(choice)
        if not module_name:
            print(f"[경고] 알 수 없는 번호입니다: {choice}", flush=True)
            continue

        try:
            run_task_module(module_name, session, menu_choice=choice)
        except LauncherExit:
            raise
        except KeyboardInterrupt:
            pass
        except (PlaywrightError, Exception) as exc:
            _handle_item_settings_task_error(
                session,
                exc,
                return_hint=(
                    "항목설정 서브메뉴로 돌아갑니다. "
                    "다른 번호를 선택해 주세요."
                ),
            )


def _is_igfc_site() -> bool:
    """현재 로그인 URL 호스트가 igfc 사이트인지 확인합니다."""
    host = urlparse(_resolve_login_url().strip().lower()).netloc
    return host == IGFC_LOGIN_HOST


def resolve_task_module(choice: str) -> str | None:
    """입력 번호에 따라 실행할 모듈 이름을 반환합니다."""
    if choice in _PENDING_CHOICES:
        print("[안내] 해당 메뉴는 아직 준비 중입니다.")
        return None
    if choice == "12" and _is_igfc_site():
        return "Mate2QA_AddOverseasOrderForm_Igfc"
    return _COMMON_TASKS.get(choice)


def _module_task_config(module, *, menu_choice: str | None = None) -> dict:
    """작업 모듈 전용 CONFIG(sach_cd_value 등)를 env 기준으로 갱신합니다."""
    module_config = getattr(module, "CONFIG", None)
    if module_config is None:
        raise AttributeError(f"{module.__name__}에 CONFIG가 없습니다.")
    task_config = refresh_config_from_env(module_config)
    wms_item = _OUTALL_WMS_ITEM_SETTINGS.get(menu_choice or "")
    if wms_item:
        _module_name, action = wms_item
        config_key = _WMS_ITEM_ACTION_CONFIG_KEYS.get(menu_choice or "")
        if config_key:
            task_config[config_key] = action
    stock_item = _STOCK_WMS_ITEM_SETTINGS.get(menu_choice or "")
    if stock_item:
        _module_name, action = stock_item
        config_key = _STOCK_ITEM_ACTION_CONFIG_KEYS.get(menu_choice or "")
        if config_key:
            task_config[config_key] = action
    return task_config


def run_task_module(
    module_name: str,
    session: BrowserSession,
    *,
    menu_choice: str | None = None,
) -> None:
    """선택한 모듈의 run_task()를 공유 세션에서 실행합니다."""
    module = importlib.import_module(module_name)
    module = importlib.reload(module)
    run_fn = getattr(module, "run_task", None)
    if run_fn is None:
        raise AttributeError(f"{module_name}에 run_task() 함수가 없습니다.")

    task_config = _module_task_config(module, menu_choice=menu_choice)
    session.prepare_for_task()
    config = session.ensure_logged_in(task_config)
    try:
        task_result = run_fn(session.page, session.context, config, keep_browser=True)
        apply_task_page_result(session, task_result)
    except LauncherExit:
        raise
    except OutAllocRgstSearchEmptyError:
        print_out_alloc_rgst_no_results()
    except OutWkOrdSearchEmptyError:
        print_out_wk_ord_no_results()
    except OutWkOrdProcessingError as exc:
        print_out_wk_ord_processing_error(exc)
        print(
            "[안내] 메뉴로 돌아갑니다. 브라우저는 유지됩니다. "
            "다른 번호를 선택해 주세요.",
            flush=True,
        )
    except PlaywrightTimeoutError as exc:
        page_url = (session.page.url if session.page else "").lower()
        if "grid-table-tab3" in str(exc):
            print(
                "[경고] 출고지시 그리드(#grid-table-tab3) 대기 시간 초과 — "
                "여기까지 진행된 상태로 메뉴로 돌아갑니다.",
                flush=True,
            )
        elif "outallocrgst.do" in page_url:
            print_out_alloc_rgst_no_results()
        else:
            raise
    session.prepare_for_task(reset_preserved=False)
    session.save_state()


def main() -> None:
    """메뉴에서 작업을 선택해 실행합니다. 99 또는 Ctrl+C 전까지 브라우저를 유지합니다."""
    with BrowserSession() as session:
        while True:
            print(build_menu_text(session))
            try:
                choice = input("번호 입력: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if choice == MAIN_MENU_EXIT:
                break

            if choice == SUBMENU_BACK:
                print(
                    f"[안내] 메인 메뉴 종료는 {MAIN_MENU_EXIT}번입니다. "
                    f"서브메뉴 복귀는 항목설정(7번) 안에서 {SUBMENU_BACK}번을 사용합니다.",
                    flush=True,
                )
                continue

            if choice == "0":
                try:
                    global _cached_session_shipper
                    config = _shipper_display_config()
                    session.ensure_logged_in(config)
                    _cached_session_shipper = (
                        change_session_shipper_on_page(session.page, config) or ""
                    ).strip() or None
                    session.save_state()
                except KeyboardInterrupt:
                    pass
                except Exception as exc:
                    print(f"[오류] {exc}")
                continue

            if choice == "7":
                try:
                    run_item_settings_submenu(session)
                except LauncherExit:
                    break
                except KeyboardInterrupt:
                    pass
                continue

            module_name = resolve_task_module(choice)
            if not module_name:
                if choice not in _PENDING_CHOICES:
                    print(f"[경고] 알 수 없는 번호입니다: {choice}")
                continue

            try:
                run_task_module(module_name, session, menu_choice=choice)
            except KeyboardInterrupt:
                pass
            except PlaywrightError as exc:
                if "Target page, context or browser has been closed" in str(exc):
                    print(
                        "[경고] 브라우저 창이 닫혔습니다. "
                        "7번 항목설정(11·21)은 서브메뉴 9로 나간 뒤 다시 실행해 주세요.",
                        flush=True,
                    )
                    session.restart_if_needed()
                else:
                    print(f"[오류] {exc}")
                    traceback.print_exc()
                    session.prepare_for_task()
                    print(
                        "[안내] 메뉴로 돌아갑니다. 브라우저는 유지됩니다. "
                        "다른 번호를 선택해 주세요."
                    )
            except Exception as exc:
                print(f"[오류] {exc}")
                traceback.print_exc()
                session.prepare_for_task()
                print("[안내] 메뉴로 돌아갑니다. 브라우저는 유지됩니다. 다른 번호를 선택해 주세요.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
