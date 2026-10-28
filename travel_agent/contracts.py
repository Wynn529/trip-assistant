"""Shared contracts between the agent, travel tools, and UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


REQUEST_FIELDS = (
    "city", "start_date", "days", "budget", "adults", "elderly", "children",
    "pace", "rain_days", "preferences", "origin",
)
DEFAULT_ASSUMPTIONS = ("city", "days", "budget", "adults", "elderly", "children", "pace")


@dataclass
class TripRequest:
    city: str = "成都"
    start_date: str = ""
    days: int = 3
    budget: int = 3000
    adults: int = 1
    elderly: int = 1
    children: int = 0
    pace: str = "舒缓"
    rain_days: list[int] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    origin: str = ""
    # Defaults remain compatible with the original demo, but are not confirmations.
    assumed_fields: list[str] = field(default_factory=lambda: list(DEFAULT_ASSUMPTIONS))

    @property
    def travelers(self) -> int:
        return max(1, self.adults + self.elderly + self.children)

    def normalized(self) -> "TripRequest":
        """Return a validated copy, without coercing bad model data or mutating history."""
        result = TripRequest(**self.to_dict())
        for name in ("city", "start_date", "pace", "origin"):
            value = getattr(result, name)
            if not isinstance(value, str) or len(value) > 80:
                raise ValueError(f"{name}: expected a string of at most 80 characters")
            setattr(result, name, value.strip())
        if not result.city or result.pace not in {"舒缓", "适中", "紧凑"}:
            raise ValueError("invalid city or pace")
        for name, lower, upper in (
            ("days", 1, 7), ("budget", 0, 100000), ("adults", 0, 10),
            ("elderly", 0, 10), ("children", 0, 10),
        ):
            value = getattr(result, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name}: expected integer in [{lower}, {upper}]")
        if result.adults + result.elderly + result.children < 1:
            raise ValueError("at least one traveler is required")
        if not isinstance(result.rain_days, list) or any(
            type(day) is not int or not 1 <= day <= 7 for day in result.rain_days
        ):
            raise ValueError("rain_days: expected integer list in [1, 7]")
        result.rain_days = sorted({day for day in result.rain_days if day <= result.days})
        for name in ("preferences", "assumed_fields"):
            values = getattr(result, name)
            if not isinstance(values, list) or len(values) > 30 or any(
                not isinstance(value, str) or not value.strip() or len(value) > 100
                for value in values
            ):
                raise ValueError(f"{name}: invalid string list")
            setattr(result, name, list(dict.fromkeys(value.strip() for value in values)))
        if any(name not in REQUEST_FIELDS for name in result.assumed_fields):
            raise ValueError("unknown assumed field")
        if result.start_date:
            if date.fromisoformat(result.start_date).isoformat() != result.start_date:
                raise ValueError("start_date: expected YYYY-MM-DD")
        return result

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeatherContext:
    status: str
    summary: str
    daily: list[dict[str, Any]] = field(default_factory=list)
    source: str = "Open-Meteo"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    request: TripRequest
    weather: WeatherContext
    itinerary: list[dict[str, Any]]
    budget_items: list[dict[str, Any]]
    total_cost: int
    within_budget: bool
    changes: list[str]
    warnings: list[str]
    booking_tasks: list[dict[str, str]]
    trace: list[dict[str, str]]
    coverage: str
    answer: str
    # Additive fields: old UI/storage constructors remain accepted.
    budget_status: str = "unverified"
    extraction_status: str = ""
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
