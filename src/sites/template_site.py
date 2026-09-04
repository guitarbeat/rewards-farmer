"""Starter skeleton for automating a different website.

Copy this file, rename the module, register it in site_registry.py, then fill
in the URLs, selectors, and step functions for your target site. Shared helpers
(tab_utils, mouse_trajectory, mimic_typing, log_utils) work on any page Edge
can open.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import log_utils

if TYPE_CHECKING:
	from selenium import webdriver

SITE_KEY = "template"
SITE_LABEL = "Custom site (template)"

# Change these for your target site.
START_URL = os.environ.get("TEMPLATE_SITE_URL", "https://example.com")
LOGIN_URL_MARKERS = ("login", "signin", "auth")

logger = logging.getLogger(__name__)


class TemplateTaskUtils:
	def __init__(self, driver: webdriver.Edge):
		import mimic_typing
		import mouse_trajectory
		import tab_utils

		self.driver = driver
		self.tab_utils = tab_utils.TabUtils(driver)
		self.mouse = mouse_trajectory.MouseUtils(driver)
		self.keyboard = mimic_typing.KeyboardUtils(driver)

		self.driver.get(START_URL)
		self.tab_utils.ensure_focus()
		self.verify_signed_in_state()

	def verify_signed_in_state(self) -> None:
		url = self.driver.current_url.lower()

		if any(marker in url for marker in LOGIN_URL_MARKERS):
			logger.warning(
				"Looks like %s is not signed in yet. Open this profile in Edge, "
				"sign in once, then run again.",
				START_URL,
			)

	def wait_for_css(self, selector: str, timeout: int = 10):
		return WebDriverWait(self.driver, timeout).until(
			lambda d: d.find_element(By.CSS_SELECTOR, selector)
		)

	def click_css(self, selector: str, timeout: int = 10) -> None:
		element = self.wait_for_css(selector, timeout)
		self.mouse.move_to_element(element)
		self.mouse.human_like_click()

	def example_step(self) -> None:
		"""Replace with real work: navigate, click, type, upload, etc."""
		# Example: wait for a heading, then pause so you can see the page load.
		self.wait_for_css("h1", timeout=15)
		time.sleep(1)
		logger.info("Template step finished on %s", self.driver.current_url)

	def complete_all_tasks(self) -> None:
		steps = (
			("Example step", self.example_step),
		)

		for name, step in steps:
			try:
				step()
				logger.info("[OK] %s", name)
			except (NoSuchElementException, TimeoutException) as exc:
				logger.warning("[SKIP] %s: not available (%s)", name, type(exc).__name__)
			except Exception as exc:
				logger.error(
					"[FAIL] %s: %s: %s",
					name,
					type(exc).__name__,
					log_utils.exception_summary(exc),
					exc_info=logger.isEnabledFor(logging.DEBUG),
				)

			try:
				self.tab_utils.close_all_other_tabs()
			except Exception:
				pass


def create_runner(driver: "webdriver.Edge") -> TemplateTaskUtils:
	return TemplateTaskUtils(driver)
