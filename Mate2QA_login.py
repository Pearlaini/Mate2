# QA OMS — 로그인 전용

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_site_config import (
    CONFIG,
    PROJECT_DIR,
    STATE_FILE_DEFAULT,
    _ENV_PATH,
    _resolve_login_url,
    refresh_config_from_env,
)

STATE_FILE = STATE_FILE_DEFAULT

# 기본 로그인: qa-oms.ourbox.co.kr (ID/PW)
# Ably 전용: qa-style.ourbox.co.kr (AblyID/AblyPW)
_ABLY_LOGIN_HOST = "qa-style.ourbox.co.kr"



def _is_ably_login_url(login_url: str) -> bool:
    """Ably QA 사이트 로그인 URL인지 확인합니다."""
    host = urlparse(login_url.strip().lower()).netloc
    return host == _ABLY_LOGIN_HOST


def load_env_credentials(login_url: Optional[str] = None) -> Dict[str, str]:
    """환경변수에서 로그인 정보를 읽습니다."""
    # env 파일 값이 OS 환경변수·이전 실행 값보다 우선되도록 항상 덮어씁니다.
    load_dotenv(_ENV_PATH, override=True)
    load_dotenv(PROJECT_DIR / "Mate2QA_login.env", override=True)

    # env 파일을 매번 다시 읽어, 노트북·캐시된 CONFIG와 어긋나지 않게 합니다.
    resolved_url = str(login_url or _resolve_login_url()).strip()

    if _is_ably_login_url(resolved_url):
        id_key, pw_key = "AblyID", "AblyPW"
        account_label = "AblyID"
    else:
        id_key, pw_key = "ID", "PW"
        account_label = "ID"

    user_id = os.getenv(id_key, "").strip()
    user_pw = os.getenv(pw_key, "").strip()
    if not user_id or not user_pw:
        raise ValueError(
            f"`Mate2QA_login.env`에 {id_key}, {pw_key}를 설정해 주세요. "
            f"(로그인 URL: {resolved_url})"
        )

    return {"id": user_id, "pw": user_pw, "account_label": account_label}


def _default_page_zoom(config: Dict) -> float:
    return float(config.get("page_zoom", 1.0))


def _popup_page_zoom(config: Dict) -> float:
    return float(config.get("page_zoom_popup", 1.0))


def set_page_zoom(page, zoom: float) -> None:
    """지정한 CSS zoom을 페이지에 적용합니다 (1.0 포함)."""
    try:
        page.evaluate(
            "(z) => { if (document.documentElement) document.documentElement.style.zoom = String(z); }",
            zoom,
        )
    except Exception as exc:
        msg = str(exc)
        if "Execution context was destroyed" in msg:
            return


def _build_page_zoom_init_script(zoom: float) -> str:
    """모든 페이지 로드 시 documentElement에 CSS zoom을 적용하는 init script."""
    return f"""
(() => {{
  const Z = '{zoom}';
  const applyZoom = () => {{
    if (document.documentElement) document.documentElement.style.zoom = Z;
  }};
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', applyZoom, {{ once: true }});
  }} else {{
    applyZoom();
  }}
}})();
"""


@contextmanager
def popup_page_zoom(page, config: Dict) -> Iterator[Callable]:
    """
    주소/모달 팝업 구간만 page_zoom_popup(기본 1.0)을 적용하고, 종료 후 일반 줌으로 복원합니다.
    yield된 register 함수로 새 창 등 추가 페이지에도 동일 줌을 적용할 수 있습니다.
    """
    normal = _default_page_zoom(config)
    popup_z = _popup_page_zoom(config)
    tracked = [page]

    def _apply_all(zoom: float) -> None:
        for p in tracked:
            try:
                if not p.is_closed():
                    set_page_zoom(p, zoom)
            except Exception:
                pass

    def register(page_to_track) -> None:
        if page_to_track not in tracked:
            tracked.append(page_to_track)
        set_page_zoom(page_to_track, popup_z)

    try:
        _apply_all(popup_z)
        yield register
    finally:
        _apply_all(normal)


def apply_page_zoom(page, config: Dict) -> None:
    """현재 페이지에 CSS zoom을 적용합니다 (로그인·화면 이동 후 재적용용)."""
    zoom = _default_page_zoom(config)
    if abs(zoom - 1.0) < 0.001:
        return
    set_page_zoom(page, zoom)


def _attach_page_zoom_handlers(context, config: Dict) -> None:
    """새 탭·페이지마다 load 시 zoom을 다시 적용합니다."""
    zoom = float(config.get("page_zoom", 1.0))
    if abs(zoom - 1.0) < 0.001:
        return

    def _on_page(page) -> None:
        def _on_load() -> None:
            apply_page_zoom(page, config)

        page.on("load", _on_load)

    context.on("page", _on_page)


def create_context(p, config: Dict, *, state_file: Optional[Path] = None):
    """저장된 세션이 있으면 재사용하고, 없으면 새 컨텍스트를 만듭니다."""
    headless = bool(config.get("headless", False))
    launch_kw: Dict = {
        "headless": headless,
        "slow_mo": config.get("slow_mo", 0),
    }
    if config.get("start_maximized", True) and not headless:
        launch_kw["args"] = ["--start-maximized"]

    browser = p.chromium.launch(**launch_kw)

    ctx_kw: Dict = {}
    if config.get("start_maximized", True) and not headless:
        # 실제 모니터 창 크기에 맞춤 (viewport 1920×1080 고정으로 잘리는 현상 방지)
        ctx_kw["no_viewport"] = True
    else:
        vw = int(config.get("viewport_width", 1920))
        vh = int(config.get("viewport_height", 1080))
        ctx_kw["viewport"] = {"width": vw, "height": vh}

    sf = state_file if state_file is not None else STATE_FILE
    if sf.exists():
        ctx_kw["storage_state"] = str(sf)

    context = browser.new_context(**ctx_kw)

    zoom = float(config.get("page_zoom", 1.0))
    if zoom and abs(zoom - 1.0) > 0.001:
        context.add_init_script(_build_page_zoom_init_script(zoom))
        _attach_page_zoom_handlers(context, config)

    return browser, context


def is_login_page(page, login_url: str) -> bool:
    """현재 페이지가 로그인 페이지인지 확인합니다."""
    current = page.url.lower()
    return "login.do" in current


def needs_login(page, login_url: str) -> bool:
    """로그인·세션 만료(오류) 화면이면 다시 로그인해야 합니다."""
    current = page.url.lower()
    if "login.do" in current:
        return True
    # 세션 만료 시 /om/error.do 로 이동하는 경우
    if "error.do" in current:
        return True
    return False


def first_visible_locator(page, candidates):
    """후보 셀렉터 중 화면에 보이는 첫 요소를 찾습니다."""
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            return loc, sel
    return None, None


def _wait_for_login_form(page, id_candidates: list[str], timeout_ms: int = 15_000) -> bool:
    """로그인 ID 입력란 중 하나가 보일 때까지 대기합니다."""
    deadline = timeout_ms
    per_sel = max(2000, timeout_ms // max(len(id_candidates), 1))
    for sel in id_candidates:
        try:
            page.locator(sel).first.wait_for(state="visible", timeout=min(per_sel, deadline))
            return True
        except PlaywrightTimeoutError:
            deadline = max(0, deadline - per_sel)
            if deadline <= 0:
                break
    return False


def do_login(page, config: Dict, creds: Dict[str, str], *, skip_goto: bool = False):
    """로그인을 수행합니다."""
    if not skip_goto:
        page.goto(config["login_url"], wait_until="domcontentloaded")

    page.wait_for_load_state("domcontentloaded")

    sel = config.get("selectors", {})
    id_candidates = [
        sel.get("login_id_input"),
        'input[name="user_id"]',
        'input[id="user_id"]',
        'input[name="loginId"]',
        'input[id="loginId"]',
    ]
    pw_candidates = [
        sel.get("login_pw_input"),
        'input[name="user_pwd"]',
        'input[id="user_pwd"]',
        'input[name="password"]',
        'input[type="password"]',
    ]
    btn_candidates = [
        sel.get("login_button"),
        'button:has-text("로그인")',
        'input[type="submit"]',
    ]
    id_candidates = [s for s in id_candidates if s]
    pw_candidates = [s for s in pw_candidates if s]
    btn_candidates = [s for s in btn_candidates if s]

    if not _wait_for_login_form(page, id_candidates):
        # 세션 만료 등으로 로그인 화면이 늦게 뜨는 경우 한 번 더 시도합니다.
        page.goto(config["login_url"], wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        _wait_for_login_form(page, id_candidates, timeout_ms=20_000)

    id_loc, id_sel = first_visible_locator(page, id_candidates)
    pw_loc, pw_sel = first_visible_locator(page, pw_candidates)
    btn_loc, btn_sel = first_visible_locator(page, btn_candidates)

    if not id_loc or not pw_loc or not btn_loc:
        raise ValueError(
            f"로그인 요소를 찾지 못했습니다. id={id_sel}, pw={pw_sel}, btn={btn_sel}. "
            f"현재 URL: {page.url}. "
            "세션이 꼬였으면 storage_state_domestic.json 삭제 후 다시 실행하거나, "
            "F12로 실제 input/button selector를 확인해 주세요."
        )

    account_label = creds.get("account_label", "ID")
    id_loc.click()
    id_loc.fill("")
    id_loc.fill(creds["id"])
    pw_loc.click()
    pw_loc.fill("")
    pw_loc.fill(creds["pw"])
    btn_loc.click()
    handle_duplicate_login_popup(page)
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")


def handle_duplicate_login_popup(page):
    """중복 로그인 팝업이 뜨면 확인 버튼을 눌러 로그인 진행을 계속합니다."""
    popup = page.locator(".swal2-popup.swal2-show")
    try:
        popup.first.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeoutError:
        return

    title = popup.locator("#swal2-title")
    if title.count() > 0 and "중복 로그인" in title.first.inner_text():
        confirm_btn = popup.locator("button.swal2-confirm.swal2-styled").first
        confirm_btn.click()
        page.wait_for_timeout(800)


def ensure_login_only(
    page,
    context,
    config: Dict,
    creds: Optional[Dict[str, str]] = None,
    *,
    state_file: Optional[Path] = None,
    select_shipper: bool = False,
):
    """로그인 상태만 확인/보장합니다.

    select_shipper=True 이면 로그인 후 화주를 선택합니다.
    메뉴 런처·개별 작업 스크립트는 기본값(False)으로 로그인만 합니다.
    """
    config = refresh_config_from_env(config)
    creds = load_env_credentials(config["login_url"])
    sf = state_file if state_file is not None else STATE_FILE
    page.goto(config["login_url"], wait_until="domcontentloaded")

    if needs_login(page, config["login_url"]):
        on_login = is_login_page(page, config["login_url"])
        do_login(page, config, creds, skip_goto=on_login)
        context.storage_state(path=str(sf))

    apply_page_zoom(page, config)

    if select_shipper:
        from Mate2QA_shipper_select import select_shipper_on_page

        select_shipper_on_page(page, config)
        context.storage_state(path=str(sf))

    return config


def run_login_with_shipper():
    """직접 실행 시: 로그인만 수행합니다."""
    config = refresh_config_from_env(CONFIG)
    creds = load_env_credentials(config["login_url"])
    with sync_playwright() as p:
        browser, context = create_context(p, config)
        page = context.new_page()
        try:
            ensure_login_only(page, context, config, creds, select_shipper=True)
            try:
                input("브라우저를 종료하려면 Enter를 누르세요...")
            except EOFError:
                pass
        except PlaywrightTimeoutError:
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run_login_with_shipper()
