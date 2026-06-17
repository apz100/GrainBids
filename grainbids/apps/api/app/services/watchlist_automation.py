from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert_rule import AlertRule
from app.models.notification_log import NotificationLog
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.saved_search import SavedSearch
from app.models.source import Source
from app.models.watchlist import Watchlist
from app.models.watchlist_automation import WatchlistAutomation
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
)
from app.services.market_search_filters import apply_market_search_filters
from app.services.notification_delivery import send_email_message


WATCHLIST_DIGEST_CHANNEL = "watchlist_digest"
WATCHLIST_ALERT_RULE_TYPE = "saved_search_match"


@dataclass
class WatchlistAutomationSyncResult:
    automation_id: uuid.UUID
    watchlist_id: uuid.UUID
    saved_search_id: uuid.UUID | None
    alert_rule_id: uuid.UUID | None
    is_enabled: bool
    digest_enabled: bool
    alert_promotion_enabled: bool


@dataclass
class WatchlistDigestResult:
    automation_id: uuid.UUID
    watchlist_id: uuid.UUID
    row_count: int
    sent: bool
    status: str
    error_message: str | None


def get_or_create_watchlist_automation(db: Session, *, watchlist: Watchlist) -> WatchlistAutomation:
    automation = db.execute(
        select(WatchlistAutomation).where(
            WatchlistAutomation.watchlist_id == watchlist.id,
            WatchlistAutomation.org_id == watchlist.org_id,
        )
    ).scalar_one_or_none()
    if automation is not None:
        return automation

    automation = WatchlistAutomation(
        org_id=watchlist.org_id,
        watchlist_id=watchlist.id,
        is_enabled=False,
        digest_enabled=True,
        alert_promotion_enabled=True,
    )
    db.add(automation)
    db.flush()
    return automation


def set_watchlist_automation(
    db: Session,
    *,
    watchlist: Watchlist,
    is_enabled: bool,
    digest_enabled: bool,
    alert_promotion_enabled: bool,
) -> WatchlistAutomationSyncResult:
    automation = get_or_create_watchlist_automation(db, watchlist=watchlist)
    automation.is_enabled = is_enabled
    automation.digest_enabled = digest_enabled
    automation.alert_promotion_enabled = alert_promotion_enabled
    _sync_linked_records(db, watchlist=watchlist, automation=automation)
    db.add(automation)
    db.commit()
    db.refresh(automation)
    return _serialize_sync_result(automation)


def sync_watchlist_automation_after_watchlist_update(db: Session, *, watchlist: Watchlist) -> None:
    automation = db.execute(
        select(WatchlistAutomation).where(
            WatchlistAutomation.watchlist_id == watchlist.id,
            WatchlistAutomation.org_id == watchlist.org_id,
        )
    ).scalar_one_or_none()
    if automation is None:
        return
    _sync_linked_records(db, watchlist=watchlist, automation=automation)
    db.add(automation)
    db.commit()


def delete_watchlist_automation(db: Session, *, watchlist: Watchlist) -> None:
    automation = db.execute(
        select(WatchlistAutomation).where(
            WatchlistAutomation.watchlist_id == watchlist.id,
            WatchlistAutomation.org_id == watchlist.org_id,
        )
    ).scalar_one_or_none()
    if automation is None:
        return
    if automation.linked_alert_rule_id is not None:
        alert_rule = db.execute(
            select(AlertRule).where(
                AlertRule.id == automation.linked_alert_rule_id,
                AlertRule.org_id == watchlist.org_id,
            )
        ).scalar_one_or_none()
        if alert_rule is not None:
            db.delete(alert_rule)
    if automation.linked_saved_search_id is not None:
        saved_search = db.execute(
            select(SavedSearch).where(
                SavedSearch.id == automation.linked_saved_search_id,
                SavedSearch.org_id == watchlist.org_id,
            )
        ).scalar_one_or_none()
        if saved_search is not None:
            db.delete(saved_search)
    db.delete(automation)
    db.commit()


def run_watchlist_automation_cycle(db: Session, *, limit: int = 50) -> list[WatchlistDigestResult]:
    automations = db.execute(
        select(WatchlistAutomation)
        .join(Watchlist, Watchlist.id == WatchlistAutomation.watchlist_id)
        .where(
            WatchlistAutomation.is_enabled.is_(True),
            WatchlistAutomation.digest_enabled.is_(True),
            Watchlist.is_active.is_(True),
        )
        .order_by(WatchlistAutomation.updated_at.desc())
    ).scalars().all()
    results: list[WatchlistDigestResult] = []
    for automation in automations:
        watchlist = db.execute(
            select(Watchlist).where(Watchlist.id == automation.watchlist_id, Watchlist.org_id == automation.org_id)
        ).scalar_one_or_none()
        if watchlist is None:
            continue
        results.append(run_watchlist_digest(db, watchlist=watchlist, automation=automation, limit=limit))
    return results


def run_watchlist_digest(
    db: Session,
    *,
    watchlist: Watchlist,
    automation: WatchlistAutomation | None = None,
    limit: int = 50,
) -> WatchlistDigestResult:
    current_automation = automation or get_or_create_watchlist_automation(db, watchlist=watchlist)
    current_automation.last_error_message = None
    rows = load_watchlist_preview_rows(db, watchlist=watchlist, limit=limit)
    current_automation.last_run_at = datetime.now(timezone.utc)
    current_automation.last_digest_row_count = len(rows)

    if not rows:
        db.add(current_automation)
        db.commit()
        db.refresh(current_automation)
        return WatchlistDigestResult(
            automation_id=current_automation.id,
            watchlist_id=watchlist.id,
            row_count=0,
            sent=False,
            status="empty",
            error_message=None,
        )

    if not settings.alert_email_enabled or not settings.alert_email_to or not settings.alert_email_from:
        current_automation.last_error_message = "missing email recipient configuration"
        db.add(current_automation)
        db.add(
            NotificationLog(
                org_id=watchlist.org_id,
                alert_id=None,
                channel=WATCHLIST_DIGEST_CHANNEL,
                recipient=settings.alert_email_to,
                status="skipped",
                error_message=current_automation.last_error_message,
                payload_json={
                    "watchlist_id": str(watchlist.id),
                    "watchlist_name": watchlist.name,
                    "row_count": len(rows),
                },
            )
        )
        db.commit()
        db.refresh(current_automation)
        return WatchlistDigestResult(
            automation_id=current_automation.id,
            watchlist_id=watchlist.id,
            row_count=len(rows),
            sent=False,
            status="skipped",
            error_message=current_automation.last_error_message,
        )

    if not settings.alert_smtp_host:
        current_automation.last_error_message = "missing smtp host"
        db.add(current_automation)
        db.add(
            NotificationLog(
                org_id=watchlist.org_id,
                alert_id=None,
                channel=WATCHLIST_DIGEST_CHANNEL,
                recipient=settings.alert_email_to,
                status="skipped",
                error_message=current_automation.last_error_message,
                payload_json={
                    "watchlist_id": str(watchlist.id),
                    "watchlist_name": watchlist.name,
                    "row_count": len(rows),
                },
            )
        )
        db.commit()
        db.refresh(current_automation)
        return WatchlistDigestResult(
            automation_id=current_automation.id,
            watchlist_id=watchlist.id,
            row_count=len(rows),
            sent=False,
            status="skipped",
            error_message=current_automation.last_error_message,
        )

    subject = f"GrainBids: watchlist digest for {watchlist.name}"
    body_lines = [
        f"Watchlist: {watchlist.name}",
        f"Matching rows: {len(rows)}",
        "",
    ]
    for row in rows:
        body_lines.append(
            " - "
            + " | ".join(
                [
                    row.get("captured_at") or "unknown",
                    row.get("location") or "-",
                    row.get("commodity_name") or "-",
                    row.get("source_name") or "-",
                    row.get("delivery_label") or row.get("futures_month") or "-",
                    f"cash={row.get('cash_price_bu') if row.get('cash_price_bu') is not None else '-'}",
                ]
            )
        )

    try:
        send_email_message(
            subject=subject,
            to=settings.alert_email_to,
            from_address=settings.alert_email_from,
            body="\n".join(body_lines),
        )
        db.add(
            NotificationLog(
                org_id=watchlist.org_id,
                alert_id=None,
                channel=WATCHLIST_DIGEST_CHANNEL,
                recipient=settings.alert_email_to,
                status="sent",
                payload_json={
                    "watchlist_id": str(watchlist.id),
                    "watchlist_name": watchlist.name,
                    "row_count": len(rows),
                    "preview_ids": [row["id"] for row in rows],
                },
            )
        )
        current_automation.last_error_message = None
        db.add(current_automation)
        db.commit()
        db.refresh(current_automation)
        return WatchlistDigestResult(
            automation_id=current_automation.id,
            watchlist_id=watchlist.id,
            row_count=len(rows),
            sent=True,
            status="sent",
            error_message=None,
        )
    except Exception as exc:  # noqa: BLE001
        current_automation.last_error_message = str(exc)
        db.add(
            NotificationLog(
                org_id=watchlist.org_id,
                alert_id=None,
                channel=WATCHLIST_DIGEST_CHANNEL,
                recipient=settings.alert_email_to,
                status="failed",
                error_message=str(exc),
                payload_json={
                    "watchlist_id": str(watchlist.id),
                    "watchlist_name": watchlist.name,
                    "row_count": len(rows),
                },
            )
        )
        db.add(current_automation)
        db.commit()
        db.refresh(current_automation)
        raise


def load_watchlist_preview_rows(
    db: Session,
    *,
    watchlist: Watchlist,
    limit: int = 30,
) -> list[dict]:
    query = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == watchlist.org_id)
    )
    query = apply_market_search_filters(query, filters=watchlist.filters_json or {})
    rows = db.execute(
        query.order_by(desc(PriceSnapshot.captured_at), desc(NormalizedPrice.cash_price_bu)).limit(limit)
    ).all()

    deduped_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    seen: set[str] = set()
    for price, snapshot in rows:
        dedupe_key = "|".join(
            [
                canonical_location_name(price.location) or "-",
                canonical_source_name(price.source_name) or "-",
                canonical_commodity_name(price.commodity_name) or "-",
                normalize_text(price.delivery_label) or normalize_text(price.delivery_end) or "-",
                normalize_text(price.futures_month) or "-",
            ]
        ).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_rows.append((price, snapshot))
        if len(deduped_rows) >= limit:
            break

    return [
        {
            "id": str(price.id),
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "location": canonical_location_name(price.location) or "-",
            "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
            "source_name": canonical_source_name(price.source_name),
            "delivery_label": normalize_text(price.delivery_label) or normalize_text(price.delivery_end),
            "futures_month": normalize_text(price.futures_month),
            "futures_change": _to_float(getattr(price, "futures_change", None)),
            "cash_price_bu": _to_float(price.cash_price_bu),
            "futures_price": _to_float(price.futures_price),
            "basis": _to_float(price.basis),
            "cash_price_mt": _to_float(price.cash_price_mt),
        }
        for price, snapshot in deduped_rows
    ]


def serialize_watchlist_automation(
    db: Session,
    *,
    watchlist: Watchlist,
    limit: int = 10,
) -> dict:
    automation = db.execute(
        select(WatchlistAutomation).where(
            WatchlistAutomation.watchlist_id == watchlist.id,
            WatchlistAutomation.org_id == watchlist.org_id,
        )
    ).scalar_one_or_none()
    saved_search = None
    if automation and automation.linked_saved_search_id is not None:
        saved_search = db.execute(
            select(SavedSearch).where(SavedSearch.id == automation.linked_saved_search_id)
        ).scalar_one_or_none()
    alert_rule = None
    if automation and automation.linked_alert_rule_id is not None:
        alert_rule = db.execute(
            select(AlertRule).where(AlertRule.id == automation.linked_alert_rule_id)
        ).scalar_one_or_none()
    recent_logs = db.execute(
        select(NotificationLog)
        .where(
            NotificationLog.org_id == watchlist.org_id,
            NotificationLog.channel == WATCHLIST_DIGEST_CHANNEL,
            NotificationLog.payload_json["watchlist_id"].astext == str(watchlist.id),
        )
        .order_by(desc(NotificationLog.created_at), desc(NotificationLog.id))
        .limit(limit)
    ).scalars().all()
    return {
        "watchlist": _serialize_watchlist(watchlist),
        "automation": _serialize_automation(automation, watchlist_id=watchlist.id),
        "saved_search": _serialize_saved_search(saved_search),
        "alert_rule": _serialize_alert_rule(alert_rule),
        "recent_notifications": [_serialize_notification_log(row) for row in recent_logs],
        "preview_rows": load_watchlist_preview_rows(db, watchlist=watchlist, limit=30),
    }


def _sync_linked_records(db: Session, *, watchlist: Watchlist, automation: WatchlistAutomation) -> None:
    saved_search = _ensure_saved_search(db, watchlist=watchlist, automation=automation)
    alert_rule = _ensure_alert_rule(db, watchlist=watchlist, automation=automation, saved_search=saved_search)

    saved_search.name = watchlist.name
    saved_search.filters_json = dict(watchlist.filters_json or {})
    saved_search.is_active = automation.is_enabled
    db.add(saved_search)

    if automation.alert_promotion_enabled and automation.is_enabled:
        alert_rule.is_active = True
    else:
        alert_rule.is_active = False
    alert_rule.saved_search_id = saved_search.id
    db.add(alert_rule)

    automation.linked_saved_search_id = saved_search.id
    automation.linked_alert_rule_id = alert_rule.id
    automation.last_error_message = None
    db.add(automation)


def _ensure_saved_search(
    db: Session,
    *,
    watchlist: Watchlist,
    automation: WatchlistAutomation,
) -> SavedSearch:
    saved_search = None
    if automation.linked_saved_search_id is not None:
        saved_search = db.execute(
            select(SavedSearch).where(
                SavedSearch.id == automation.linked_saved_search_id,
                SavedSearch.org_id == watchlist.org_id,
            )
        ).scalar_one_or_none()
    if saved_search is not None:
        return saved_search

    saved_search = SavedSearch(
        org_id=watchlist.org_id,
        name=watchlist.name,
        filters_json=dict(watchlist.filters_json or {}),
        delivery_months_json=None,
        is_active=automation.is_enabled,
    )
    db.add(saved_search)
    db.flush()
    return saved_search


def _ensure_alert_rule(
    db: Session,
    *,
    watchlist: Watchlist,
    automation: WatchlistAutomation,
    saved_search: SavedSearch,
) -> AlertRule:
    alert_rule = None
    if automation.linked_alert_rule_id is not None:
        alert_rule = db.execute(
            select(AlertRule).where(
                AlertRule.id == automation.linked_alert_rule_id,
                AlertRule.org_id == watchlist.org_id,
            )
        ).scalar_one_or_none()
    if alert_rule is not None:
        return alert_rule

    alert_rule = AlertRule(
        org_id=watchlist.org_id,
        saved_search_id=saved_search.id,
        rule_type=WATCHLIST_ALERT_RULE_TYPE,
        threshold_value=1,
        comparison_operator="=",
        delivery_months_json=None,
        location=None,
        is_active=automation.is_enabled and automation.alert_promotion_enabled,
    )
    db.add(alert_rule)
    db.flush()
    return alert_rule


def _serialize_sync_result(automation: WatchlistAutomation) -> WatchlistAutomationSyncResult:
    return WatchlistAutomationSyncResult(
        automation_id=automation.id,
        watchlist_id=automation.watchlist_id,
        saved_search_id=automation.linked_saved_search_id,
        alert_rule_id=automation.linked_alert_rule_id,
        is_enabled=automation.is_enabled,
        digest_enabled=automation.digest_enabled,
        alert_promotion_enabled=automation.alert_promotion_enabled,
    )


def _serialize_automation(automation: WatchlistAutomation | None, *, watchlist_id: uuid.UUID) -> dict:
    if automation is None:
        return {
            "id": None,
            "watchlist_id": str(watchlist_id),
            "is_enabled": False,
            "digest_enabled": False,
            "alert_promotion_enabled": False,
            "linked_saved_search_id": None,
            "linked_alert_rule_id": None,
            "last_run_at": None,
            "last_digest_row_count": None,
            "last_error_message": None,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": str(automation.id),
        "watchlist_id": str(automation.watchlist_id),
        "is_enabled": automation.is_enabled,
        "digest_enabled": automation.digest_enabled,
        "alert_promotion_enabled": automation.alert_promotion_enabled,
        "linked_saved_search_id": str(automation.linked_saved_search_id) if automation.linked_saved_search_id else None,
        "linked_alert_rule_id": str(automation.linked_alert_rule_id) if automation.linked_alert_rule_id else None,
        "last_run_at": automation.last_run_at.isoformat() if automation.last_run_at else None,
        "last_digest_row_count": automation.last_digest_row_count,
        "last_error_message": automation.last_error_message,
        "created_at": automation.created_at.isoformat() if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() if automation.updated_at else None,
    }


def _serialize_watchlist(watchlist: Watchlist) -> dict:
    return {
        "id": str(watchlist.id),
        "org_id": str(watchlist.org_id),
        "name": watchlist.name,
        "filters_json": watchlist.filters_json or {},
        "is_active": watchlist.is_active,
    }


def _serialize_saved_search(saved_search: SavedSearch | None) -> dict | None:
    if saved_search is None:
        return None
    return {
        "id": str(saved_search.id),
        "name": saved_search.name,
        "filters_json": saved_search.filters_json or {},
        "delivery_months": saved_search.delivery_months_json or [],
        "is_active": saved_search.is_active,
    }


def _serialize_alert_rule(alert_rule: AlertRule | None) -> dict | None:
    if alert_rule is None:
        return None
    return {
        "id": str(alert_rule.id),
        "rule_type": alert_rule.rule_type,
        "comparison_operator": alert_rule.comparison_operator,
        "threshold_value": float(alert_rule.threshold_value),
        "saved_search_id": str(alert_rule.saved_search_id) if alert_rule.saved_search_id else None,
        "location": alert_rule.location,
        "delivery_months": alert_rule.delivery_months_json or [],
        "is_active": alert_rule.is_active,
    }


def _serialize_notification_log(row: NotificationLog) -> dict:
    return {
        "id": str(row.id),
        "alert_id": str(row.alert_id) if row.alert_id else None,
        "channel": row.channel,
        "recipient": row.recipient,
        "status": row.status,
        "provider_message_id": row.provider_message_id,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "payload_json": row.payload_json or {},
    }


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number
