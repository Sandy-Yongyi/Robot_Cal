from __future__ import annotations

from typing import Iterable, Sequence, cast

from model.formats.complete_workpiece.BlockDataFormat import BlockData
from model.utils.LoggerUtil import logger


class CabinetTypeRecognizer:
    """按外框和内部分区的原始绝对坐标识别柜体型号。"""

    def __init__(self, config: dict | None):
        config = config or {}
        matching = config.get("matching", {})
        fallback_tolerance = self._read_tolerance(matching, "tolerance_mm", 50.0)
        self.tolerance_x_mm = self._read_tolerance(matching, "tolerance_x_mm", fallback_tolerance)
        self.tolerance_y_mm = self._read_tolerance(matching, "tolerance_y_mm", fallback_tolerance)
        self.tolerance_z_mm = self._read_tolerance(matching, "tolerance_z_mm", fallback_tolerance)

        profiles = config.get("cabinet_types", [])
        self.profiles = profiles if isinstance(profiles, list) else []

    def recognize(self, block_data: BlockData) -> int:
        """唯一匹配时返回柜号，否则返回 0。"""
        if not isinstance(block_data, BlockData):
            return 0

        outside_bounds = self._outside_bounds(block_data)
        if outside_bounds is None:
            return 0

        inside_bounds = self._inside_bounds(block_data)
        if inside_bounds is None:
            return 0

        matches = []
        for profile in self.profiles:
            try:
                if self._profile_matches(profile, outside_bounds, inside_bounds):
                    matches.append(int(profile["type"]))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(f"Skipping invalid cabinet type profile: {profile}, reason={exc}")

        if len(matches) > 1:
            logger.warning(f"Ambiguous cabinet type match {matches}; using type 0")
        return matches[0] if len(matches) == 1 else 0

    def _profile_matches(
        self,
        profile,
        outside_bounds: tuple[float, float, float, float, float, float],
        inside_bounds: list[tuple[float, float, float, float, float, float]],
    ) -> bool:
        if not isinstance(profile, dict) or not profile.get("enabled", True):
            return False

        cabinet_type = int(profile["type"])
        if cabinet_type <= 0:
            raise ValueError("cabinet type must be greater than zero")

        expected_outside = self._bounds(profile["outside_bounds_mm"])
        if not self._bounds_match(outside_bounds, expected_outside):
            return False

        expected_inside = self._expected_inside_bounds(profile, expected_outside)
        actual_inside = self._sort_bounds(inside_bounds)
        if len(actual_inside) != len(expected_inside):
            return False

        return all(
            self._bounds_match(actual, expected)
            for actual, expected in zip(actual_inside, expected_inside)
        )

    def _expected_inside_bounds(
        self,
        profile: dict,
        expected_outside: tuple[float, float, float, float, float, float],
    ) -> list[tuple[float, float, float, float, float, float]]:
        expected_inside_raw = profile.get("inside_bounds_mm")
        if expected_inside_raw is not None:
            if not isinstance(expected_inside_raw, list):
                raise ValueError("inside_bounds_mm must be a list")
            return self._sort_bounds([self._bounds(item) for item in expected_inside_raw])

        expected_relative_raw = profile.get("inside_relative_bounds_mm", [])
        if not isinstance(expected_relative_raw, list):
            raise ValueError("inside_relative_bounds_mm must be a list")
        return self._sort_bounds(
            [
                self._relative_to_absolute_bounds(self._bounds(item), expected_outside)
                for item in expected_relative_raw
            ]
        )

    def _bounds_match(self, actual: Sequence[float], expected: Sequence[float]) -> bool:
        tolerances = (
            self.tolerance_x_mm,
            self.tolerance_x_mm,
            self.tolerance_y_mm,
            self.tolerance_y_mm,
            self.tolerance_z_mm,
            self.tolerance_z_mm,
        )
        return all(abs(a - e) <= tolerance for a, e, tolerance in zip(actual, expected, tolerances))

    @staticmethod
    def _read_tolerance(matching: dict, key: str, default: float) -> float:
        try:
            tolerance = float(matching.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"Invalid cabinet {key}; using {default} mm")
            return float(default)
        if tolerance < 0:
            logger.warning(f"Negative cabinet {key}; using {default} mm")
            return float(default)
        return tolerance

    @staticmethod
    def _bounds(values: Iterable[float]) -> tuple[float, float, float, float, float, float]:
        bounds = tuple(float(value) for value in values)
        if len(bounds) != 6:
            raise ValueError("bounds must contain x_min, x_max, y_min, y_max, z_min and z_max")
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        if x_min > x_max or y_min > y_max or z_min > z_max:
            raise ValueError("bounds min values must be <= max values")
        return bounds

    @staticmethod
    def _sort_bounds(bounds_list: list[tuple[float, float, float, float, float, float]]):
        return sorted(bounds_list, key=lambda item: (item[4], item[5], item[2], item[3], item[0], item[1]))

    @staticmethod
    def _relative_to_absolute_bounds(
        bounds: tuple[float, float, float, float, float, float],
        outside_bounds: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float]:
        outside_x_min, _, outside_y_min, _, outside_z_min, _ = outside_bounds
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        return (
            x_min + outside_x_min,
            x_max + outside_x_min,
            y_min + outside_y_min,
            y_max + outside_y_min,
            z_min + outside_z_min,
            z_max + outside_z_min,
        )

    @staticmethod
    def _outside_bounds(block_data: BlockData):
        outside_list = block_data.outside_data or []
        if len(outside_list) != 1:
            return None

        outside = outside_list[0]
        bounds = (
            outside.outside_x_min,
            outside.outside_x_max,
            outside.outside_y_min,
            outside.outside_y_max,
            outside.outside_z_min,
            outside.outside_z_max,
        )
        if any(value is None for value in bounds):
            return None

        x_min = cast(int | float, outside.outside_x_min)
        x_max = cast(int | float, outside.outside_x_max)
        y_min = cast(int | float, outside.outside_y_min)
        y_max = cast(int | float, outside.outside_y_max)
        z_min = cast(int | float, outside.outside_z_min)
        z_max = cast(int | float, outside.outside_z_max)
        return (
            float(x_min),
            float(x_max),
            float(y_min),
            float(y_max),
            float(z_min),
            float(z_max),
        )

    @staticmethod
    def _inside_bounds(block_data: BlockData):
        inside_bounds = []
        for inside_column in block_data.inside_data or []:
            for partition in inside_column.subinside_datalist or []:
                bounds = (
                    partition.subinside_x_min,
                    partition.subinside_x_max,
                    partition.subinside_y_min,
                    partition.subinside_y_max,
                    partition.subinside_z_min,
                    partition.subinside_z_max,
                )
                if any(value is None for value in bounds):
                    return None

                x_min = cast(int | float, partition.subinside_x_min)
                x_max = cast(int | float, partition.subinside_x_max)
                y_min = cast(int | float, partition.subinside_y_min)
                y_max = cast(int | float, partition.subinside_y_max)
                z_min = cast(int | float, partition.subinside_z_min)
                z_max = cast(int | float, partition.subinside_z_max)
                inside_bounds.append(
                    (
                        float(x_min),
                        float(x_max),
                        float(y_min),
                        float(y_max),
                        float(z_min),
                        float(z_max),
                    )
                )
        return inside_bounds
