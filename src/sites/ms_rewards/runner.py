"""MS Rewards / Bing task runner — composes browser helpers and task mixins."""

from __future__ import annotations

import logging

import log_utils
import mimic_typing
import mouse_trajectory
import tab_utils
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from sites.ms_rewards.browser import BrowserHelpers
from sites.ms_rewards.paths import VISUAL_SEARCH_IMAGE_PATH
from sites.ms_rewards.selectors import ElementSelectionUtils
from sites.ms_rewards.steps import AUTOMATION_TASK_STEPS
from sites.ms_rewards.tasks import (
	BonusTasks,
	DailySetTasks,
	ExploreTasks,
	MiscCardTasks,
	SearchTasks,
	VisualSearchTasks,
)

__all__ = ["RewardsTaskUtils", "VISUAL_SEARCH_IMAGE_PATH"]

logger = logging.getLogger(__name__)


class RewardsTaskUtils(
	BrowserHelpers,
	DailySetTasks,
	ExploreTasks,
	VisualSearchTasks,
	MiscCardTasks,
	SearchTasks,
	BonusTasks,
):
	def __init__(self, driver: webdriver.Edge):
		self.driver = driver

		self.driver.get("https://rewards.bing.com/")

		self.tab_utils = tab_utils.TabUtils(driver)
		self.tab_utils.ensure_focus()

		self.mouse = mouse_trajectory.MouseUtils(driver)
		self.keyboard = mimic_typing.KeyboardUtils(driver)
		self.elements = ElementSelectionUtils(driver)
		self.verify_signed_in_state()

	def complete_all_tasks(self):
		# Each task is run independently. The Rewards UI differs by market and
		# changes between deploys, so a task the current variant does not ship
		# must not take the remaining ones down with it.
		step_methods = {
			"Bing daily set": self.complete_bing_daily_set,
			"Explore on Bing": self.complete_explore_on_bing_tasks,
			"Visual search": self.complete_visual_search,
			"Misc cards": self.complete_misc_cards,
			"Required searches": self.complete_required_searches,
			"Bonus points": self.claim_bonus_points,
		}
		steps = tuple((name, step_methods[name]) for name in AUTOMATION_TASK_STEPS)

		for name, step in steps:
			logger.info("[STEP] %s", name)
			# The tags stay in the message rather than being folded into the
			# level, they are the per-task outcome summary and reading a run
			# means scanning for them.
			try:
				step()
				logger.info("[OK] %s", name)
			except (NoSuchElementException, TimeoutException) as exc:
				logger.warning(
					"[SKIP] %s: not available in this UI variant (%s)",
					name, type(exc).__name__,
				)
			except Exception as exc:
				logger.error(
					"[FAIL] %s: %s: %s",
					name, type(exc).__name__, log_utils.exception_summary(exc),
					exc_info=logger.isEnabledFor(logging.DEBUG),
				)

			# Leave a clean tab state behind for the next task.
			try:
				self.tab_utils.close_all_other_tabs()
			except Exception:
				pass
