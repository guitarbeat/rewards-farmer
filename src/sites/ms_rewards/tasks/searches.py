"""Required Bing search quota."""

from __future__ import annotations

import logging
import random
import time

import queries
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


class SearchTasks:
	def complete_required_searches(self, max_rounds: int = 6):
		# Points per search are not fixed. Some markets award 3 rather than 5,
		# the daily maximum itself changes (observed 15, 30 and 60 on the same
		# account within one day, with the counter resetting), and daily set and
		# card searches count towards the same quota. A single up front division
		# therefore leaves points on the table and still reports success.
		# Measure, search, measure again.
		points_earned, max_pts = self.read_search_points()

		logger.info("Search points before: %s/%s", points_earned, max_pts)

		for round_number in range(1, max_rounds + 1):
			if points_earned >= max_pts:
				break

			# Assume the lower known rate so a round never overshoots by much.
			searches = max(1, (max_pts - points_earned) // 3)

			self.run_search_batch(searches)

			previous = points_earned
			points_earned, max_pts = self.read_search_points()

			logger.info(
				"Round %s: %s searches -> %s/%s",
				round_number, searches, points_earned, max_pts
			)

			if points_earned <= previous:
				logger.warning("Round produced no points, stopping instead of searching pointlessly.")
				break

		if points_earned < max_pts:
			logger.warning("Search quota not filled: %s/%s", points_earned, max_pts)
		else:
			logger.info("Search quota complete: %s/%s", points_earned, max_pts)

	def read_search_points(self):
		"""Open the points breakdown, read the Bing search row, close it again."""
		self.switch_to_earn_page()

		# 30s rather than the default 10s: this runs after the earlier tasks have
		# navigated away, so the earn page re-renders from scratch first and the
		# breakdown button regularly needs longer than 10s to appear. Timing out
		# here skipped the entire search task while points were still available.
		self.wait_for_then_click(self.elements.get_points_breakdown_button, timeout=30)

		# Wait for the search row, not for the panel's close button. The close
		# button is incidental to reading the number, and waiting on it first
		# meant a panel that rendered its content but not its button killed the
		# whole search task while the number was already on screen.
		points_earned, max_pts = self.wait_for_element(
			self.elements.get_points_earned_from_searches_on_points_breakdown,
			timeout=30
		)

		# Closing is best effort, the panel does not block the next navigation.
		try:
			self.move_to_and_click(self.elements.get_generic_sidebar_close_button())
		except Exception:
			pass

		return points_earned, max_pts

	def run_search_batch(self, count: int):
		self.driver.get("https://www.bing.com/")
		self.tab_utils.ensure_focus()

		self.wait_for_element(self.elements.get_bing_search_bar)

		# search bar should be auto-focused

		for i, query in enumerate(
			queries.related_queries(count)
		):
			self.keyboard.send_keys(f"{query} -noai{Keys.ENTER}")

			time.sleep(random.uniform(0.5, 1))

			try:
				self.wait_for_then_click(self.elements.get_clear_bing_search_query_button)
			except StaleElementReferenceException:
				logger.warning(
					"StaleElementReferenceException when trying to click the clear button for query %s. Trying again...",
					i + 1
				)
				self.wait_for_then_click(self.elements.get_clear_bing_search_query_button)

		self.driver.get("https://rewards.bing.com/")
		self.tab_utils.ensure_focus()
