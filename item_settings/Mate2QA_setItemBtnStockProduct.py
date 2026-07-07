# Mate2QA — WMS 상품재고 항목설정 JSON 저장·적용 (런처 7번 서브 411·412)

from item_settings.Mate2QA_setItemBtnStockCommon import (
    ACTION_SAVE,
    CONFIG as _BASE_CONFIG,
    STATE_FILE,
    run_stock_item_task,
)
from Mate2QA_site_config import PROJECT_DIR

SETTINGS_FILE_STOCK_PRODUCT = PROJECT_DIR / "grid_item_settings_stock_product.json"
SCREEN_NAME = "상품재고"

CONFIG = {
    **_BASE_CONFIG,
    "item_settings_file": SETTINGS_FILE_STOCK_PRODUCT.name,
    "stock_item_action": ACTION_SAVE,
    "stock_item_screen_name": SCREEN_NAME,
    "stock_item_screen_key": "stock_product",
    "stock_item_url_key": "sach_prod_stock_list_url",
    "stock_item_save_menu_no": "411",
}


def run_task(page, context, config=None, *, keep_browser: bool = False):
    """411(save) 또는 412(apply) 항목설정 작업을 실행합니다."""
    return run_stock_item_task(page, context, config or CONFIG, keep_browser=keep_browser)


def run():
    """단독 실행: 저장(기본) 후 종료."""
    from Mate2QA_browser_session import run_with_browser

    run_with_browser(run_task, config=CONFIG, state_file=STATE_FILE)


if __name__ == "__main__":
    run()
