"""Pick which site automation backend a run uses.

Set AUTOMATION_SITE to a registered key. Each backend exposes the same
complete_all_tasks() entry point that main.py calls after starting Edge.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
	from selenium import webdriver

ENV_VAR = "AUTOMATION_SITE"
DEFAULT_SITE = "ms_rewards"

SiteFactory = Callable[["webdriver.Edge"], "TaskRunner"]

SITE_LABELS: dict[str, str] = {
	"ms_rewards": "MS Rewards (Bing)",
	"template": "Custom site (template)",
}

SITE_MODULES: dict[str, str] = {
	"ms_rewards": "sites.ms_rewards",
	"template": "sites.template_site",
}


class TaskRunner(Protocol):
	def complete_all_tasks(self) -> None:
		"""Run every step for this site."""


def site_keys() -> list[str]:
	return list(SITE_LABELS.keys())


def site_label(site_key: str) -> str:
	if site_key not in SITE_LABELS:
		raise KeyError(site_key)
	return SITE_LABELS[site_key]


def _factory_for(site_key: str) -> SiteFactory:
	module_name = SITE_MODULES[site_key]
	module = importlib.import_module(module_name)
	return module.create_runner


def resolve(site_key: str | None = None) -> tuple[str, str, SiteFactory]:
	"""Return (key, label, factory) for the requested or default site."""
	key = (site_key or os.environ.get(ENV_VAR) or DEFAULT_SITE).strip().lower()

	if key not in SITE_LABELS:
		known = ", ".join(sorted(SITE_LABELS))
		raise ValueError(f"Unknown {ENV_VAR}={key!r}. Choose one of: {known}")

	return key, site_label(key), _factory_for(key)
