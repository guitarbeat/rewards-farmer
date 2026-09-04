"""Shared types and defaults for human-like mouse paths."""

from __future__ import annotations

Point = tuple[int, int]

DEFAULT_INTERMEDIATE_RADIUS_INTERVAL = (20, 40)
DEFAULT_DEVIATION_INTERVAL = (1, 5)
DEFAULT_DISTORTION_ZONE_TIME_LENGTH = 0.05
DEFAULT_DISTORTION_FREQUENCY = 0.15

FITTS_LAW_A = 0.5500
FITTS_LAW_B = 0.1276
