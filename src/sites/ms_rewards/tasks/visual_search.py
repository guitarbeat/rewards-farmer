"""Visual search task mixin."""

from __future__ import annotations

import logging
import os
import random
import time

import log_utils
import random_image_for_visual_search
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from sites.ms_rewards.paths import VISUAL_SEARCH_IMAGE_PATH, VISUAL_SEARCH_STREAK_URL

logger = logging.getLogger("rewards_tasks")


def dismiss_cookie_banners(driver) -> bool:
	"""Dismiss cookie consent overlays that block Bing visual search."""
	for selector in (
		"#bnp_btn_accept",
		"#bnp_container button",
		"#bnp_cookie_banner button",
		"#id_acc",
		"#bnp_close_link",
	):
		try:
			for elem in driver.find_elements(By.CSS_SELECTOR, selector):
				try:
					if elem.is_displayed():
						driver.execute_script("arguments[0].click();", elem)
						time.sleep(0.5)
						return True
				except Exception:
					continue
		except Exception:
			continue

	return False


def _on_bing_search(driver) -> bool:
	url = driver.current_url or ""
	return "bing.com" in url and "rewards.bing.com" not in url


class VisualSearchTasks:
	def complete_visual_search(self):
		image_path = random_image_for_visual_search.ensure_visual_search_image(force_refresh=True)
		if not os.path.isfile(image_path) or os.path.getsize(image_path) <= 0:
			raise FileNotFoundError(
				f"visual search image missing at {VISUAL_SEARCH_IMAGE_PATH}"
			)

		self.switch_to_earn_page()
		main_handle = self.driver.current_window_handle
		bing_tab_ready = False

		try:
			try:
				self.wait_for_then_click(self.elements.get_open_visual_search_sidebar, timeout=5)
				self.progress = "opened the sidebar"
				self.wait_for_then_click(
					self.elements.get_search_now_link_from_visual_search_sidebar,
					timeout=5,
				)

				try:
					WebDriverWait(self.driver, 6).until(lambda d: len(d.window_handles) > 1)
					self.tab_utils.switch_to_other_tab()
					bing_tab_ready = True
				except TimeoutException:
					if _on_bing_search(self.driver):
						bing_tab_ready = True
			except Exception as exc:
				logger.info(
					"Could not open visual search from Rewards sidebar (%s). "
					"Falling back to direct Bing visual search URL.",
					log_utils.exception_summary(exc),
				)

			if not bing_tab_ready or not _on_bing_search(self.driver):
				if len(self.driver.window_handles) == 1:
					before = list(self.driver.window_handles)
					self.driver.execute_script(f"window.open('{VISUAL_SEARCH_STREAK_URL}', '_blank');")
					if len(self.driver.window_handles) > len(before):
						self.tab_utils.switch_to_other_tab()
					else:
						self.driver.get(VISUAL_SEARCH_STREAK_URL)
				else:
					self.tab_utils.switch_to_other_tab()
					self.driver.get(VISUAL_SEARCH_STREAK_URL)

			self.progress = "opened the visual search page"
			self.tab_utils.ensure_focus()
			time.sleep(random.uniform(1.5, 2.5))

			dismiss_cookie_banners(self.driver)

			try:
				self.wait_for_then_click(self.elements.get_visual_search_button, timeout=5)
			except Exception:
				pass

			file_input = self.wait_for_element(self.elements.get_visual_search_file_input, timeout=10)
			landing_url = self.driver.current_url
			file_input.send_keys(image_path)
			self.progress = "uploaded the image"

			def left_landing_page(_):
				return (self.driver.current_url or "") != landing_url

			try:
				WebDriverWait(self.driver, 15).until(left_landing_page)
			except TimeoutException:
				logger.warning(
					"Visual search: Bing did not move off %s after upload; image may still have been processed.",
					landing_url,
				)

			time.sleep(random.uniform(3, 5))
		finally:
			try:
				if main_handle in self.driver.window_handles:
					self.driver.switch_to.window(main_handle)
				self.tab_utils.close_all_other_tabs(exceptions=[main_handle])
			except Exception:
				pass
