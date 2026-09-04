"""Bing daily set activities."""

from __future__ import annotations

import logging
import random
import time

from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)


class DailySetTasks:
	def complete_bing_daily_set(self, expected_activities: int = 3):
		self.switch_to_earn_page()

		self.wait_for_then_click(self.elements.get_open_daily_set_button)

		# The panel hydrates progressively, so the first non-empty snapshot can
		# hold fewer than 3 activities. wait_for_element returns on the first
		# truthy result, so a 1-element list satisfied it and indexing [1] and
		# [2] then raised IndexError, taking the whole task down. Wait for the
		# full set instead, and if it never fills, work with what is there.
		def full_activity_list():
			activities = self.elements.get_daily_set_elements()

			return activities if len(activities) >= expected_activities else False

		try:
			daily_set_links = self.wait_for_element(full_activity_list, timeout=30)
		except TimeoutException:
			daily_set_links = self.elements.get_daily_set_elements()

			logger.warning(
				"Daily set panel only shows %s of %s activities",
				len(daily_set_links), expected_activities
			)

		main_tab = self.driver.current_window_handle

		# Re-read the panel per index immediately before interaction: clicking an activity can re-render it and
		# stale the captured references.
		for index in range(len(daily_set_links)):
			def get_activity_elem(idx=index):
				return self.elements.get_daily_set_element_by_index(idx)

			try:
				self.move_to_and_click(get_activity_elem)
			except Exception as exc:
				logger.warning("Failed to click daily set activity %s: %s", index + 1, exc)
				continue

			time.sleep(random.uniform(2, 3))
			self.tab_utils.close_all_other_tabs(exceptions=[main_tab])

		self.tab_utils.close_all_other_tabs(exceptions=[main_tab])
