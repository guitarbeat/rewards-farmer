"""Human-like mouse movement: Bezier paths, Fitts timing, Selenium control.

Public API matches the former single-module layout so existing imports keep
working (`import mouse_trajectory`, `from mouse_trajectory import ...`).
"""

from mouse_trajectory.bezier import (
	cubic_bezier,
	cubic_bezier_single_coordinate,
	get_bezier_path,
	get_distorted_bezier_path,
	random_anysign,
)
from mouse_trajectory.constants import (
	DEFAULT_DEVIATION_INTERVAL,
	DEFAULT_DISTORTION_FREQUENCY,
	DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	FITTS_LAW_A,
	FITTS_LAW_B,
	Point,
)
from mouse_trajectory.mouse import MouseUtils
from mouse_trajectory.path import (
	choose_target_in_element,
	get_final_path_from_real_time,
	get_final_path_with_fitts_law,
)
from mouse_trajectory.timing import (
	get_movement_time_from_fitts_law,
	get_path_with_transformed_velo,
	logistic_sigmoid,
)
from selenium.webdriver.common.actions.action_builder import ActionBuilder

__all__ = [
	"Point",
	"DEFAULT_INTERMEDIATE_RADIUS_INTERVAL",
	"DEFAULT_DEVIATION_INTERVAL",
	"DEFAULT_DISTORTION_ZONE_TIME_LENGTH",
	"DEFAULT_DISTORTION_FREQUENCY",
	"FITTS_LAW_A",
	"FITTS_LAW_B",
	"cubic_bezier_single_coordinate",
	"cubic_bezier",
	"random_anysign",
	"get_bezier_path",
	"get_distorted_bezier_path",
	"logistic_sigmoid",
	"get_path_with_transformed_velo",
	"get_final_path_from_real_time",
	"get_movement_time_from_fitts_law",
	"get_final_path_with_fitts_law",
	"choose_target_in_element",
	"MouseUtils",
	"ActionBuilder",
]
