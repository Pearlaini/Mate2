# QA OMS — 로그인 전용

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import (
    Page,
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

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
# 큐텐-칸닷슈 QA: qa-kdash-om.shopeasy.co.kr (Q10ID/Q10PW)
_ABLY_LOGIN_HOST = "qa-style.ourbox.co.kr"
_Q10_LOGIN_HOST = "qa-kdash-om.shopeasy.co.kr"


def _login_host(login_url: str) -> str:
    """로그인 URL에서 호스트만 추출합니다."""
    return urlparse(login_url.strip().lower()).netloc


def _is_on_page(page, url: str) -> bool:
    """현재 페이지가 지정 URL(경로 기준)과 같은 화면인지 확인합니다."""
    try:
        target_path = urlparse((url or "").strip().lower()).path
        current_path = urlparse((page.url or "").strip().lower()).path
        return bool(target_path) and current_path == target_path
    except Exception:
        return False


def _is_ably_login_url(login_url: str) -> bool:
    """Ably QA 사이트 로그인 URL인지 확인합니다."""
    return _login_host(login_url) == _ABLY_LOGIN_HOST


def _is_q10_login_url(login_url: str) -> bool:
    """큐텐-칸닷슈 QA 사이트 로그인 URL인지 확인합니다."""
    return _login_host(login_url) == _Q10_LOGIN_HOST


def _resolve_credential_keys(login_url: str) -> tuple[str, str, str]:
    """로그인 URL에 맞는 env 키(ID, PW, 표시용 라벨)를 반환합니다."""
    if _is_ably_login_url(login_url):
        return "AblyID", "AblyPW", "AblyID"
    if _is_q10_login_url(login_url):
        return "Q10ID", "Q10PW", "Q10ID"
    return "ID", "PW", "ID"


def _resolve_shipper_env_key(login_url: str) -> str:
    """로그인 URL에 맞는 화주 env 키를 반환합니다."""
    if _is_ably_login_url(login_url):
        return "AblySHIPPER_LABEL"
    if _is_q10_login_url(login_url):
        return "Q10SHIPPER_LABEL"
    return "SHIPPER_LABEL"


def _resolve_sach_cd_env_key(login_url: str) -> str:
    """로그인 URL에 맞는 판매채널 value env 키를 반환합니다."""
    if _is_ably_login_url(login_url):
        return "AblySACH_CD_VALUE"
    if _is_q10_login_url(login_url):
        return "Q10SACH_CD_VALUE"
    return "SACH_CD_VALUE"


def _reload_login_env() -> None:
    """Mate2QA_login.env를 다시 읽습니다."""
    load_dotenv(_ENV_PATH, override=True)


def load_env_shipper_label(login_url: Optional[str] = None) -> str:
    """환경변수에서 사이트별 기본 화주명을 읽습니다. 없으면 빈 문자열."""
    _reload_login_env()
    resolved_url = str(login_url or _resolve_login_url()).strip()
    key = _resolve_shipper_env_key(resolved_url)
    return os.getenv(key, "").strip()


def load_env_sach_cd_value(login_url: Optional[str] = None) -> str:
    """환경변수에서 사이트별 판매채널 option value를 읽습니다. 없으면 빈 문자열."""
    _reload_login_env()
    resolved_url = str(login_url or _resolve_login_url()).strip()
    key = _resolve_sach_cd_env_key(resolved_url)
    return os.getenv(key, "").strip()


def load_env_credentials(login_url: Optional[str] = None) -> Dict[str, str]:
    """환경변수에서 로그인 정보를 읽습니다."""
    # env 파일 값이 OS 환경변수·이전 실행 값보다 우선되도록 항상 덮어씁니다.
    _reload_login_env()

    # env 파일을 매번 다시 읽어, 노트북·캐시된 CONFIG와 어긋나지 않게 합니다.
    resolved_url = str(login_url or _resolve_login_url()).strip()

    id_key, pw_key, account_label = _resolve_credential_keys(resolved_url)

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


def _wait_popup_navigated(popup: Page, timeout_ms: int = 20_000) -> None:
    """about:blank에서 실제 URL로 이동할 때까지 대기합니다."""
    try:
        popup.wait_for_function(
            "() => !['about:blank', ''].includes(window.location.href)",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        pass
    try:
        popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def click_opens_popup_or_same_tab(
    page: Page,
    locator,
    *,
    timeout_ms: int = 20_000,
    register_zoom: Optional[Callable[[Page], None]] = None,
) -> Page:
    """
    클릭 후 새 창이 열리면 팝업 Page를 반환하고, 같은 탭 이동이면 원래 page를 반환합니다.
    OMS가 window.open('about:blank') 후 URL을 넣는 경우 로딩 완료까지 기다립니다.
    """
    pages_before = {id(p) for p in page.context.pages if not p.is_closed()}
    popup: Optional[Page] = None

    try:
        with page.expect_popup(timeout=min(timeout_ms, 8_000)) as popup_info:
            locator.click()
        popup = popup_info.value
    except PlaywrightTimeoutError:
        locator.click()
        page.wait_for_timeout(600)
        new_pages = [
            p
            for p in page.context.pages
            if not p.is_closed() and id(p) not in pages_before
        ]
        if new_pages:
            popup = new_pages[-1]
        else:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(800)
            return page

    if register_zoom is not None:
        register_zoom(popup)
    _wait_popup_navigated(popup, timeout_ms=timeout_ms)
    return popup


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


_AUTOMATION_FINGERPRINT_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


def create_context(p, config: Dict, *, state_file: Optional[Path] = None):
    """저장된 세션이 있으면 재사용하고, 없으면 새 컨텍스트를 만듭니다."""
    headless = bool(config.get("headless", False))
    reduce_fp = bool(config.get("reduce_automation_fingerprint", True))
    channel = (config.get("browser_channel") or "").strip()

    launch_kw: Dict = {
        "headless": headless,
        "slow_mo": config.get("slow_mo", 0),
    }
    launch_args: list[str] = []
    if config.get("start_maximized", True) and not headless:
        launch_args.append("--start-maximized")
    if reduce_fp:
        launch_args.append("--disable-blink-features=AutomationControlled")
    if launch_args:
        launch_kw["args"] = launch_args
    if reduce_fp:
        launch_kw["ignore_default_args"] = ["--enable-automation"]

    browser = None
    if channel:
        try:
            browser = p.chromium.launch(channel=channel, **launch_kw)
        except Exception:
            print(
                f"[경고] '{channel}' 브라우저를 열지 못해 기본 Chromium을 사용합니다.",
                flush=True,
            )
    if browser is None:
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

    if reduce_fp:
        context.add_init_script(_AUTOMATION_FINGERPRINT_INIT_SCRIPT)

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


def session_expired_on_server(page, config: Dict) -> bool:
    """화면 이동 없이 서버 세션 만료 여부를 확인합니다.

    쿠키를 공유하는 API 요청으로 주문목록을 호출해 로그인/오류 페이지로
    리다이렉트되는지 확인합니다 (업무 화면이 떠 있어도 만료를 즉시 감지).
    """
    probe_url = (config.get("order_list_url") or "").strip()
    if not probe_url:
        return False
    try:
        resp = page.request.get(probe_url, timeout=10_000)
        final_url = (resp.url or "").lower()
        return "login.do" in final_url or "error.do" in final_url
    except Exception:
        # 확인 실패 시에는 기존 URL 기반 판정에 맡깁니다
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

    login_url = config["login_url"]
    captcha_present = _detect_human_verification(page)
    if captcha_present:
        if not _wait_for_human_verification(page, login_url):
            raise ValueError(
                "CAPTCHA 확인 시간이 초과되었습니다. "
                "브라우저에서 '사람인지 확인하십시오' 체크 후 다시 실행해 주세요."
            )
        if needs_login(page, login_url):
            print(
                "[알림] CAPTCHA 확인 후 '로그인' 버튼을 직접 눌러 주세요.\n"
                "       로그인 완료되면 자동으로 다음 단계로 진행합니다.",
                flush=True,
            )
            _wait_for_login_navigation(page, login_url)
    else:
        btn_loc.click()

    handle_duplicate_login_popup(page)
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")


_CAPTCHA_DETECT_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[title*='reCAPTCHA' i]",
    ".g-recaptcha",
    "text=사람인지 확인",
)

_CAPTCHA_TOKEN_READY_SCRIPT = """() => {
    const el = document.getElementById('g-recaptcha-response');
    if (!el || !el.value || el.value.length === 0) return false;
    const body = (document.body && document.body.innerText) || '';
    if (body.includes('인증에 실패') || body.toLowerCase().includes('verification failed')) {
        return false;
    }
    return true;
}"""

_CAPTCHA_FAILED_SCRIPT = """() => {
    const body = (document.body && document.body.innerText) || '';
    return body.includes('인증에 실패')
        || body.toLowerCase().includes('verification failed');
}"""


def _detect_human_verification(page) -> bool:
    """로그인 화면에 reCAPTCHA 등 사람 확인 위젯이 있는지 확인합니다."""
    for sel in _CAPTCHA_DETECT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                return True
        except Exception:
            continue
    return False


def _is_captcha_token_ready(page) -> bool:
    """g-recaptcha-response 토큰이 발급됐고 실패 문구가 없는지 확인합니다."""
    try:
        return bool(page.evaluate(_CAPTCHA_TOKEN_READY_SCRIPT))
    except Exception:
        return False


def _is_captcha_failed_visible(page) -> bool:
    """화면에 CAPTCHA 인증 실패 문구가 보이는지 확인합니다."""
    try:
        return bool(page.evaluate(_CAPTCHA_FAILED_SCRIPT))
    except Exception:
        return False


def _wait_for_login_navigation(page, login_url: str, timeout_ms: int = 240_000) -> None:
    """로그인 페이지(login.do)에서 벗어날 때까지 대기합니다 (수동 로그인 완료)."""
    try:
        page.wait_for_function(
            "() => !window.location.href.toLowerCase().includes('login.do')",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            f"{timeout_ms // 1000}초 동안 로그인 완료를 확인하지 못했습니다. "
            "브라우저에서 '로그인' 버튼을 눌렀는지 확인해 주세요."
        ) from exc
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass


def _wait_for_human_verification(
    page,
    login_url: str,
    timeout_ms: int = 240_000,
) -> bool:
    """reCAPTCHA가 있으면 사람이 직접 체크할 때까지 기다립니다.

    자동화가 CAPTCHA를 대신 풀지는 않습니다. 토큰 발급·실패·재시도를 감지하고,
    토큰 없이는 False를 반환해 로그인 버튼 자동 클릭을 막습니다.
    """
    if not _detect_human_verification(page):
        return True

    print(
        "[알림] reCAPTCHA가 감지되었습니다. 브라우저 창에서 "
        "'사람인지 확인하십시오' 체크박스를 직접 클릭해 주세요...",
        flush=True,
    )

    warned_failure = False
    deadline = time.monotonic() + timeout_ms / 1000
    poll_ms = 500

    while time.monotonic() < deadline:

        if not needs_login(page, login_url):
            print("[알림] 로그인 완료를 확인했습니다.", flush=True)
            return True

        if _is_captcha_token_ready(page):
            page.wait_for_timeout(1500)
            if _is_captcha_token_ready(page):
                print("[알림] CAPTCHA 확인 완료. 로그인을 계속 진행합니다.", flush=True)
                return True

        if _is_captcha_failed_visible(page):
            if not warned_failure:
                print(
                    "[경고] CAPTCHA 인증 실패. 체크박스를 다시 눌러 주세요.",
                    flush=True,
                )
                warned_failure = True

        page.wait_for_timeout(poll_ms)

    print(
        f"[경고] {timeout_ms // 1000}초 동안 CAPTCHA 확인이 되지 않았습니다. "
        "로그인을 중단합니다.",
        flush=True,
    )
    return False


def _wait_for_recaptcha_solved(page, timeout_ms: int = 240_000) -> None:
    """하위 호환용 — _wait_for_human_verification 래퍼."""
    _wait_for_human_verification(page, "", timeout_ms=timeout_ms)


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


def apply_env_shipper_after_login(
    page,
    context,
    config: Dict,
    *,
    state_file: Optional[Path] = None,
) -> None:
    """로그인 직후 주문목록에서 env 화주를 적용합니다 (세션 화주가 있으면 유지)."""
    from Mate2QA_shipper_select import PAGE_READY_OM_ORDER_LIST, select_shipper_on_page

    sf = state_file if state_file is not None else STATE_FILE
    env_label = load_env_shipper_label(config.get("login_url"))
    order_list_url = (config.get("order_list_url") or "").strip()
    if not order_list_url:
        return

    # 이미 주문목록 화면이면 다시 이동하지 않습니다 (깜박임 방지)
    if not _is_on_page(page, order_list_url):
        page.goto(order_list_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
    select_shipper_on_page(
        page,
        config,
        page_ready_selectors=PAGE_READY_OM_ORDER_LIST,
        target_label=env_label,
    )
    context.storage_state(path=str(sf))


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

    로그인 확인 후 env에 설정된 화주를 주문목록에서 자동 적용합니다.
    (이미 세션 화주가 선택되어 있으면 그대로 유지, env 미설정·목록 없음이면 '선택하세요' 유지)
    select_shipper 인자는 하위 호환용이며 동작은 항상 env 기준입니다.
    """
    config = refresh_config_from_env(config)
    creds = load_env_credentials(config["login_url"])
    sf = state_file if state_file is not None else STATE_FILE

    # 주문목록으로 바로 이동해 로그인 여부를 확인합니다.
    # (기존: login.do → 메인 리다이렉트 → 주문목록 순 3회 이동 → 화면 깜박임 원인)
    order_list_url = (config.get("order_list_url") or "").strip()
    first_url = order_list_url or config["login_url"]
    page.goto(first_url, wait_until="domcontentloaded")

    if needs_login(page, config["login_url"]):
        on_login = is_login_page(page, config["login_url"])
        do_login(page, config, creds, skip_goto=on_login)
        context.storage_state(path=str(sf))
        if order_list_url and not _is_on_page(page, order_list_url):
            page.goto(order_list_url, wait_until="domcontentloaded")

    apply_page_zoom(page, config)
    apply_env_shipper_after_login(page, context, config, state_file=sf)

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
