"""Dashboard bonus-points claim."""

from __future__ import annotations

import logging

from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)


class BonusTasks:
	def claim_bonus_points(self):
		self.switch_to_dashboard()

		self.wait_for_then_click(self.elements.get_bonus_button_on_dashboard)

		try:
			self.wait_for_then_click(self.elements.get_claim_bonus_points_button)
		except TimeoutException:
			logger.warning(
				"Could not find the 'Claim Bonus Points' button. "
				"There are likely no bonus points to claim at this time."
			)
