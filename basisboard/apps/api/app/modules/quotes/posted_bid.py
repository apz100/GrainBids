from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PostedBidInput:
    location: str
    commodity: str
    posted_price_mt: float
    user: str = ""
    notes: str = ""


def validate_posted_bid(value: PostedBidInput) -> None:
    if not value.location.strip():
        raise ValueError("location is required")
    if not value.commodity.strip():
        raise ValueError("commodity is required")
    if value.posted_price_mt is None:
        raise ValueError("posted_price_mt is required")
