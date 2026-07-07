# Mate2QA — 포장지시 JSON 기준 출고작업 탭 일괄 적용 (런처 7번 서브 310)
#
# 실행: 메인 7번 → 31번 → 310번

from typing import Dict

from playwright.sync_api import Page

from Mate2QA_browser_session import wait_enter_after_task
from item_settings.Mate2QA_setItemBtn import CONFIG as _BASE_CONFIG, load_item_settings
from item_settings.Mate2QA_setItemBtnOutComplete import (
    CONFIG as _COMPLETE_CONFIG,
    run_apply_outcomplete,
)
from item_settings.Mate2QA_setItemBtnOutConfirm import (
    CONFIG as _CONFIRM_CONFIG,
    run_apply_outconfirm,
)
from item_settings.Mate2QA_setItemBtnOutInstruction import (
    CONFIG as _INSTRUCTION_CONFIG,
    run_apply_outinstruction,
)
from item_settings.Mate2QA_setItemBtnOutPacking import SETTINGS_FILE_OUTPACKING
from item_settings.Mate2QA_setItemBtnOutPicking import (
    CONFIG as _PICKING_CONFIG,
    run_apply_outpicking,
)
from Mate2QA_site_config import STATE_FILE_DOMESTIC, refresh_config_from_env

SCREEN_NAME = "포장지시 JSON 기준 출고작업 일괄적용"
ACTION_APPLY = "apply"

CONFIG = {
    **_BASE_CONFIG,
    "item_settings_file": SETTINGS_FILE_OUTPACKING.name,
    "outpacking_base_apply_action": ACTION_APPLY,
}

STATE_FILE = STATE_FILE_DOMESTIC


def _target_config(base_config: Dict, runtime_config: Dict) -> Dict:
    """대상 화면 설정에 런타임 로그인/환경값과 포장지시 JSON 파일명을 합칩니다."""
    return {
        **base_config,
        **runtime_config,
        "item_settings_file": SETTINGS_FILE_OUTPACKING.name,
    }


def run_apply_outpacking_json_to_related_tabs(
    page: Page, config: Dict, *, keep_browser: bool = True
) -> None:
    """포장지시 JSON을 기준으로 관련 출고작업 탭 4곳에 항목설정을 적용합니다."""
    settings = load_item_settings(config=config)
    if not settings:
        raise FileNotFoundError(
            f"설정 파일이 없습니다: {SETTINGS_FILE_OUTPACKING}\n"
            "먼저 331번으로 포장지시 JSON을 저장해 주세요."
        )

    targets = [
        ("출고지시", run_apply_outinstruction, _INSTRUCTION_CONFIG),
        ("피킹지시", run_apply_outpicking, _PICKING_CONFIG),
        ("출고확정", run_apply_outconfirm, _CONFIRM_CONFIG),
        ("출고완료", run_apply_outcomplete, _COMPLETE_CONFIG),
    ]

    print(
        f"[안내] 포장지시 JSON 기준 일괄적용 시작: {SETTINGS_FILE_OUTPACKING}",
        flush=True,
    )
    for label, apply_fn, base_config in targets:
        print(f"[안내] {label} 적용 시작", flush=True)
        apply_fn(
            page,
            _target_config(base_config, config),
            keep_browser=keep_browser,
        )
        print(f"[완료] {label} 적용 완료", flush=True)

    print("[완료] 포장지시 JSON 기준 4개 화면 일괄적용 완료", flush=True)


def run_task(page, context, config=None, *, keep_browser: bool = False):
    """310번: 포장지시 JSON 기준으로 출고지시·피킹지시·출고확정·출고완료 적용."""
    cfg = refresh_config_from_env(config or CONFIG)
    run_apply_outpacking_json_to_related_tabs(page, cfg, keep_browser=keep_browser)

    if keep_browser:
        return cfg

    wait_enter_after_task(
        keep_browser=False,
        message=f"{SCREEN_NAME} 완료 후 Enter를 누르세요.",
    )
    return cfg


def run():
    """단독 실행: 포장지시 JSON 기준 일괄적용 후 종료."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
