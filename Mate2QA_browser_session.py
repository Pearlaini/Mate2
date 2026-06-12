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

from Mate2QA_login import (
    apply_page_zoom,
    create_context,
    ensure_login_only,
    load_env_credentials,
    needs_login,
)
from Mate2QA_site_config import (
    CONFIG,
    STATE_FILE_DOMESTIC,
    print_site_url_banner,
    refresh_config_from_env,
)

MSG_CLOSE_BROWSER = "Enter를 누르시면 팝업창이 닫힙니다."
MSG_KEEP_BROWSER = "Enter를 누르세요."
MSG_KEEP_BROWSER_AFTER_SAVE = "저장 후 Enter를 누르세요."
MSG_CLOSE_BROWSER_AFTER_SAVE = "저장 후 Enter를 누르시면 팝업창이 닫힙니다."


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

    def _is_alive(self) -> bool:
        """Chromium·컨텍스트가 아직 사용 가능한지 확인합니다."""
        try:
            if not self.browser or not self.context:
                return False
            return self.browser.is_connected()
        except Exception:
            return False

    def _teardown_browser(self) -> None:
        """브라우저·컨텍스트만 정리합니다 (Playwright 핸들은 유지)."""
        for closer in (self.context, self.browser):
            if closer:
                try:
                    closer.close()
                except Exception:
                    pass
        self.page = None
        self.context = None
        self.browser = None

    def restart_if_needed(self) -> None:
        """연결이 끊기면 브라우저를 다시 열고 로그인합니다."""
        if self._is_alive():
            return

        print("[안내] 브라우저 연결이 끊겨 다시 시작합니다.", flush=True)
        self._teardown_browser()
        if self._p:
            try:
                self._p.stop()
            except Exception:
                pass
            self._p = None

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

    def save_state(self) -> None:
        """현재 쿠키·세션을 파일에 저장합니다."""
        if not self._is_alive() or not self.context:
            return
        try:
            self.context.storage_state(path=str(self.state_file))
        except Exception:
            pass

    def ensure_logged_in(self, config: Optional[Dict] = None) -> Dict:
        """작업 전 로그인·세션 만료 여부를 다시 확인합니다.

        이미 업무 화면에 있으면 login_url로 이동하지 않습니다 (화면이 튕기는 현상 방지).
        """
        self.restart_if_needed()
        if not self.page or not self.context or self.config is None:
            raise RuntimeError("브라우저 세션이 시작되지 않았습니다.")

        merged = refresh_config_from_env(config or self.config)
        creds = load_env_credentials(merged["login_url"])

        if needs_login(self.page, merged["login_url"]):
            merged = ensure_login_only(
                self.page,
                self.context,
                merged,
                creds,
                state_file=self.state_file,
            )
        else:
            apply_page_zoom(self.page, merged)

        self.config = merged
        return merged

    def prepare_for_task(self) -> None:
        """메인 탭 외 추가 탭을 닫아 다음 작업을 준비합니다."""
        self.restart_if_needed()
        if not self.context:
            return

        if self.page is None or self.page.is_closed():
            live_pages = [p for p in self.context.pages if not p.is_closed()]
            if live_pages:
                self.page = live_pages[0]
            else:
                self.page = self.context.new_page()

        main = self.page
        for extra in list(self.context.pages):
            if extra is main or extra.is_closed():
                continue
            try:
                extra.close()
            except Exception:
                pass
        try:
            if not main.is_closed():
                main.bring_to_front()
        except Exception:
            pass

    def close(self) -> None:
        """세션 저장 후 브라우저를 닫습니다."""
        try:
            self.save_state()
        except Exception:
            pass
        self._teardown_browser()
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
