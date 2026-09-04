"""Shared browser interaction helpers for the MS Rewards runner."""

from __future__ import annotations

import logging
import time
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


class BrowserHelpers:
	"""Click / wait / tab helpers shared by every Rewards task mixin."""

	driver: webdriver.Edge
	mouse: object
	elements: object

	def verify_signed_in_state(self):
		try:
			time.sleep(2)
			url = self.driver.current_url.lower()
			if "login.live.com" in url or "account.microsoft.com" in url or "signup" in url:
				logger.warning("Microsoft Rewards is NOT signed in on rewards.bing.com for this profile!")
				logger.warning("Please sign in once on rewards.bing.com in this Edge profile window.")
		except Exception:
			pass

	def find_element(self, xpath: str):
		return self.driver.find_element(By.XPATH, xpath)

	def wait_for_element(
		self,
		element_getter: Callable[[], WebElement | list[WebElement]],
		timeout: int = 10,
	) -> WebElement | list[WebElement]:
		def condition(_: webdriver.Edge):
			try:
				element_or_elements = element_getter()

				return element_or_elements
			except Exception:
				return False

		return WebDriverWait(self.driver, timeout).until(condition)

	def switch_to_earn_page(self):
		self.move_to_and_click(self.elements.get_earn_tab())

	def switch_to_dashboard(self):
		self.move_to_and_click(self.elements.get_dashboard_tab())

	def move_to_and_click(
		self,
		elem_or_getter: WebElement | Callable[[], WebElement],
		retries: int = 3,
	):
		for attempt in range(retries):
			try:
				if callable(elem_or_getter):
					target_elem = elem_or_getter()
				else:
					target_elem = elem_or_getter

				self.mouse.move_to_element(target_elem)
				self.mouse.human_like_click()
				return
			except StaleElementReferenceException as exc:
				if attempt == retries - 1:
					raise exc
				logger.warning(
					"StaleElementReferenceException during click attempt %s/%s, retrying...",
					attempt + 1, retries
				)
				time.sleep(0.5)

	def wait_for_then_click(self, element_getter: Callable[[], WebElement], timeout: int = 10):
		elem = self.wait_for_element(element_getter, timeout)
		self.move_to_and_click(element_getter if callable(element_getter) else elem)
