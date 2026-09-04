"""Visual search streak upload."""

from __future__ import annotations

import logging
import os
import random
import time

from sites.ms_rewards.paths import VISUAL_SEARCH_IMAGE_PATH

logger = logging.getLogger(__name__)


class VisualSearchTasks:
	def complete_visual_search(self):
		self.switch_to_earn_page()

		if not os.path.exists(VISUAL_SEARCH_IMAGE_PATH):
			logger.info("visual_search.jpg not found. Generating visual search image...")
			import random_image_for_visual_search
			random_image_for_visual_search.get_random_image()

		self.wait_for_then_click(self.elements.get_open_visual_search_sidebar)

		self.wait_for_then_click(self.elements.get_search_now_link_from_visual_search_sidebar)

		self.tab_utils.switch_to_other_tab()

		self.wait_for_then_click(self.elements.get_visual_search_button)

		file_input = self.wait_for_element(self.elements.get_visual_search_file_input)

		file_input.send_keys(VISUAL_SEARCH_IMAGE_PATH)

		time.sleep(random.uniform(3, 5))

		self.tab_utils.switch_to_other_tab()
		self.tab_utils.close_all_other_tabs()
