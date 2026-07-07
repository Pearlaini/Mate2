# QA 해외 주문목록 — 주문발주 ~ 출고준비 이동 (메뉴 14번, 구현 예정)
#
# 사이트 URL 변경: Mate2QA_site_config.py (또는 Mate2QA_login.env)

from Mate2QA_site_config import CONFIG as _SITE_CONFIG, STATE_FILE_DEFAULT

CONFIG = {**_SITE_CONFIG}

# 해외 주문 세션 (국내 storage_state_domestic.json과 분리)
STATE_FILE = STATE_FILE_DEFAULT


def run_task(page, context, config, *, keep_browser: bool = False):
    """해외 주문 이동 자동화 (구현 예정)."""
    print("[안내] 해외 주문발주 ~ 출고준비 이동은 아직 준비 중입니다.", flush=True)


def run():
    """로그인 후 해외 주문 이동 자동화 (단독 실행, 구현 예정)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
