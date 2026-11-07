from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def utcnow() -> datetime:
    """Naive UTC (all timestamps in the DB are naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), default=str)


def jsonable(x: Any) -> Any:
    return json.loads(canon(x))


def dec(x: Any) -> Decimal:
    return Decimal(str(x if x is not None else 0))


def q2(x: Any) -> Decimal:
    return dec(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
