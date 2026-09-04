"""Microsoft Rewards / Bing automation (the original bot).

Public site entry used by site_registry: create_runner(driver).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sites.ms_rewards.runner import RewardsTaskUtils
from sites.ms_rewards.steps import AUTOMATION_TASK_STEPS, BROWSER_STEP, REQUIRED_SEARCHES

if TYPE_CHECKING:
	from selenium import webdriver

SITE_KEY = "ms_rewards"
SITE_LABEL = "MS Rewards (Bing)"

__all__ = [
	"SITE_KEY",
	"SITE_LABEL",
	"AUTOMATION_TASK_STEPS",
	"BROWSER_STEP",
	"REQUIRED_SEARCHES",
	"RewardsTaskUtils",
	"create_runner",
]


def create_runner(driver: webdriver.Edge):
	return RewardsTaskUtils(driver)
