from __future__ import annotations

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .base import DhcpSettings, RouterError


class ArcherC80Driver:
    """Tested against the English TP-Link Archer C80 web interface."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    @staticmethod
    def _login_and_open_dhcp(page: Page, base_url: str, username: str, password: str) -> None:
        page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
        user = page.locator('input[type="text"], input[name*="user" i]').first
        if user.count() and user.is_visible() and username:
            user.fill(username)
        page.locator('input[type="password"]').first.fill(password)
        login = page.locator('#login-btn, button:has-text("Log In"), a:has-text("Log In")').first
        if login.count() and login.is_visible():
            login.click()
        else:
            page.keyboard.press("Enter")
        page.get_by_text("Advanced", exact=True).first.wait_for(timeout=12_000)
        page.get_by_text("Advanced", exact=True).first.click()
        page.get_by_text("Network", exact=True).first.click(timeout=8_000)
        page.get_by_text("DHCP Server", exact=True).first.click(timeout=8_000)
        page.get_by_text("Default Gateway", exact=False).first.wait_for(timeout=10_000)

    @staticmethod
    def _field(page: Page, label: str):
        return page.locator(
            f'xpath=//*[contains(normalize-space(text()), "{label}")]/following::input[1]'
        ).first

    def _session(self, callback):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="msedge", headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                try:
                    self._login_and_open_dhcp(page, self.base_url, self.username, self.password)
                    return callback(page)
                finally:
                    context.close()
                    browser.close()
        except PlaywrightTimeoutError as exc:
            raise RouterError(
                "پنل مودم پاسخ داد، اما صفحه DHCP مورد انتظار پیدا نشد. "
                "مدل، زبان پنل یا firmware احتمالاً پشتیبانی نمی‌شود."
            ) from exc
        except RouterError:
            raise
        except Exception as exc:
            raise RouterError(f"اتصال به مودم ناموفق بود: {exc}") from exc

    def read_dhcp(self) -> DhcpSettings:
        def read(page: Page) -> DhcpSettings:
            return DhcpSettings(
                default_gateway=self._field(page, "Default Gateway").input_value().strip(),
                primary_dns=self._field(page, "Primary DNS").input_value().strip(),
                pool_start=self._field(page, "IP Address Pool").input_value().strip(),
                pool_end=page.locator(
                    'xpath=//*[contains(normalize-space(text()), "IP Address Pool")]/following::input[2]'
                )
                .first.input_value()
                .strip(),
            )

        return self._session(read)

    def apply_dhcp(self, gateway: str, dns: str) -> DhcpSettings:
        def apply(page: Page) -> DhcpSettings:
            for label, value in (("Default Gateway", gateway), ("Primary DNS", dns)):
                field = self._field(page, label)
                field.fill(value)
            buttons = page.locator('a[title="SAVE"], button:has-text("Save"), a:has-text("Save")')
            for index in range(buttons.count()):
                button = buttons.nth(index)
                if button.is_visible():
                    button.click()
                    break
            else:
                raise RouterError("دکمه Save در صفحه DHCP پیدا نشد؛ هیچ تأییدی انجام نشد.")
            page.wait_for_timeout(1500)
            confirm = page.locator('button:has-text("OK"), a:has-text("OK")').first
            if confirm.count() and confirm.is_visible():
                confirm.click()
                page.wait_for_timeout(1200)
            actual = DhcpSettings(
                self._field(page, "Default Gateway").input_value().strip(),
                self._field(page, "Primary DNS").input_value().strip(),
            )
            if actual.default_gateway != gateway or actual.primary_dns != dns:
                raise RouterError(
                    "مودم مقادیر ذخیره‌شده را تأیید نکرد. برای جلوگیری از وضعیت نامشخص، "
                    "تنظیمات پنل را دستی بررسی کنید."
                )
            return actual

        return self._session(apply)
