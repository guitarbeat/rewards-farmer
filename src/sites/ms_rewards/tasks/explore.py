"""Explore on Bing task mixin."""

from __future__ import annotations

import logging
import random
import time

import queries
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from sites.ms_rewards.selectors import ElementNotReady

logger = logging.getLogger("rewards_tasks")


class ExploreTasks:
	def _explore_on_bing_cards(self):
		# Asked once first, so an account without the section moves on at once
		# instead of sitting out a wait. Only a section that is there and still
		# rendering gets the wait.
		try:
			return self.elements.get_explore_on_bing_elements()
		except ElementNotReady:
			return self.wait_for_element(self.elements.get_explore_on_bing_elements)

	def complete_explore_on_bing_tasks(self):
		self.switch_to_earn_page()

		explore_on_bing_links = self._explore_on_bing_cards()

		if not explore_on_bing_links:
			# Raise rather than return, so complete_all_tasks reports this as
			# [SKIP]. Returning quietly made it print [OK] for a task that never
			# ran, which is exactly the kind of false success a scheduled run
			# must not produce.
			raise NoSuchElementException("no Explore on Bing section in this UI variant")

		total = len(explore_on_bing_links)
		self.progress = f"searched 0 of {total} cards"

		for number in range(1, total + 1):
			# Read again before every card. Coming back from the search tab
			# re-renders the section, so a reference taken before the first
			# search went stale: "searched 2 of 3 cards, then
			# StaleElementReferenceException" (#102).
			cards = self._explore_on_bing_cards()

			if number > len(cards):
				break

			card = cards[number - 1]
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

			self.progress = f"searched {number} of {total} cards"

		time.sleep(random.uniform(1, 2)) # allow card statuses to update

		for card in self._explore_on_bing_cards():
			if not self.elements.card_is_complete(card):
				logger.warning(
					"Explore on Bing Card [desc=%r] is not complete after searching. Please check manually.",
					self.elements.extract_card_descriptions(card)
				)

