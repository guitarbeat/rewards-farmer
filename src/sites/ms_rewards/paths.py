"""Site-local paths for MS Rewards assets."""

from __future__ import annotations

import os

from constants import REPO_ROOT

REWARDS_HOME_URL = "https://rewards.bing.com/"
VISUAL_SEARCH_IMAGE_PATH = os.path.join(REPO_ROOT, "visual_search.jpg")
VISUAL_SEARCH_STREAK_URL = "https://www.bing.com/?features=vsstreak,vstooltip&form=ML2XES"
