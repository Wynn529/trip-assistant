"""Shared contracts between the agent, travel tools, and UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


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

    @property
    def travelers(self) -> int:
        return max(1, self.adults + self.elderly + self.children)

    def normalized(self) -> "TripRequest":
        self.city = self.city.strip() or "成都"
        self.days = min(7, max(1, int(self.days)))
        self.budget = min(100000, max(100, int(self.budget)))
        self.adults = min(10, max(0, int(self.adults)))
        self.elderly = min(10, max(0, int(self.elderly)))
        self.children = min(10, max(0, int(self.children)))
        self.rain_days = sorted({int(x) for x in self.rain_days if 1 <= int(x) <= self.days})
        if self.start_date:
            date.fromisoformat(self.start_date)
        return self

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
