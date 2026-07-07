# Mate2QA — 런처·서브메뉴 공통 네비게이션 번호

MAIN_MENU_EXIT = "99"
SUBMENU_BACK = "9"


class LauncherExit(Exception):
    """서브메뉴에서 종료(99) 입력 시 런처 전체를 종료합니다."""


def resolve_submenu_choice(choice: str) -> str:
    """서브메뉴 입력을 'continue' | 'back' | 'exit' 로 해석합니다."""
    text = (choice or "").strip()
    if text == MAIN_MENU_EXIT:
        return "exit"
    if text == SUBMENU_BACK:
        return "back"
    return "continue"


def submenu_nav_footer(*, back_label: str) -> str:
    """서브메뉴 하단 복귀·종료 안내 한 줄을 반환합니다."""
    return f" {SUBMENU_BACK}  {back_label}  /  {MAIN_MENU_EXIT}  종료"
