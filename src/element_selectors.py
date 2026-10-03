"""Compatibility shim — selectors live in sites.ms_rewards.selectors."""

from sites.ms_rewards.selectors import ElementNotReady, ElementSelectionUtils, Labels

__all__ = ["ElementNotReady", "ElementSelectionUtils", "Labels"]
