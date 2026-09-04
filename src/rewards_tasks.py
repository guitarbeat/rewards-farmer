"""Compatibility shim — MS Rewards tasks live in sites.ms_rewards."""

from sites.ms_rewards.runner import RewardsTaskUtils, VISUAL_SEARCH_IMAGE_PATH

__all__ = ["RewardsTaskUtils", "VISUAL_SEARCH_IMAGE_PATH"]
