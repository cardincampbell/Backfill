"""
Abstract adapter interface — every scheduling platform integration implements this.
Adding a new platform = writing a new adapter, not touching the core engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SchedulingAdapter(ABC):

    @abstractmethod
    async def sync_roster(self, restaurant_id: int) -> list[dict]:
        """Return a list of worker dicts from the external platform."""
        ...

    @abstractmethod
    async def sync_schedule(self, restaurant_id: int, date_range: tuple) -> list[dict]:
        """Return a list of shift dicts from the external platform."""
        ...

    @abstractmethod
    async def on_vacancy(self, shift: dict) -> None:
        """Called when a shift becomes vacant — trigger cascade via core engine."""
        ...

    async def push_fill(self, shift: dict, worker: dict) -> None:
        """
        Write a fill confirmation back to the external platform.
        No-op for read-only adapters (Homebase).
        """
        pass  # default: read-only adapters do nothing
