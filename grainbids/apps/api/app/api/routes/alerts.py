from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.notification_log import NotificationLog
from app.models.saved_search import SavedSearch


class NotificationChannelUpdate(BaseModel):
    notification_channels: list[dict]


router = APIRouter(prefix="/api/alerts", tags=["alerts"])
OPEN_ALERT_STATUSES = {"new", "open", "pending"}
ALERT_STATUSES = OPEN_ALERT_STATUSES | {"acknowledged", "resolved"}


@router.get("/module")
def module_info():
    return {
        "module": "alerts",
        "primary_routes": ["/api/alerts/rules", "/api/alerts/recent", "/api/alerts/notification-logs"],
    }


@router.get("/rules")
def list_alert_rules(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rules = db.execute(
        select(AlertRule).where(AlertRule.org_id == context.org_id).order_by(desc(AlertRule.created_at))
    ).scalars().all()
    rows = []
    for rule in rules:
        last_trigger = db.execute(
            select(func.max(Alert.triggered_at)).where(Alert.alert_rule_id == rule.id)
        ).scalar_one_or_none()
        open_count = db.execute(
            select(func.count(Alert.id)).where(Alert.alert_rule_id == rule.id, Alert.status.in_(OPEN_ALERT_STATUSES))
        ).scalar_one()
        rows.append(
            {
                "id": str(rule.id),
                "rule_type": rule.rule_type,
                "threshold_value": float(rule.threshold_value),
                "comparison_operator": rule.comparison_operator,
                "location": rule.location,
                "saved_search_id": str(rule.saved_search_id) if rule.saved_search_id else None,
                "delivery_months": rule.delivery_months_json or [],
                "notification_channels": rule.notification_channels_json or [],
                "is_active": rule.is_active,
                "last_triggered_at": last_trigger.isoformat() if last_trigger else None,
                "open_alert_count": int(open_count or 0),
            }
        )
    return {"rows": rows}


@router.get("/recent")
def list_recent_alerts(
    limit: int = Query(20, ge=1, le=200),
    open_only: bool = Query(False),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    query = (
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(AlertRule.org_id == context.org_id)
    )
    if open_only:
        query = query.where(Alert.status.in_(OPEN_ALERT_STATUSES))
    rows = db.execute(query.order_by(desc(Alert.triggered_at)).limit(limit)).all()
    return {
        "rows": [
            {
                "id": str(alert.id),
                "alert_rule_id": str(alert.alert_rule_id),
                "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
                "status": alert.status,
                "message": alert.message,
                "rule_type": rule.rule_type,
                "comparison_operator": rule.comparison_operator,
                "threshold_value": float(rule.threshold_value),
                "location": rule.location,
                "saved_search_id": str(rule.saved_search_id) if rule.saved_search_id else None,
                "delivery_months": rule.delivery_months_json or [],
            }
            for alert, rule in rows
        ]
    }


@router.get("/notification-logs")
def list_notification_logs(
    limit: int = Query(50, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(NotificationLog)
        .where(NotificationLog.org_id == context.org_id)
        .order_by(desc(NotificationLog.created_at), desc(NotificationLog.id))
        .limit(limit)
    ).scalars().all()
    return {"rows": [_serialize_notification_log(row) for row in rows]}


@router.patch("/{alert_id}/status")
def update_alert_status(
    alert_id: uuid.UUID,
    status: str = Query(..., min_length=2, max_length=50),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_status = status.strip().lower()
    if normalized_status not in ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    row = db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(Alert.id == alert_id, AlertRule.org_id == context.org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")

    alert, rule = row
    alert.status = normalized_status
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {
        "id": str(alert.id),
        "alert_rule_id": str(alert.alert_rule_id),
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        "status": alert.status,
        "message": alert.message,
        "rule_type": rule.rule_type,
        "comparison_operator": rule.comparison_operator,
        "threshold_value": float(rule.threshold_value),
        "location": rule.location,
        "saved_search_id": str(rule.saved_search_id) if rule.saved_search_id else None,
        "delivery_months": rule.delivery_months_json or [],
    }


@router.post("/{alert_id}/ack")
def acknowledge_alert(
    alert_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_alert_status(
        alert_id=alert_id,
        status="acknowledged",
        context=context,
        db=db,
    )


@router.post("/rules")
def create_alert_rule(
    rule_type: str = Query(..., min_length=2, max_length=50),
    threshold_value: float = Query(...),
    comparison_operator: str = Query(">", pattern="^(>|<|>=|<=|=)$"),
    location: str | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    saved_search_id: uuid.UUID | None = Query(None),
    delivery_months: str | None = Query(None, description="Comma-separated month labels"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    saved_search: SavedSearch | None = None
    if saved_search_id is not None:
        saved_search = db.execute(
            select(SavedSearch).where(SavedSearch.id == saved_search_id, SavedSearch.org_id == context.org_id)
        ).scalar_one_or_none()
        if saved_search is None:
            raise HTTPException(status_code=404, detail="saved search not found")

    month_scope = _parse_delivery_months(delivery_months)
    row = AlertRule(
        org_id=context.org_id,
        commodity_id=commodity_id,
        saved_search_id=saved_search.id if saved_search else None,
        rule_type=rule_type.strip(),
        threshold_value=threshold_value,
        comparison_operator=comparison_operator,
        location=location.strip() if location else None,
        delivery_months_json=month_scope,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}


@router.patch("/rules/{rule_id}")
def update_alert_rule(
    rule_id: uuid.UUID,
    threshold_value: float | None = Query(None),
    comparison_operator: str | None = Query(None, pattern="^(>|<|>=|<=|=)$"),
    is_active: bool | None = Query(None),
    location: str | None = Query(None),
    saved_search_id: uuid.UUID | None = Query(None),
    delivery_months: str | None = Query(None, description="Comma-separated month labels"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    if threshold_value is not None:
        row.threshold_value = threshold_value
    if comparison_operator is not None:
        row.comparison_operator = comparison_operator
    if is_active is not None:
        row.is_active = is_active
    if location is not None:
        row.location = location.strip() or None
    if saved_search_id is not None:
        saved_search = db.execute(
            select(SavedSearch).where(SavedSearch.id == saved_search_id, SavedSearch.org_id == context.org_id)
        ).scalar_one_or_none()
        if saved_search is None:
            raise HTTPException(status_code=404, detail="saved search not found")
        row.saved_search_id = saved_search.id
    if delivery_months is not None:
        row.delivery_months_json = _parse_delivery_months(delivery_months)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "is_active": row.is_active}


@router.patch("/rules/{rule_id}/channels")
def update_alert_rule_channels(
    rule_id: uuid.UUID,
    payload: NotificationChannelUpdate,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    row.notification_channels_json = payload.notification_channels
    db.add(row)
    db.commit()
    return {"id": str(row.id), "notification_channels": row.notification_channels_json or []}


@router.delete("/rules/{rule_id}")
def delete_alert_rule(
    rule_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    db.delete(row)
    db.commit()
    return {"deleted": str(rule_id)}


def _parse_delivery_months(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [chunk.strip() for chunk in raw.split(",")]
    normalized = [value for value in values if value]
    return normalized or None


def _serialize_notification_log(row: NotificationLog) -> dict[str, str | None]:
    return {
        "id": str(row.id),
        "alert_id": str(row.alert_id) if row.alert_id else None,
        "channel": row.channel,
        "recipient": row.recipient,
        "status": row.status,
        "provider_message_id": row.provider_message_id,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
