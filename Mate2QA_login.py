# QA OMS — 로그인 전용

import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from Mate2QA_site_config import CONFIG

STATE_FILE = Path("storage_state.json")

# 스크립트와 같은 디렉터리의 .env 우선 (실행 cwd가 달라도 동작)
_ENV_PATH = Path(__file__).resolve().parent / "Mate2QA_login.env"


def load_env_credentials() -> Dict[str, str]:
    """환경변수에서 로그인 정보를 읽습니다."""
    load_dotenv(_ENV_PATH)
    load_dotenv("Mate2QA_login.env")

    user_id = os.getenv("ID", "").strip()
    user_pw = os.getenv("PW", "").strip()

    if not user_id or not user_pw:
        raise ValueError("`Mate2QA_login.env`에 ID, PW를 설정해 주세요.")
    return {"id": user_id, "pw": user_pw}


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


def apply_page_zoom(page, config: Dict) -> None:
    """현재 페이지에 CSS zoom을 적용합니다 (로그인·화면 이동 후 재적용용)."""
    zoom = float(config.get("page_zoom", 1.0))
    if abs(zoom - 1.0) < 0.001:
        return
    try:
        page.evaluate(
            "(z) => { if (document.documentElement) document.documentElement.style.zoom = String(z); }",
            zoom,
        )
    except Exception as exc:
        msg = str(exc)
        if "Execution context was destroyed" in msg:
            return
        print(f"[경고] 페이지 줌({zoom}) 재적용 실패: {exc}")


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
        print(f"[안내] 브라우저 페이지 줌 {int(zoom * 100)}% 적용 (CSS zoom).")

    return browser, context


def is_login_page(page, login_url: str) -> bool:
    """현재 페이지가 로그인 페이지인지 확인합니다."""
    current = page.url.lower()
    return "login.do" in current


def first_visible_locator(page, candidates):
    """후보 셀렉터 중 화면에 보이는 첫 요소를 찾습니다."""
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            return loc, sel
    return None, None


def do_login(page, config: Dict, creds: Dict[str, str], *, skip_goto: bool = False):
    """로그인을 수행합니다."""
    if not skip_goto:
        page.goto(config["login_url"], wait_until="domcontentloaded")

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

    id_loc, id_sel = first_visible_locator(page, id_candidates)
    pw_loc, pw_sel = first_visible_locator(page, pw_candidates)
    btn_loc, btn_sel = first_visible_locator(page, btn_candidates)

    if not id_loc or not pw_loc or not btn_loc:
        raise ValueError(
            f"로그인 요소를 찾지 못했습니다. id={id_sel}, pw={pw_sel}, btn={btn_sel}. "
            "F12로 실제 input/button selector를 확인해 주세요."
        )

    id_loc.fill(creds["id"])
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
        print("[안내] 중복 로그인 팝업에서 '확인'을 클릭했습니다.")


def ensure_login_only(
    page, context, config: Dict, creds: Dict[str, str], *, state_file: Optional[Path] = None
):
    """로그인 상태만 확인/보장합니다."""
    sf = state_file if state_file is not None else STATE_FILE
    page.goto(config["login_url"], wait_until="domcontentloaded")

    if is_login_page(page, config["login_url"]):
        print("[안내] 로그인되지 않은 상태입니다. 자동 로그인합니다.")
        do_login(page, config, creds, skip_goto=True)
        context.storage_state(path=str(sf))
        print(f"[안내] 로그인 완료, 세션을 {sf}에 저장했습니다.")
    else:
        print(f"[안내] 이미 로그인되어 있습니다. 현재 URL: {page.url}")

    apply_page_zoom(page, config)


def run_login_with_shipper():
    """직접 실행 시: 로그인만 수행합니다."""
    creds = load_env_credentials()
    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG)
        page = context.new_page()
        try:
            ensure_login_only(page, context, CONFIG, creds)
            try:
                input("브라우저를 종료하려면 Enter를 누르세요...")
            except EOFError:
                print("[안내] 표준 입력이 없거나 닫혀 있어 Enter 대기를 건너뜁니다.")
        except PlaywrightTimeoutError:
            print("[오류] 페이지 로딩이 지연되었습니다. URL/네트워크/selector를 확인해 주세요.")
            raise
        finally:
            context.storage_state(path=str(STATE_FILE))
            context.close()
            browser.close()


if __name__ == "__main__":
    run_login_with_shipper()
