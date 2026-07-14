from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.newsletter_subscriber import NewsletterSubscriber


router = APIRouter(prefix="/api/newsletter", tags=["newsletter"])

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class NewsletterSignup(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    first_name: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default="Eastern Ontario", max_length=160)
    audience: Literal["farmer", "grain_business", "ag_professional", "other"] = "farmer"
    signup_source: str = Field(default="homepage", min_length=1, max_length=100)
    consent: Literal[True]
    website: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("first_name", "region")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @field_validator("signup_source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        return value.strip().lower()


class NewsletterSignupResponse(BaseModel):
    status: Literal["subscribed"] = "subscribed"
    message: str = "You're on the GrainBids market report list."


@router.post("/subscribers", response_model=NewsletterSignupResponse, status_code=status.HTTP_201_CREATED)
def create_newsletter_subscriber(
    payload: NewsletterSignup,
    db: Session = Depends(get_db),
) -> NewsletterSignupResponse:
    # A filled hidden field is treated as a bot submission. Return the same response
    # without storing anything so the endpoint does not help bots tune their requests.
    if payload.website:
        return NewsletterSignupResponse()

    existing = db.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == payload.email)
    ).scalar_one_or_none()
    if existing is not None:
        existing.first_name = payload.first_name or existing.first_name
        existing.region = payload.region or existing.region
        existing.audience = payload.audience
        existing.signup_source = payload.signup_source
        existing.consent_version = "market-report-v1"
        existing.status = "active"
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return NewsletterSignupResponse()

    row = NewsletterSubscriber(
        email=payload.email,
        first_name=payload.first_name,
        region=payload.region,
        audience=payload.audience,
        signup_source=payload.signup_source,
        consent_version="market-report-v1",
        status="active",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent duplicate signup is still a successful, idempotent request.
        db.rollback()
    return NewsletterSignupResponse()


def normalize_email(value: str) -> str:
    return value.strip().lower()
