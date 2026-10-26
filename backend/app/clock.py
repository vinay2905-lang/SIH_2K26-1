"""Single source of 'now' so synthetic data can be generated with realistic historical timestamps."""
from datetime import datetime, timezone
from typing import Callable

_override: Callable[[], datetime] | None = None


def now() -> datetime:
    return _override() if _override else datetime.now(timezone.utc)


def set_clock(fn: Callable[[], datetime] | None) -> None:
    global _override
    _override = fn
