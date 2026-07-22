# QA 공통 — 화주(pwn_header_change) 선택 (터미널·브라우저 모두 지원)

import sys
from typing import Dict, List, Optional

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from Mate2QA_login import _is_ably_login_url, first_visible_locator, load_env_shipper_label
from Mate2QA_order_search import load_search_filter

_SHIPPER_SELECT = 'select[name="pwn_header_change"]'

# 화주 change 후 해당 화면 버튼 로딩 대기용 (작업 모듈에서 공통 사용)
PAGE_READY_WM_INBOUND = ["#btnReqRgst", 'button:has-text("입고등록")']
PAGE_READY_WM_OUT_EXPECT = [
    "#outExpectRgstBtn",
    'button:has-text("출고 수기등록")',
]
PAGE_READY_OM_PUT_EXPECT = [
    "#btnReqRgst",
    'button:has-text("입고등록")',
    'button:has-text("등록")',
]
PAGE_READY_OM_ORDER_LIST = [
    'button:has-text("주문서추가")',
    'a:has-text("주문서추가")',
    'button:has-text("등록")',
    'a:has-text("등록")',
]
_SHIPPER_PLACEHOLDER = "선택하세요"

_SHIPPER_READ_SCRIPT = """() => {
    const el = document.querySelector('select[name="pwn_header_change"]');
    if (!el) return { value: '', text: '' };
    const opt = el.options[el.selectedIndex];
    return {
        value: (el.value || '').trim(),
        text: opt ? (opt.textContent || '').trim() : '',
    };
}"""


def resolve_shipper_label(config: Dict) -> str:
    """화주 이름: JSON → CONFIG → env → 사이트 기본 순으로 읽습니다."""
    data = load_search_filter()
    if data:
        label = (data.get("shipper_label") or "").strip()
        if label:
            return label
    configured = (config.get("shipper_label") or "").strip()
    if configured:
        return configured
    env_label = load_env_shipper_label(config.get("login_url"))
    if env_label:
        return env_label
    login_url = (config.get("login_url") or "").strip()
    if login_url and _is_ably_login_url(login_url):
        return (config.get("shipper_label_ably_default") or "").strip()
    return (config.get("shipper_label_default") or "").strip()


def _get_shipper_options(page) -> List[Dict[str, str]]:
    """pwn_header_change 드롭다운의 option 목록을 반환합니다."""
    return page.evaluate(
        """() => {
            const el = document.querySelector('select[name="pwn_header_change"]');
            if (!el) return [];
            return Array.from(el.options).map((o) => ({
                value: (o.value || '').trim(),
                text: (o.textContent || '').trim(),
            }));
        }"""
    )


def _is_shipper_page_unstable_error(exc: Exception) -> bool:
    """화주 변경 직후 페이지 이동 중 발생하는 일시 오류인지 확인합니다."""
    msg = str(exc).lower()
    return (
        "execution context was destroyed" in msg
        or "navigation" in msg
        or "target closed" in msg
    )


def _read_current_shipper(page, *, retries: int = 8) -> tuple[str, str]:
    """현재 선택된 화주 (value, text)를 반환합니다."""
    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            result = page.evaluate(_SHIPPER_READ_SCRIPT)
            return (result.get("value") or "").strip(), (result.get("text") or "").strip()
        except PlaywrightError as exc:
            last_err = exc
            if not _is_shipper_page_unstable_error(exc):
                raise
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(400)
    if last_err:
        raise last_err
    return "", ""


def _is_shipper_placeholder(value: str, text: str) -> bool:
    """아직 화주를 고르지 않은 '선택하세요' 상태인지 확인합니다."""
    if not value:
        return True
    return text == _SHIPPER_PLACEHOLDER


def read_current_shipper_label(page) -> str:
    """현재 페이지 화주 드롭다운 표시명. '선택하세요'·미선택이면 빈 문자열."""
    value, text = _read_current_shipper(page, retries=3)
    if _is_shipper_placeholder(value, text):
        return ""
    return text


def _wait_for_shipper_dropdown(page, *, timeout_ms: int = 12_000) -> bool:
    """pwn_header_change 드롭다운이 보이고 option이 로드될 때까지 대기합니다."""
    if page.locator(_SHIPPER_SELECT).count() == 0:
        return False
    try:
        page.locator(_SHIPPER_SELECT).first.wait_for(state="visible", timeout=timeout_ms)
        page.wait_for_function(
            """() => {
                const el = document.querySelector('select[name="pwn_header_change"]');
                return el && el.options && el.options.length > 1;
            }""",
            timeout=timeout_ms,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def _selectable_shipper_options(options: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """placeholder를 제외한 선택 가능한 화주 목록입니다."""
    return [
        opt
        for opt in options
        if opt.get("value") and opt.get("text") != _SHIPPER_PLACEHOLDER
    ]


def _find_shipper_choice(
    choices: List[Dict[str, str]], *, value: str = "", text: str = ""
) -> Optional[Dict[str, str]]:
    """value·text와 일치하는 화주 option을 목록에서 찾습니다."""
    val = (value or "").strip()
    lbl = (text or "").strip()
    if val:
        for opt in choices:
            if opt.get("value") == val:
                return opt
    if lbl:
        for opt in choices:
            if opt.get("text") == lbl:
                return opt
    return None


def _resolve_browser_shipper_pick(
    page, choices: List[Dict[str, str]]
) -> Optional[Dict[str, str]]:
    """브라우저 드롭다운에서 placeholder가 아닌 화주가 선택됐는지 확인합니다."""
    current_value, current_text = _read_current_shipper(page)
    if _is_shipper_placeholder(current_value, current_text):
        return None
    matched = _find_shipper_choice(
        choices, value=current_value, text=current_text
    )
    return matched or {"value": current_value, "text": current_text}


def _apply_shipper_value(page, value: str) -> str:
    """드롭다운 value로 화주를 선택하고 선택된 화주명을 반환합니다."""
    current_value, _ = _read_current_shipper(page)
    if current_value == (value or "").strip():
        _, current_text = _read_current_shipper(page)
        return current_text

    script = """(value) => {
        const el = document.querySelector('select[name="pwn_header_change"]');
        if (!el) return '';
        el.value = value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        const opt = el.options[el.selectedIndex];
        return opt ? (opt.textContent || '').trim() : '';
    }"""

    try:
        with page.expect_navigation(timeout=20_000, wait_until="domcontentloaded"):
            return page.evaluate(script, value)
    except PlaywrightTimeoutError:
        return page.evaluate(script, value)


def _stdin_has_buffered_input() -> bool:
    """터미널에 입력 대기 중인 글자가 있는지 확인합니다."""
    if sys.platform == "win32":
        import msvcrt

        return msvcrt.kbhit()
    import select

    return bool(select.select([sys.stdin], [], [], 0)[0])


def _read_stdin_line_if_ready() -> Optional[str]:
    """입력이 준비됐을 때만 한 줄을 읽습니다 (블로킹 없음)."""
    if not _stdin_has_buffered_input():
        return None
    return sys.stdin.readline().strip()


def wait_after_shipper_change(
    page,
    *,
    page_ready_selectors: Optional[List[str]] = None,
) -> None:
    """화주 change 이벤트 후 화면이 다시 안정될 때까지 대기합니다."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass

    try:
        page.wait_for_function(
            """() => {
                const el = document.querySelector('select[name="pwn_header_change"]');
                return el && el.value && el.value.trim() !== '';
            }""",
            timeout=10_000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(800)
    if page_ready_selectors:
        btn, _ = first_visible_locator(page, page_ready_selectors)
        if not btn:
            page.wait_for_timeout(1000)


def _ask_user_pick_shipper(
    page,
    choices: List[Dict[str, str]],
    *,
    missing_label: str = "",
) -> tuple[Dict[str, str], bool]:
    """설정 화주가 없거나 '선택하세요'일 때 사용자에게 화주를 묻습니다.

    터미널 번호 입력 또는 브라우저 드롭다운 직접 선택 모두 인식합니다.
    반환: (선택한 화주, 브라우저에서 직접 선택했는지 여부)
    """
    browser_pick = _resolve_browser_shipper_pick(page, choices)
    if browser_pick:
        return browser_pick, True

    if missing_label:
        print(
            f"\n[안내] 설정된 화주 '{missing_label}'이(가) 화주 목록에 없습니다.",
            flush=True,
        )
    print(
        "화주를 선택해 주세요.\n"
        "  · 터미널(검은 창)에 번호 입력\n"
        "  · 또는 브라우저 화주 드롭다운에서 직접 선택",
        flush=True,
    )
    for idx, opt in enumerate(choices, start=1):
        print(f"  {idx}  {opt['text']} ({opt['value']})", flush=True)

    print("번호 입력 (또는 화주명): ", end="", flush=True)
    raw: Optional[str] = None
    while raw is None:
        browser_pick = _resolve_browser_shipper_pick(page, choices)
        if browser_pick:
            return browser_pick, True
        try:
            line = _read_stdin_line_if_ready()
        except EOFError:
            line = None
        if line is not None:
            raw = line
            break
        page.wait_for_timeout(400)

    if raw == "":
        browser_pick = _resolve_browser_shipper_pick(page, choices)
        if browser_pick:
            return browser_pick, True
        print("[경고] 번호 또는 화주명을 입력해 주세요.", flush=True)
        return _ask_user_pick_shipper(page, choices, missing_label=missing_label)

    if raw.isdigit():
        pick_idx = int(raw) - 1
        if 0 <= pick_idx < len(choices):
            return choices[pick_idx], False
        print(f"[경고] 1~{len(choices)} 사이 번호를 입력해 주세요.", flush=True)
        return _ask_user_pick_shipper(page, choices, missing_label=missing_label)

    matched = _find_shipper_choice(choices, text=raw) or _find_shipper_choice(
        choices, value=raw
    )
    if matched:
        return matched, False
    print("[경고] 목록에 없는 입력입니다. 번호 또는 화주명을 다시 입력해 주세요.", flush=True)
    return _ask_user_pick_shipper(page, choices, missing_label=missing_label)


def select_shipper_on_page(
    page,
    config: Dict,
    *,
    page_ready_selectors: Optional[List[str]] = None,
    target_label: Optional[str] = None,
) -> None:
    """pwn_header_change에서 화주사를 선택합니다.

    - 이미 세션 화주가 선택되어 있으면 그대로 유지합니다 (C).
    - '선택하세요'이고 target_label이 목록에 있으면 자동 선택합니다.
    - target_label이 비어 있거나 목록에 없으면 '선택하세요'를 유지합니다 (B).
    - target_label을 넘기지 않으면 resolve_shipper_label(config)을 사용합니다.
    """
    if target_label is None:
        target_label = resolve_shipper_label(config)
    else:
        target_label = (target_label or "").strip()

    selector = _SHIPPER_SELECT

    if page.locator(selector).count() == 0:
        return

    try:
        page.locator(selector).first.wait_for(state="visible", timeout=15_000)
        page.wait_for_function(
            """() => {
                const el = document.querySelector('select[name="pwn_header_change"]');
                return el && el.options && el.options.length > 1;
            }""",
            timeout=15_000,
        )
    except PlaywrightTimeoutError:
        pass

    current_value, current_text = _read_current_shipper(page)
    if not _is_shipper_placeholder(current_value, current_text):
        wait_after_shipper_change(page, page_ready_selectors=page_ready_selectors)
        return

    if not target_label:
        return

    selectable = _selectable_shipper_options(_get_shipper_options(page))
    if not selectable:
        raise ValueError("선택 가능한 화주 option이 없습니다.")

    match = next((o for o in selectable if o["text"] == target_label), None)
    if match:
        _apply_shipper_value(page, match["value"])
        wait_after_shipper_change(page, page_ready_selectors=page_ready_selectors)
        return

    print(
        f"[경고] 설정 화주 '{target_label}'이(가) 목록에 없어 '선택하세요'를 유지합니다.",
        flush=True,
    )


def read_session_shipper_label_on_page(page, config: Dict) -> str:
    """이미 열린 브라우저 탭에서 주문목록 화주명을 읽습니다.

    현재 화면에 화주 드롭다운(공통 헤더)이 있으면 이동 없이 바로 읽어
    메뉴 표시 때마다 주문목록으로 재이동하던 깜박임을 없앱니다.
    """
    try:
        if page.locator(_SHIPPER_SELECT).count() > 0 and _wait_for_shipper_dropdown(
            page, timeout_ms=5_000
        ):
            return read_current_shipper_label(page)
    except PlaywrightError:
        pass

    order_list_url = (config.get("order_list_url") or "").strip()
    if not order_list_url:
        return ""

    page.goto(order_list_url, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    if not _wait_for_shipper_dropdown(page):
        return ""
    return read_current_shipper_label(page)


def change_session_shipper_on_page(page, config: Dict) -> str:
    """이미 열린 브라우저에서 화주를 직접 바꾼 뒤 JSON에 저장합니다.

    터미널 Enter는 변경 완료 확인용입니다.
    반환: 변경 후 화주명 (미선택이면 빈 문자열)
    """
    from Mate2QA_order_search import load_search_filter, save_search_filter

    order_list_url = (config.get("order_list_url") or "").strip()
    if not order_list_url:
        raise ValueError("order_list_url이 설정되지 않았습니다.")

    page.goto(order_list_url, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    if not _wait_for_shipper_dropdown(page):
        raise ValueError(
            "화주 드롭다운을 찾지 못했습니다. 주문목록 화면을 확인해 주세요."
        )

    before_label = read_current_shipper_label(page)
    if before_label:
        print(f"[안내] 현재 세션 화주: {before_label}", flush=True)
    else:
        print("[안내] 현재 화주가 선택되지 않았습니다.", flush=True)

    print(
        "브라우저 상단의 화주 드롭다운에서 원하는 화주를 선택해 주세요.",
        flush=True,
    )
    print("변경이 끝나면 이 터미널에서 Enter를 눌러 주세요.", flush=True)
    try:
        input()
    except EOFError:
        pass

    wait_after_shipper_change(
        page, page_ready_selectors=PAGE_READY_OM_ORDER_LIST
    )
    after_label = read_current_shipper_label(page)

    if after_label:
        print(f"[완료] '{after_label}'(으)로 변경되었습니다.", flush=True)
    else:
        print("[경고] 화주가 아직 '선택하세요' 상태입니다.", flush=True)

    filter_data = load_search_filter() or {}
    filter_data["shipper_label"] = after_label
    save_search_filter(filter_data)
    return after_label


def run_change_session_shipper(config: Dict) -> str:
    """브라우저를 띄워 주문목록에서 화주를 직접 바꾼 뒤 세션을 저장합니다 (단독 실행용)."""
    from playwright.sync_api import sync_playwright

    from Mate2QA_login import create_context, ensure_login_only, load_env_credentials
    from Mate2QA_site_config import STATE_FILE_DOMESTIC

    ui_config = {
        **config,
        "headless": False,
        "slow_mo": config.get("slow_mo", 150),
    }
    creds = load_env_credentials(config.get("login_url"))

    with sync_playwright() as p:
        browser, context = create_context(
            p, ui_config, state_file=STATE_FILE_DOMESTIC
        )
        page = context.new_page()
        try:
            ensure_login_only(
                page,
                context,
                ui_config,
                creds,
                state_file=STATE_FILE_DOMESTIC,
            )
            after_label = change_session_shipper_on_page(page, ui_config)
            context.storage_state(path=str(STATE_FILE_DOMESTIC))
            return after_label
        finally:
            try:
                context.storage_state(path=str(STATE_FILE_DOMESTIC))
            except Exception:
                pass
            context.close()
            browser.close()


def probe_session_shipper_label(config: Dict, *, page=None) -> str:
    """주문목록에 접속해 현재 연결된 화주명을 읽습니다 (런처 표시용).

    page가 주어지면 기존 브라우저 탭을 사용하고, 없으면 headless로 별도 창을 엽니다.
    """
    if page is not None:
        return read_session_shipper_label_on_page(page, config)

    from playwright.sync_api import sync_playwright

    from Mate2QA_login import create_context, ensure_login_only, load_env_credentials
    from Mate2QA_site_config import STATE_FILE_DOMESTIC

    order_list_url = (config.get("order_list_url") or "").strip()
    if not order_list_url:
        return ""

    probe_config = {
        **config,
        "headless": True,
        "slow_mo": 0,
        "start_maximized": False,
    }
    creds = load_env_credentials(config.get("login_url"))

    with sync_playwright() as p:
        browser, context = create_context(
            p, probe_config, state_file=STATE_FILE_DOMESTIC
        )
        probe_page = context.new_page()
        try:
            ensure_login_only(
                probe_page,
                context,
                probe_config,
                creds,
                state_file=STATE_FILE_DOMESTIC,
            )
            return read_session_shipper_label_on_page(probe_page, probe_config)
        finally:
            try:
                context.storage_state(path=str(STATE_FILE_DOMESTIC))
            except Exception:
                pass
            context.close()
            browser.close()
