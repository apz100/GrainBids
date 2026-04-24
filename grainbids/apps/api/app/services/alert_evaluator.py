from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source


OPEN_ALERT_STATUSES = ("new", "open", "pending")


@dataclass
class AlertEvaluationResult:
    source_id: uuid.UUID | None
    snapshot_id: uuid.UUID
    evaluated_rules: int
    evaluated_rows: int
    created_alerts: int
    deduped_alerts: int


def evaluate_alert_rules_for_snapshot(
    db: Session,
    *,
    snapshot_id: uuid.UUID,
) -> AlertEvaluationResult:
    snapshot_row = db.execute(
        select(PriceSnapshot, Source)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(PriceSnapshot.id == snapshot_id)
    ).first()

    if snapshot_row is None:
        raise ValueError("snapshot not found")

    snapshot, source = snapshot_row
    rules = db.execute(
        select(AlertRule)
        .where(
            AlertRule.org_id == source.org_id,
            AlertRule.is_active.is_(True),
        )
        .order_by(AlertRule.created_at.asc())
    ).scalars().all()

    rows = db.execute(
        select(NormalizedPrice).where(NormalizedPrice.snapshot_id == snapshot.id)
    ).scalars().all()

    created_alerts = 0
    deduped_alerts = 0
    evaluated_rows = 0

    for rule in rules:
        if rule.commodity_id and rule.commodity_id != snapshot.commodity_id:
            continue

        threshold = _to_decimal(rule.threshold_value)
        if threshold is None:
            continue

        for row in rows:
            if not _location_matches(rule.location, row.location):
                continue

            metric_value = _extract_metric_value(rule.rule_type, row)
            if metric_value is None:
                continue

            evaluated_rows += 1
            if not _compare(metric_value, threshold, rule.comparison_operator):
                continue

            message = _build_alert_message(
                rule=rule,
                row=row,
                metric_value=metric_value,
                threshold=threshold,
            )

            existing = db.execute(
                select(Alert.id).where(
                    and_(
                        Alert.alert_rule_id == rule.id,
                        Alert.message == message,
                        Alert.status.in_(OPEN_ALERT_STATUSES),
                    )
                )
            ).first()
            if existing:
                deduped_alerts += 1
                continue

            db.add(
                Alert(
                    alert_rule_id=rule.id,
                    message=message,
                    status="new",
                )
            )
            created_alerts += 1

    if created_alerts > 0:
        db.commit()

    return AlertEvaluationResult(
        source_id=source.id,
        snapshot_id=snapshot.id,
        evaluated_rules=len(rules),
        evaluated_rows=evaluated_rows,
        created_alerts=created_alerts,
        deduped_alerts=deduped_alerts,
    )


def _extract_metric_value(rule_type: str, row: NormalizedPrice) -> Decimal | None:
    key = rule_type.strip().lower()
    field_map = {
        "basis": row.basis,
        "basis_change": row.basis_change,
        "cash_price_bu": row.cash_price_bu,
        "cash_price_mt": row.cash_price_mt,
        "cash_price_bu_change": row.cash_price_bu_change,
        "cash_price_mt_change": row.cash_price_mt_change,
    }
    return _to_decimal(field_map.get(key))


def _location_matches(rule_location: str | None, row_location: str | None) -> bool:
    if not rule_location:
        return True
    if not row_location:
        return False
    return rule_location.strip().lower() in row_location.strip().lower()


def _to_decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    parsed = Decimal(str(value))
    return parsed if parsed.is_finite() else None


def _compare(value: Decimal, threshold: Decimal, operator: str) -> bool:
    normalized = operator.strip()
    if normalized == ">":
        return value > threshold
    if normalized == "<":
        return value < threshold
    if normalized == ">=":
        return value >= threshold
    if normalized == "<=":
        return value <= threshold
    if normalized == "=":
        return value == threshold
    return False


def _build_alert_message(
    *,
    rule: AlertRule,
    row: NormalizedPrice,
    metric_value: Decimal,
    threshold: Decimal,
) -> str:
    location = row.location
    commodity = row.commodity_name
    delivery = row.delivery_label or "n/a"
    return (
        f"Rule {rule.id} triggered: {rule.rule_type} {rule.comparison_operator} {threshold} "
        f"(actual={metric_value}) at {location} / {commodity} / {delivery}"
    )
