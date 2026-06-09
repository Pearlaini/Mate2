# Mate2QA — 로그인 후 작업 메뉴 런처
#
# 실행: python Mate2QA_menu_launcher.py

import importlib
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_login import (
    _is_ably_login_url,
    create_context,
    ensure_login_only,
    load_env_credentials,
)
from Mate2QA_site_config import CONFIG, STATE_FILE_DOMESTIC, print_site_url_banner, refresh_config_from_env

MENU_TEXT = """
============================================================
어떤 작업을 진행할지 번호를 입력해 주세요.
 11  추가: 국내 주문서
 12  이동: 국내 주문발주~출고준비
 13  추가: 화주입고

 21  추가: 국내 출고 수기등록
 22  출고보류해제
 23  이동: 출고등록 ~ 출고지시
 24  이동: 출고지시 ~ 출고확정(수동)
 25  이동: Wave ~ 출고확정(수동)

 31  추가: 입고요청
 41  재고조회(로케이션조회/품목이동)
  0  종료
============================================================
"""

# 아직 연결되지 않은 메뉴
_PENDING_CHOICES: frozenset[str] = frozenset()

# 공통 작업 (사이트 무관)
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


def resolve_task_module(choice: str, login_url: str) -> str | None:
    """입력 번호와 로그인 URL에 따라 실행할 모듈 이름을 반환합니다."""
    if choice in _PENDING_CHOICES:
        print("[안내] 해당 메뉴는 아직 준비 중입니다.")
        return None

    return _COMMON_TASKS.get(choice)


def run_task_module(module_name: str) -> None:
    """선택한 모듈의 run()을 실행합니다. (코드 수정 반영을 위해 매번 reload)"""
    module = importlib.import_module(module_name)
    module = importlib.reload(module)
    run_fn = getattr(module, "run", None)
    if run_fn is None:
        raise AttributeError(f"{module_name}에 run() 함수가 없습니다.")
    run_fn()


def perform_initial_login() -> str:
    """로그인만 수행하고 세션을 저장합니다. 로그인 URL을 반환합니다."""
    print_site_url_banner()
    config = refresh_config_from_env(CONFIG)
    creds = load_env_credentials(config["login_url"])

    with sync_playwright() as p:
        browser, context = create_context(p, config, state_file=STATE_FILE_DOMESTIC)
        page = context.new_page()
        try:
            ensure_login_only(page, context, config, creds, state_file=STATE_FILE_DOMESTIC)
        except PlaywrightTimeoutError:
            raise
        finally:
            context.storage_state(path=str(STATE_FILE_DOMESTIC))
            context.close()
            browser.close()

    return config["login_url"]


def main() -> None:
    """로그인 후 메뉴에서 작업을 선택해 실행합니다. 0 또는 Ctrl+C 전까지 반복합니다."""
    try:
        login_url = perform_initial_login()
    except KeyboardInterrupt:
        return
    except Exception as exc:
        sys.exit(1)

    site_label = "Ably(qa-style)" if _is_ably_login_url(login_url) else "기본(qa-oms 등)"

    while True:
        print(MENU_TEXT)
        try:
            choice = input("번호 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            break

        module_name = resolve_task_module(choice, login_url)
        if not module_name:
            if choice not in _PENDING_CHOICES:
                print(f"[경고] 알 수 없는 번호입니다: {choice}")
            continue

        try:
            run_task_module(module_name)
            print("[안내] 다음 작업 번호를 입력해 주세요. (0=종료)")
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
