"""Required Bing searches task mixin."""

from __future__ import annotations

import logging
import os
import random
import time

import queries
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

from sites.ms_rewards.paths import REWARDS_HOME_URL

logger = logging.getLogger("rewards_tasks")


MOBILE_UA = (
	"Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
	"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"
)


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

		sent = 0
		self.progress = "sent 0 searches"

		# Configurable search burst size to comply with Microsoft 15-minute search cooldown
		burst_limit = int(os.environ.get("SEARCH_BURST_LIMIT", "0"))
		cooldown_delay = float(os.environ.get("SEARCH_COOLDOWN_DELAY_SECONDS", "0"))

		for round_number in range(1, max_rounds + 1):
			if points_earned >= max_pts:
				break

			# Assume the lower known rate so a round never overshoots by much.
			needed = max(1, (max_pts - points_earned) // 3)
			searches = min(needed, burst_limit) if burst_limit > 0 else needed

			batch = self.run_search_batch(searches, already_sent=sent)
			sent += batch

			previous = points_earned
			points_earned, max_pts = self.read_search_points()

			logger.info(
				"Round %s: %s searches -> %s/%s",
				round_number, batch, points_earned, max_pts
			)

			if points_earned <= previous:
				logger.warning("Round produced no points, stopping instead of searching pointlessly.")
				break

			if points_earned < max_pts and cooldown_delay > 0:
				logger.info("[DELAY] %.1f (search cooldown pacing)", cooldown_delay)
				time.sleep(cooldown_delay)

		if points_earned < max_pts:
			logger.warning("Search quota not filled: %s/%s", points_earned, max_pts)
		else:
			logger.info("Search quota complete: %s/%s", points_earned, max_pts)

		# Mobile searches pass if enabled
		if os.environ.get("ENABLE_MOBILE_SEARCH", "").strip().lower() in ("1", "true", "yes"):
			self.run_mobile_searches()

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

	def run_search_batch(self, count: int, already_sent: int = 0) -> int:
		"""Search up to count queries and return how many actually went out.

		The trends source can come back with fewer queries than asked for, so
		the caller cannot assume count.
		"""
		self.driver.get("https://www.bing.com/")
		self.tab_utils.ensure_focus()

		self.wait_for_element(self.elements.get_bing_search_bar)

		# search bar should be auto-focused

		sent_here = 0

		for i, query in enumerate(
			queries.related_queries(count)
		):
			self.keyboard.send_keys(f"{query} -noai{Keys.ENTER}")
			sent_here = i + 1
			sent = already_sent + sent_here
			self.progress = f"sent {sent} {'search' if sent == 1 else 'searches'}"

			time.sleep(random.uniform(5.5, 7.5))

			try: self.wait_for_then_click(self.elements.get_clear_bing_search_query_button)
			except StaleElementReferenceException:
				logger.warning(
					"StaleElementReferenceException when trying to click the clear button for query %s. Trying again...",
					i + 1
				)
				self.wait_for_then_click(self.elements.get_clear_bing_search_query_button)

		self.driver.get(REWARDS_HOME_URL)
		self.tab_utils.ensure_focus()

		return sent_here

	def set_mobile_emulation(self, enabled: bool = True) -> None:
		"""Switch browser emulation between Mobile UA / Viewport and Desktop via CDP."""
		if not hasattr(self.driver, "execute_cdp_cmd"):
			return

		if enabled:
			try:
				self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": MOBILE_UA})
				self.driver.execute_cdp_cmd(
					"Emulation.setDeviceMetricsOverride",
					{
						"width": 390,
						"height": 844,
						"deviceScaleFactor": 3,
						"mobile": True,
					},
				)
				logger.info("Switched to mobile browser emulation (CDP).")
			except Exception as exc:
				logger.warning("Failed to enable mobile CDP emulation: %s", exc)
		else:
			try:
				self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
				self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ""})
				logger.info("Restored desktop browser configuration (CDP).")
			except Exception as exc:
				logger.warning("Failed to restore desktop CDP emulation: %s", exc)

	def read_mobile_search_points(self) -> tuple[int, int]:
		"""Open the points breakdown, read the Mobile search row, close it again."""
		self.switch_to_earn_page()
		self.wait_for_then_click(self.elements.get_points_breakdown_button, timeout=30)
		points_earned, max_pts = self.wait_for_element(
			self.elements.get_mobile_search_points_on_points_breakdown,
			timeout=30,
		)
		try:
			self.move_to_and_click(self.elements.get_generic_sidebar_close_button())
		except Exception:
			pass
		return points_earned, max_pts

	def run_mobile_searches(self, max_rounds: int = 6):
		"""Execute mobile searches under mobile user agent and viewport emulation."""
		logger.info("Starting mobile search emulation pass...")
		self.set_mobile_emulation(True)

		try:
			try:
				points_earned, max_pts = self.read_mobile_search_points()
			except Exception as exc:
				logger.warning("Could not read mobile search points breakdown: %s. Using default target quota.", exc)
				points_earned, max_pts = 0, int(os.environ.get("MOBILE_SEARCH_POINTS", "60"))

			logger.info("Mobile search points before: %s/%s", points_earned, max_pts)
			if points_earned >= max_pts:
				logger.info("Mobile search quota already complete: %s/%s", points_earned, max_pts)
				return

			burst_limit = int(os.environ.get("SEARCH_BURST_LIMIT", "0"))
			cooldown_delay = float(os.environ.get("SEARCH_COOLDOWN_DELAY_SECONDS", "0"))

			sent = 0
			for round_number in range(1, max_rounds + 1):
				if points_earned >= max_pts:
					break

				needed = max(1, (max_pts - points_earned) // 3)
				searches = min(needed, burst_limit) if burst_limit > 0 else needed

				batch = self.run_search_batch(searches, already_sent=sent)
				sent += batch

				previous = points_earned
				try:
					points_earned, max_pts = self.read_mobile_search_points()
				except Exception:
					# Fallback estimation if reading sidebar fails mid-run
					points_earned += batch * 3

				logger.info(
					"Mobile round %s: %s searches -> %s/%s",
					round_number, batch, points_earned, max_pts
				)

				if points_earned <= previous:
					logger.warning("Mobile round produced no points, stopping instead of searching pointlessly.")
					break

				if points_earned < max_pts and cooldown_delay > 0:
					logger.info("[DELAY] %.1f (search cooldown pacing)", cooldown_delay)
					time.sleep(cooldown_delay)

			if points_earned < max_pts:
				logger.warning("Mobile search quota not filled: %s/%s", points_earned, max_pts)
			else:
				logger.info("Mobile search quota complete: %s/%s", points_earned, max_pts)
		finally:
			self.set_mobile_emulation(False)

