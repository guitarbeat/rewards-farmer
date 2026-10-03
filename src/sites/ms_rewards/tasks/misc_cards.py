"""Misc card task mixin."""

from __future__ import annotations

import logging
import random
import time

from selenium.webdriver.remote.webelement import WebElement

logger = logging.getLogger("rewards_tasks")


class MiscCardTasks:
	def complete_misc_cards(self):
		self.switch_to_earn_page()
		main_tab = self.driver.current_window_handle

		misc_cards: list[WebElement] = self.wait_for_element(self.elements.get_all_misc_cards)

		opened = 0
		self.progress = "opened 0 cards"

		for index in range(len(misc_cards)):
			cards = self.elements.get_all_misc_cards()
			if index >= len(cards):
				break
			card = cards[index]

			try:
				self.mouse.wheel_scroll_element_into_view(card)

				if not self.elements.card_is_complete(card) and self.elements.get_card_point_value(card) > 0:
					self.move_to_and_click(card)

					opened += 1
					self.progress = f"opened {opened} {'card' if opened == 1 else 'cards'}"

					time.sleep(random.uniform(1, 2))
					self.tab_utils.close_all_other_tabs(exceptions=[main_tab])
			except Exception as exc:
				logger.warning("Misc Card [%d] interaction failed: %s", index, exc)
				continue

		for card in self.elements.get_all_misc_cards():
			if not self.elements.card_is_complete(card) and self.elements.get_card_point_value(card) > 0:
				logger.warning(
					"Misc Card [desc=%r] is not complete after clicking. Please check manually.",
					self.elements.extract_card_descriptions(card)
				)

		self.tab_utils.close_all_other_tabs(exceptions=[main_tab])

		self.mouse.wheel_scroll_to_top()

