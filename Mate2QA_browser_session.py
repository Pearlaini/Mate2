# Mate2QA — 메뉴 런처용 브라우저 세션 (한 창에서 작업 연속 실행)

from pathlib import Path
from typing import Callable, Dict, Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from Mate2QA_login import create_context, ensure_login_only, load_env_credentials
from Mate2QA_site_config import (
    CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)

MSG_CLOSE_BROWSER = "Enter를 누르시면 팝업창이 닫힙니다."
MSG_KEEP_BROWSER = "Enter를 누르시면 메뉴로 돌아갑니다. (브라우저는 유지됩니다)"


def wait_enter_after_task(*, keep_browser: bool, message: Optional[str] = None) -> None:
    """작업 완료 후 사용자 확인을 기다립니다."""
    if message is None:
        message = MSG_KEEP_BROWSER if keep_browser else MSG_CLOSE_BROWSER
    try:
        input(message)
    except EOFError:
        pass


def run_with_browser(
    run_task_fn: Callable,
    *,
    config: Dict,
    state_file: Path = STATE_FILE_DOMESTIC,
    creds: Optional[Dict[str, str]] = None,
    print_banner: bool = True,
) -> None:
    """단독 실행: 브라우저를 열고 run_task()를 호출한 뒤 닫습니다."""
    if print_banner:
        print_site_url_banner()
    config = refresh_config_from_env(config)
    if creds is None:
        creds = load_env_credentials(config.get("login_url"))

    with sync_playwright() as p:
        browser, context = create_context(p, config, state_file=state_file)
        page = context.new_page()
        try:
            config = ensure_login_only(
                page, context, config, creds, state_file=state_file
            )
            run_task_fn(page, context, config, keep_browser=False)
        except PlaywrightTimeoutError:
            raise
        finally:
            context.storage_state(path=str(state_file))
            context.close()
            browser.close()


class BrowserSession:
    """메뉴 런처가 유지하는 공유 Chromium 세션입니다."""

    def __init__(self, *, state_file: Path = STATE_FILE_DOMESTIC) -> None:
        self.state_file = state_file
        self._p = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.config: Optional[Dict] = None

    def start(self) -> "BrowserSession":
        """브라우저를 한 번 열고 로그인 상태를 확인합니다."""
        self._p = sync_playwright().start()
        self.config = refresh_config_from_env(CONFIG)
        creds = load_env_credentials(self.config["login_url"])
        self.browser, self.context = create_context(
            self._p, self.config, state_file=self.state_file
        )
        self.page = self.context.new_page()
        self.config = ensure_login_only(
            self.page,
            self.context,
            self.config,
            creds,
            state_file=self.state_file,
        )
        return self

    def save_state(self) -> None:
        """현재 쿠키·세션을 파일에 저장합니다."""
        if self.context:
            self.context.storage_state(path=str(self.state_file))

    def ensure_logged_in(self) -> Dict:
        """작업 전 로그인·세션 만료 여부를 다시 확인합니다."""
        if not self.page or not self.context or self.config is None:
            raise RuntimeError("브라우저 세션이 시작되지 않았습니다.")
        creds = load_env_credentials(self.config["login_url"])
        self.config = ensure_login_only(
            self.page,
            self.context,
            self.config,
            creds,
            state_file=self.state_file,
        )
        return self.config

    def prepare_for_task(self) -> None:
        """메인 탭 외 추가 탭을 닫아 다음 작업을 준비합니다."""
        if not self.context or not self.page:
            return
        main = self.page
        for extra in list(self.context.pages):
            if extra is main or extra.is_closed():
                continue
            try:
                extra.close()
            except Exception:
                pass
        try:
            main.bring_to_front()
        except Exception:
            pass

    def close(self) -> None:
        """세션 저장 후 브라우저를 닫습니다."""
        try:
            self.save_state()
        except Exception:
            pass
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self._p:
            try:
                self._p.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.browser = None
        self._p = None

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
