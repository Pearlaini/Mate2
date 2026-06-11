# Mate2QA — 작업 메뉴 런처 (브라우저 세션 유지·작업 연속 실행)
#
# 실행: python Mate2QA_menu_launcher.py

import importlib
from typing import Optional

from Mate2QA_browser_session import BrowserSession
from Mate2QA_shipper_select import (
    change_session_shipper_on_page,
    probe_session_shipper_label,
)
from Mate2QA_site_config import refresh_config_from_env

# True: 메뉴 표시마다 세션 화주 조회 / False: 런처 시작 1회만 조회
_PROBE_SHIPPER_EACH_MENU = True

_MENU_BODY = """
 0  세션 화주 변경                  / 9  종료
 11  추가: 국내 주문서
 12  이동: 국내 주문발주 ~ 출고준비  / 13  추가: 화주입고

 21  추가: 국내 출고 수기등록        / 22  출고보류해제
 23  이동: 출고등록 ~ 출고지시
 24  이동: 출고지시 ~ 출고확정(수동)
 25  이동: Wave ~ 출고확정(수동)

 31  추가: 입고요청
 41  재고조회(로케이션조회/품목이동)
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
            session.ensure_logged_in()
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
        "============================================================\n"
        f"어떤 작업을 진행할지 번호를 입력해 주세요. {shipper_banner}\n"
        f"{_MENU_BODY}"
    )


_PENDING_CHOICES: frozenset[str] = frozenset()

_COMMON_TASKS = {
    "11": "Mate2QA_AddOmDomesticOrderForm",
    "12": "Mate2QA_OmMoveDomestic",
    "13": "Mate2QA_AddOmInboundForm",
    "21": "Mate2QA_AddWmDomesticOrderForm",
    "22": "Mate2QA_WmReleaseHold",
    "23": "Mate2QA_WmMoveFromRegtoBox",
    "24": "Mate2QA_WmMoveFromBoxtoFinal",
    "25": "Mate2QA_WmMoveFromWavetoFinal",
    "31": "Mate2Qa_AddWmInboundForm",
    "41": "Mate2QA_Stock",
}


def resolve_task_module(choice: str) -> str | None:
    """입력 번호에 따라 실행할 모듈 이름을 반환합니다."""
    if choice in _PENDING_CHOICES:
        print("[안내] 해당 메뉴는 아직 준비 중입니다.")
        return None
    return _COMMON_TASKS.get(choice)


def run_task_module(module_name: str, session: BrowserSession) -> None:
    """선택한 모듈의 run_task()를 공유 세션에서 실행합니다."""
    module = importlib.import_module(module_name)
    module = importlib.reload(module)
    run_fn = getattr(module, "run_task", None)
    if run_fn is None:
        raise AttributeError(f"{module_name}에 run_task() 함수가 없습니다.")

    session.prepare_for_task()
    config = session.ensure_logged_in()
    run_fn(session.page, session.context, config, keep_browser=True)
    session.prepare_for_task()
    session.save_state()


def main() -> None:
    """메뉴에서 작업을 선택해 실행합니다. 9 또는 Ctrl+C 전까지 브라우저를 유지합니다."""
    print(
        "[안내] 브라우저를 시작합니다. 작업 후에도 창은 유지됩니다. (9=종료)",
        flush=True,
    )
    with BrowserSession() as session:
        while True:
            print(build_menu_text(session))
            try:
                choice = input("번호 입력: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if choice == "9":
                break

            if choice == "0":
                try:
                    global _cached_session_shipper
                    config = _shipper_display_config()
                    session.ensure_logged_in()
                    _cached_session_shipper = (
                        change_session_shipper_on_page(session.page, config) or ""
                    ).strip() or None
                    session.save_state()
                    print("[안내] 메뉴로 돌아갑니다. 변경된 화주가 배너에 표시됩니다.")
                except KeyboardInterrupt:
                    pass
                except Exception as exc:
                    print(f"[오류] {exc}")
                continue

            module_name = resolve_task_module(choice)
            if not module_name:
                if choice not in _PENDING_CHOICES:
                    print(f"[경고] 알 수 없는 번호입니다: {choice}")
                continue

            try:
                run_task_module(module_name, session)
                print("[안내] 다음 작업 번호를 입력해 주세요. (9=종료)")
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                print(f"[오류] {exc}")
                print("[안내] 메뉴로 돌아갑니다. 다른 번호를 선택해 주세요.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
