# Mate2QA — 해외 항목설정 (런처 7번 → 서브 21)
#
# 실행: python -m item_settings.Mate2QA_setItemBtnOverseas

from item_settings.Mate2QA_setItemBtn import (
    CONFIG as _BASE_CONFIG,
    SCOPE_OVERSEAS,
    SETTINGS_FILE_OVERSEAS,
    run_task as _run_task,
)
from Mate2QA_site_config import STATE_FILE_DEFAULT, refresh_config_from_env

CONFIG = {
    **_BASE_CONFIG,
    "item_settings_scope": SCOPE_OVERSEAS,
    "item_settings_file": SETTINGS_FILE_OVERSEAS.name,
}

STATE_FILE = STATE_FILE_DEFAULT


def run_task(page, context, config=None, *, keep_browser: bool = False):
    """해외 항목설정 서브메뉴를 실행합니다."""
    cfg = refresh_config_from_env(config or CONFIG)
    return _run_task(page, context, cfg, keep_browser=keep_browser)


def run():
    """로그인 후 해외 항목설정 서브메뉴 실행 (단독 실행)."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
