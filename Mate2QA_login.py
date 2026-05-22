# 칸다슈 개발사이트 — 로그인·화주(회사) 선택 전용

import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================
# 사용자 설정 영역
# =========================
CONFIG = {
    "login_url": "https://dev-kdash-oms.shopeasy.co.kr:8443",
    # 화주 전환(pwn_header_change)이 노출되는 화면
    "order_list_url": "https://dev-kdash-oms.shopeasy.co.kr:8443/om/intlOrder/order/orderList.do",
    "headless": False,
    "slow_mo": 150,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "selectors": {
        "login_id_input": 'input[name="loginId"]',
        "login_pw_input": 'input[name="password"]',
        "login_button": 'button:has-text("로그인")',
    },
}

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


def create_context(p, config: Dict, *, state_file: Optional[Path] = None):
    """저장된 세션이 있으면 재사용하고, 없으면 새 컨텍스트를 만듭니다."""
    browser = p.chromium.launch(
        headless=config["headless"],
        slow_mo=config["slow_mo"],
    )

    vw = int(config.get("viewport_width", 1920))
    vh = int(config.get("viewport_height", 1080))
    ctx_kw: Dict = {"viewport": {"width": vw, "height": vh}}

    sf = state_file if state_file is not None else STATE_FILE
    if sf.exists():
        ctx_kw["storage_state"] = str(sf)

    context = browser.new_context(**ctx_kw)

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


def do_login(page, config: Dict, creds: Dict[str, str]):
    """로그인을 수행합니다."""
    page.goto(config["login_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    print(f"[디버그] 현재 URL: {page.url}")
    print(f"[디버그] 페이지 제목: {page.title()}")

    # 칸다슈 dev: user_id / loginId·userId 등 혼재
    id_candidates = [
        'input[name="userId"]',
        'input[id="userId"]',
        'input[name="user_id"]',
        'input[id="user_id"]',
        'input[name="loginId"]',
        'input[id="loginId"]',
    ]
    # 칸다슈: user_pwd / 기타 QA(ourbox 등): password·pw 등
    pw_candidates = [
        'input[name="user_pwd"]',
        'input[id="user_pwd"]',
        'input[name="password"]',
        'input[id="password"]',
        'input[name="pw"]',
        'input[id="pw"]',
        'input[type="password"]',
    ]
    btn_candidates = [
        'button:has-text("로그인")',
        'input[type="submit"]',
        'button[type="submit"]',
        ".btn_login",
    ]

    id_loc, id_sel = first_visible_locator(page, id_candidates)
    pw_loc, pw_sel = first_visible_locator(page, pw_candidates)
    btn_loc, btn_sel = first_visible_locator(page, btn_candidates)

    if not id_loc or not pw_loc or not btn_loc:
        raise ValueError(
            f"로그인 요소를 찾지 못했습니다. id={id_sel}, pw={pw_sel}, btn={btn_sel}. "
            "F12로 실제 input/button selector를 확인해 주세요."
        )

    print(f"[디버그] ID 셀렉터: {id_sel}")
    print(f"[디버그] PW 셀렉터: {pw_sel}")
    print(f"[디버그] BTN 셀렉터: {btn_sel}")

    id_loc.fill(creds["id"])
    pw_loc.fill(creds["pw"])
    btn_loc.click()
    handle_duplicate_login_popup(page)
    # networkidle은 장시간 대기·타임아웃이 나기 쉬워 실패 시 domcontentloaded로 완화
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        print("[안내] networkidle 타임아웃—페이지 표시만 대기 후 계속합니다.")
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
    """주문 페이지 없이 로그인 상태만 확인/보장합니다."""
    sf = state_file if state_file is not None else STATE_FILE
    page.goto(config["login_url"], wait_until="domcontentloaded")

    if is_login_page(page, config["login_url"]):
        print("[안내] 로그인되지 않은 상태입니다. 자동 로그인합니다.")
        do_login(page, config, creds)
        context.storage_state(path=str(sf))
        print(f"[안내] 로그인 완료, 세션을 {sf}에 저장했습니다.")
    else:
        print(f"[안내] 이미 로그인되어 있습니다. 현재 URL: {page.url}")


def select_company_value(page):
    """pwn_header_change에서 '광동생활건강' 값을 선택합니다."""
    selector = 'select[name="pwn_header_change"]'
    target_label = "광동생활건강"

    if page.locator(selector).count() > 0:
        page.select_option(selector, label=target_label)
        print(f"[안내] '{target_label}' 값을 선택했습니다.")
        return

    trigger_candidates = [
        "#pwn_header_change",
        '[name="pwn_header_change"]',
        'button:has-text("선택하세요")',
        'span:has-text("선택하세요")',
    ]
    trigger_loc, _ = first_visible_locator(page, trigger_candidates)
    if trigger_loc:
        trigger_loc.click()
        page.locator(f'text="{target_label}"').first.click()
        print(f"[안내] '{target_label}' 값을 선택했습니다.")
        return

    print(
        "[경고] pwn_header_change 요소를 찾지 못했습니다. "
        "회사가 이미 선택된 환경으로 보고 회사 전환 단계를 건너뜁니다."
    )


def goto_and_select_shipper(page, config: Dict):
    """화주 선택 UI가 있는 페이지로 이동한 뒤 회사(화주)를 선택합니다."""
    page.goto(config["order_list_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"[안내] 화주 선택 화면으로 이동했습니다. 현재 URL: {page.url}")
    select_company_value(page)


def run_login_with_shipper():
    """직접 실행 시: 로그인 보장 후 주문목록으로 이동하여 화주를 선택합니다."""
    creds = load_env_credentials()
    with sync_playwright() as p:
        browser, context = create_context(p, CONFIG)
        page = context.new_page()
        try:
            ensure_login_only(page, context, CONFIG, creds)
            goto_and_select_shipper(page, CONFIG)
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
