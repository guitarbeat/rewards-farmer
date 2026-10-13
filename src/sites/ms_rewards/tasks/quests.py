"""Quests (punch cards) task mixin."""

from __future__ import annotations

import logging
import random
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException

logger = logging.getLogger("rewards_tasks")


class QuestTasks:
	def complete_quests(self, max_steps: int = 8):
		"""Work through the punch cards in the quests section.

		Every activity is a plain Bing link, so there is nothing to interpret.
		Cards unlock one step at a time, which is why each card's page is loaded
		again after every activity instead of collecting its links up front.
		"""
		self.switch_to_earn_page()

		quest_urls = []

		for link in self.elements.get_quest_links():
			href = link.get_dom_attribute("href") or ""

			if href.startswith("/"):
				href = "https://rewards.bing.com" + href

			if href and href not in quest_urls:
				quest_urls.append(href)

		if not quest_urls:
			raise NoSuchElementException("no quests in this UI variant")

		logger.info("%s quest(s) found", len(quest_urls))

		self.progress = f"worked through 0 of {len(quest_urls)} quests"

		for number, url in enumerate(quest_urls, start=1):
			self.complete_single_quest(url, max_steps)
			self.progress = f"worked through {number} of {len(quest_urls)} quests"

	def complete_single_quest(self, url: str, max_steps: int) -> int:
		"""Click the unlocked activities of one punch card, returning how many."""
		completed = 0
		clicked = set()

		for _ in range(max_steps):
			self.driver.get(url)
			self.tab_utils.ensure_focus()

			try:
				self.wait_for_element(self.elements.get_quest_activity_links)
			except TimeoutException:
				break

			# Some cards keep an activity clickable after the click, for example
			# one whose punches come from searching on separate days rather than
			# from the link. Without this the loop clicked the same link once
			# per round until max_steps ran out.
			activities = [
				activity for activity in self.elements.get_quest_activity_links()
				if ((activity.text or "").strip(), activity.get_dom_attribute("href") or "") not in clicked
			]

			if not activities:
				break

			activity = activities[0]
			label = (activity.text or "").strip()
			clicked.add((label, activity.get_dom_attribute("href") or ""))

			self.move_to_and_click(activity)
			time.sleep(random.uniform(2, 4))
			self.tab_utils.close_all_other_tabs()

			completed += 1
			logger.info("Quest activity done: %r", label[:40])

			time.sleep(random.uniform(1, 2))

		card = url.rsplit("/", 1)[-1]

		if completed:
			logger.info("%s activity/activities completed on %s", completed, card)
		else:
			logger.info("Nothing left to click on %s", card)

		return completed
