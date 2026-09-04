"""Per-task mixins for the MS Rewards runner."""

from sites.ms_rewards.tasks.bonus import BonusTasks
from sites.ms_rewards.tasks.daily_set import DailySetTasks
from sites.ms_rewards.tasks.explore import ExploreTasks
from sites.ms_rewards.tasks.misc_cards import MiscCardTasks
from sites.ms_rewards.tasks.searches import SearchTasks
from sites.ms_rewards.tasks.visual_search import VisualSearchTasks

__all__ = [
	"BonusTasks",
	"DailySetTasks",
	"ExploreTasks",
	"MiscCardTasks",
	"SearchTasks",
	"VisualSearchTasks",
]
