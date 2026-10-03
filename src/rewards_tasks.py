"""Compatibility shim — MS Rewards tasks live in sites.ms_rewards."""

import logging
import time

import queries

from sites.ms_rewards.paths import REWARDS_HOME_URL, VISUAL_SEARCH_IMAGE_PATH
from sites.ms_rewards.runner import (
	ElementNeverAppeared,
	RewardsTaskUtils,
	task_failure_report,
)

logger = logging.getLogger("rewards_tasks")

__all__ = [
	"ElementNeverAppeared",
	"REWARDS_HOME_URL",
	"RewardsTaskUtils",
	"VISUAL_SEARCH_IMAGE_PATH",
	"logger",
	"task_failure_report",
	"time",
	"queries",
]
