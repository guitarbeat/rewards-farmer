"""MS Rewards / Bing task runner — composes browser helpers and task mixins."""

from __future__ import annotations

import logging

import log_utils
import mimic_typing
import mouse_trajectory
import tab_utils
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from sites.ms_rewards.browser import BrowserHelpers, ElementNeverAppeared
from sites.ms_rewards.paths import REWARDS_HOME_URL, VISUAL_SEARCH_IMAGE_PATH
from sites.ms_rewards.selectors import ElementNotReady, ElementSelectionUtils
from sites.ms_rewards.steps import AUTOMATION_TASK_STEPS
from sites.ms_rewards.tasks import (
	BonusTasks,
	DailySetTasks,
	ExploreTasks,
	MiscCardTasks,
	SearchTasks,
	VisualSearchTasks,
)

__all__ = [
	"ElementNeverAppeared",
	"RewardsTaskUtils",
	"VISUAL_SEARCH_IMAGE_PATH",
	"task_failure_report",
]

logger = logging.getLogger("rewards_tasks")


def task_failure_report(exc: BaseException, progress: str | None = None) -> tuple[str, str]:
	"""The tag and the reason a failed task is reported with."""
	name = type(exc).__name__

	# Ordered from the most specific case outwards, not by exception hierarchy:
	# ElementNeverAppeared is a TimeoutException and ElementNotReady is a
	# NoSuchElementException, so each has to be tested before the class it
	# refines.
	if isinstance(exc, ElementNeverAppeared):
		cause = None
	elif isinstance(exc, (ElementNotReady, TimeoutException)):
		cause = f"on the page but not ready in time ({name})"
	elif isinstance(exc, NoSuchElementException):
		cause = None
	else:
		cause = f"{name}: {log_utils.exception_summary(exc)}"

	if progress is None:
		if cause is None:
			return "SKIP", f"not available in this UI variant ({name})"
		return "FAIL", cause

	if cause is None:
		cause = f"the next element never appeared ({name})"

	return "FAIL", f"{progress}, then {cause}"


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

		# Set headers to spoof the rewards app for the rewards only quests
		self.driver.execute_cdp_cmd("Network.enable", {})
		headers = {
			"User-Agent": (
				"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
				"(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0 "
				"MSRewards/Desktop/1.1.0"
			),
			"X-Rewards-Source": "msrewards-desktop",
		}
		self.driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": headers})

		self.driver.get(REWARDS_HOME_URL)

		self.tab_utils = tab_utils.TabUtils(driver)
		self.tab_utils.ensure_focus()

		# The tab the tasks work in. Recorded rather than looked up later,
		# because "the current tab" stops meaning this one the moment a task
		# opens a card in a new one.
		self.main_window = driver.current_window_handle

		# How far the running task got, for the report if it stops part way.
		self.progress: str | None = None

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
			completed = False
			self.progress = None

			try:
				step()
				logger.info("[OK] %s", name)
				completed = True
			except Exception as exc:
				tag, reason = task_failure_report(exc, self.progress)
				logger.log(
					logging.WARNING if tag == "SKIP" else logging.ERROR,
					"[%s] %s: %s", tag, name, reason,
					exc_info=logger.isEnabledFor(logging.DEBUG),
				)

			# Leave a clean tab state behind for the next task. Both halves of
			# this matter, and they are separate failures: the right tab has to
			# survive, and it has to be showing the right page.
			self.restore_main_tab()

			if not completed:
				self.return_to_rewards_home()
