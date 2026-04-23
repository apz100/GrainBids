from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.organization import Organization


router = APIRouter(prefix="/api/alerts", tags=["alerts"])
OPEN_ALERT_STATUSES = {"new", "open", "pending"}
ALERT_STATUSES = OPEN_ALERT_STATUSES | {"acknowledged", "resolved"}


@router.get("/module")
def module_info():
    return {
        "module": "alerts",
        "primary_routes": ["/api/alerts/rules", "/api/alerts/recent"],
    }


@router.get("/rules")
def list_alert_rules(
    org_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    rules = db.execute(
        select(AlertRule).where(AlertRule.org_id == resolved_org).order_by(desc(AlertRule.created_at))
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
                "is_active": rule.is_active,
                "last_triggered_at": last_trigger.isoformat() if last_trigger else None,
                "open_alert_count": int(open_count or 0),
            }
        )
    return {"rows": rows}


@router.get("/recent")
def list_recent_alerts(
    org_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    open_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    query = (
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(AlertRule.org_id == resolved_org)
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
            }
            for alert, rule in rows
        ]
    }


@router.patch("/{alert_id}/status")
def update_alert_status(
    alert_id: uuid.UUID,
    status: str = Query(..., min_length=2, max_length=50),
    org_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    normalized_status = status.strip().lower()
    if normalized_status not in ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    resolved_org = org_id or _default_org_id(db)
    row = db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(Alert.id == alert_id, AlertRule.org_id == resolved_org)
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
    }


@router.post("/{alert_id}/ack")
def acknowledge_alert(
    alert_id: uuid.UUID,
    org_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    return update_alert_status(
        alert_id=alert_id,
        status="acknowledged",
        org_id=org_id,
        db=db,
    )


@router.post("/rules")
def create_alert_rule(
    rule_type: str = Query(..., min_length=2, max_length=50),
    threshold_value: float = Query(...),
    comparison_operator: str = Query(">", pattern="^(>|<|>=|<=|=)$"),
    location: str | None = Query(None),
    org_id: uuid.UUID | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    row = AlertRule(
        org_id=resolved_org,
        commodity_id=commodity_id,
        rule_type=rule_type.strip(),
        threshold_value=threshold_value,
        comparison_operator=comparison_operator,
        location=location.strip() if location else None,
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
    db: Session = Depends(get_db),
):
    row = db.execute(select(AlertRule).where(AlertRule.id == rule_id)).scalar_one_or_none()
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
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "is_active": row.is_active}


@router.delete("/rules/{rule_id}")
def delete_alert_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    row = db.execute(select(AlertRule).where(AlertRule.id == rule_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    db.delete(row)
    db.commit()
    return {"deleted": str(rule_id)}


def _default_org_id(db: Session) -> uuid.UUID:
    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="No organization exists. Create one first.")
    return org.id
