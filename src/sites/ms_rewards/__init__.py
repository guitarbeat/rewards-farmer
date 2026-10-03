"""Microsoft Rewards / Bing automation (the original bot).

Public site entry used by site_registry: create_runner(driver).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from selenium import webdriver
	from sites.ms_rewards.runner import RewardsTaskUtils

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


def __getattr__(name: str):
	if name in {"AUTOMATION_TASK_STEPS", "BROWSER_STEP", "REQUIRED_SEARCHES"}:
		from sites.ms_rewards import steps as _steps
		return getattr(_steps, name)
	if name == "RewardsTaskUtils":
		from sites.ms_rewards.runner import RewardsTaskUtils
		return RewardsTaskUtils
	raise AttributeError(name)


def create_runner(driver: webdriver.Edge):
	from sites.ms_rewards.runner import RewardsTaskUtils

	return RewardsTaskUtils(driver)
