"""Explore on Bing card searches."""

from __future__ import annotations

import logging
import random
import time

import queries
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


class ExploreTasks:
	def complete_explore_on_bing_tasks(self):
		self.switch_to_earn_page()

		explore_on_bing_links = self.elements.get_explore_on_bing_elements()

		if not explore_on_bing_links:
			# Raise rather than return, so complete_all_tasks reports this as
			# [SKIP]. Returning quietly made it print [OK] for a task that never
			# ran, which is exactly the kind of false success a scheduled run
			# must not produce.
			raise NoSuchElementException("no Explore on Bing section in this UI variant")

		for card in explore_on_bing_links:
			desc = self.elements.extract_card_descriptions(card)
			query = queries.search_query_for_task(desc)

			self.move_to_and_click(card)
			self.tab_utils.switch_to_other_tab()

			self.wait_for_element(self.elements.get_bing_search_bar)

			# search bar should be auto-focused

			self.keyboard.send_keys(f"{query} -noai{Keys.ENTER}")

			time.sleep(random.uniform(2, 3))

			self.tab_utils.switch_to_other_tab()
			self.tab_utils.close_all_other_tabs()

		time.sleep(random.uniform(1, 2))  # allow card statuses to update

		for card in explore_on_bing_links:
			if not self.elements.card_is_complete(card):
				logger.warning(
					"Explore on Bing Card [desc=%r] is not complete after searching. Please check manually.",
					self.elements.extract_card_descriptions(card)
				)
