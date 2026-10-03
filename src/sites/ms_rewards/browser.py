"""Shared browser interaction helpers for the MS Rewards runner."""

from __future__ import annotations

import logging
import time
from typing import Callable

import log_utils
from selenium import webdriver
from selenium.common.exceptions import (
	NoSuchElementException,
	StaleElementReferenceException,
	TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from sites.ms_rewards.paths import REWARDS_HOME_URL
from sites.ms_rewards.selectors import ElementNotReady

logger = logging.getLogger("rewards_tasks")


class ElementNeverAppeared(TimeoutException):
	"""A wait expired without the element ever being in the page.

	WebDriverWait reports only that the wait ran out, so a section this market
	does not ship and a section that was on screen and slow arrived as the same
	TimeoutException. Reporting both as "not available in this UI variant" was
	wrong for the second one, which is what #52 describes.

	Subclassed from TimeoutException so the handlers that already wait on a
	control being absent, claim_bonus_points and complete_bing_daily_set, keep
	working unchanged.
	"""


class BrowserHelpers:
	"""Click / wait / tab helpers shared by every Rewards task mixin."""

	driver: webdriver.Edge
	mouse: object
	elements: object
	tab_utils: object
	main_window: str

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
		# Keep the last reason the getter gave. Without it a wait that expires
		# cannot say whether the element was missing the whole time or was on
		# the page and not ready, and those are reported differently.
		last_error: BaseException | None = None

		def condition(_: webdriver.Edge):
			nonlocal last_error

			try:
				element_or_elements = element_getter()
			except Exception as exc:
				# Exception rather than a bare except, so Ctrl+C during a
				# getter ends the run instead of being retried away.
				last_error = exc
				return False

			last_error = None
			return element_or_elements

		try:
			return WebDriverWait(self.driver, timeout).until(condition)
		except TimeoutException:
			# A falsy return means the getter found something and rejected it,
			# and ElementNotReady means it was there but still rendering. Only
			# a plain NoSuchElementException every time means it was never
			# there at all.
			never_there = (
				isinstance(last_error, NoSuchElementException)
				and not isinstance(last_error, ElementNotReady)
			)

			if not never_there:
				raise

			raise ElementNeverAppeared(
				f"nothing matched during the {timeout}s wait: {log_utils.exception_summary(last_error)}"
			) from last_error

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

	def restore_main_tab(self):
		"""Close the stray tabs, keeping the one the tasks work in."""
		try:
			handles = self.driver.window_handles
			if not handles:
				return

			keep = self.main_window if self.main_window in handles else handles[0]
			self.tab_utils.close_all_other_tabs(exceptions=[keep])
		except Exception as exc:
			logger.warning(
				"Could not tidy the open tabs: %s", log_utils.exception_summary(exc)
			)

	def return_to_rewards_home(self):
		"""Put the browser back on the Rewards home page after a failed task."""
		try:
			if self.driver.current_url.startswith(REWARDS_HOME_URL):
				return

			self.driver.get(REWARDS_HOME_URL)
			self.tab_utils.ensure_focus()
		except Exception as exc:
			logger.warning(
				"Could not return to the Rewards home page: %s",
				log_utils.exception_summary(exc),
			)
