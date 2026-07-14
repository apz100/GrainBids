from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
import statistics
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.normalized_prices import _load_preview_payload
from app.core.config import settings
from app.core.request_context import RequestContext
from app.models.market_report_delivery import MarketReportDelivery
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.services.smtp_sender import send_smtp_message


REPORT_COMMODITIES = ("Corn", "Soybeans", "Wheat")


@dataclass(frozen=True)
class MarketReport:
    issue_key: str
    subject: str
    region: str
    generated_at: datetime
    data_as_of: datetime | None
    sections: tuple[dict[str, object], ...]
    text: str
    html: str

    def as_dict(self) -> dict[str, object]:
        serialized_sections = [
            {
                **section,
                "data_as_of": section["data_as_of"].isoformat() if section["data_as_of"] else None,
            }
            for section in self.sections
        ]
        return {
            "issue_key": self.issue_key,
            "subject": self.subject,
            "region": self.region,
            "generated_at": self.generated_at.isoformat(),
            "data_as_of": self.data_as_of.isoformat() if self.data_as_of else None,
            "sections": serialized_sections,
            "text": self.text,
            "html": self.html,
        }


@dataclass(frozen=True)
class DeliverySummary:
    issue_key: str
    targeted: int
    sent: int
    skipped: int
    failed: int
    dry_run: bool


def build_market_report(
    db: Session,
    *,
    org_id: uuid.UUID,
    generated_at: datetime | None = None,
    region: str | None = None,
) -> MarketReport:
    generated_at = generated_at or datetime.now(timezone.utc)
    region = (region or settings.market_report_region).strip() or "Eastern Ontario"
    context = RequestContext(org_id=org_id, user_email=None, user_role="admin")
    rows_by_commodity = {
        commodity: _load_preview_payload(
            context=context,
            db=db,
            commodity=commodity,
            location=None,
            source_name=None,
            region=region,
            company_id=None,
            location_id=None,
            captured_date=None,
            include_non_canonical=False,
            sort="cash_bu_desc",
            limit=500,
        )
        for commodity in REPORT_COMMODITIES
    }
    return compile_market_report(rows_by_commodity, generated_at=generated_at, region=region)


def compile_market_report(
    rows_by_commodity: dict[str, list[dict[str, object]]],
    *,
    generated_at: datetime,
    region: str,
) -> MarketReport:
    sections = tuple(
        _compile_section(commodity, rows_by_commodity.get(commodity, []))
        for commodity in REPORT_COMMODITIES
    )
    captured_values = [
        value
        for section in sections
        if (value := section["data_as_of"]) is not None
    ]
    data_as_of = max(captured_values) if captured_values else None
    iso_year, iso_week, _ = generated_at.isocalendar()
    issue_key = f"{iso_year}-W{iso_week:02d}"
    subject = f"GrainBids {region} Market Report — {generated_at:%B} {generated_at.day}, {generated_at:%Y}"
    text = _render_text(subject, sections, data_as_of)
    html = _render_html(subject, sections, data_as_of)
    return MarketReport(
        issue_key=issue_key,
        subject=subject,
        region=region,
        generated_at=generated_at,
        data_as_of=data_as_of,
        sections=sections,
        text=text,
        html=html,
    )


def deliver_market_report(
    db: Session,
    *,
    org_id: uuid.UUID,
    report: MarketReport,
    send: bool = False,
    retry_failed: bool = False,
) -> DeliverySummary:
    subscribers = db.execute(
        select(NewsletterSubscriber)
        .where(NewsletterSubscriber.status == "active")
        .order_by(NewsletterSubscriber.created_at.asc(), NewsletterSubscriber.email.asc())
    ).scalars().all()
    if not send:
        return DeliverySummary(report.issue_key, len(subscribers), 0, 0, 0, True)

    _validate_delivery_config()
    sent = 0
    skipped = 0
    failed = 0
    for subscriber in subscribers:
        existing = db.execute(
            select(MarketReportDelivery).where(
                MarketReportDelivery.subscriber_id == subscriber.id,
                MarketReportDelivery.issue_key == report.issue_key,
            )
        ).scalar_one_or_none()
        if existing is not None and (existing.status != "failed" or not retry_failed):
            skipped += 1
            continue

        if subscriber.unsubscribe_token is None:
            subscriber.unsubscribe_token = uuid.uuid4()
            db.commit()

        delivery = existing or MarketReportDelivery(
            org_id=org_id,
            subscriber_id=subscriber.id,
            issue_key=report.issue_key,
            subject=report.subject,
            status="pending",
        )
        delivery.status = "pending"
        delivery.error_message = None
        if existing is None:
            db.add(delivery)
        db.commit()

        try:
            send_smtp_message(_build_message(report, subscriber))
            delivery.status = "sent"
            delivery.sent_at = datetime.now(timezone.utc)
            sent += 1
        except Exception as exc:
            delivery.status = "failed"
            delivery.error_message = str(exc)[:2000]
            failed += 1
        db.commit()

    return DeliverySummary(report.issue_key, len(subscribers), sent, skipped, failed, False)


def _compile_section(commodity: str, rows: list[dict[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if _as_number(row.get("cash_price_bu")) is not None]
    usable.sort(key=lambda row: _as_number(row.get("cash_price_bu")) or float("-inf"), reverse=True)
    cash_values = [_as_number(row.get("cash_price_bu")) for row in usable]
    basis_values = [value for row in usable if (value := _as_number(row.get("basis"))) is not None]
    captured_values = [
        parsed for row in usable if (parsed := _parse_datetime(row.get("captured_at"))) is not None
    ]
    top_bids = [dict(row) for row in usable[:3]]
    return {
        "commodity": commodity,
        "market_count": len(usable),
        "top_bids": top_bids,
        "median_cash_price_bu": statistics.median(cash_values) if cash_values else None,
        "cash_spread_bu": (max(cash_values) - min(cash_values)) if len(cash_values) > 1 else None,
        "average_basis": statistics.mean(basis_values) if basis_values else None,
        "data_as_of": max(captured_values) if captured_values else None,
    }


def _render_text(subject: str, sections: tuple[dict[str, object], ...], data_as_of: datetime | None) -> str:
    lines = [subject, "", f"Data as of: {_format_as_of(data_as_of)}", ""]
    for section in sections:
        lines.extend([str(section["commodity"]), "-"])
        top_bids = section["top_bids"]
        if not top_bids:
            lines.append("No current canonical bids were available.")
        else:
            for row in top_bids:
                lines.append(
                    f"• {_row_label(row)} — {_format_cash(row.get('cash_price_bu'))}; "
                    f"basis {_format_basis(row.get('basis'))}; {_market_period_label(row)}"
                )
            lines.append(
                f"Listed markets: {section['market_count']}; cash median across listed delivery periods: "
                f"{_format_cash(section['median_cash_price_bu'])}; listed range: "
                f"{_format_cash(section['cash_spread_bu'])} before freight."
            )
        lines.append("")
    lines.extend(
        [
            f"View current bids: {settings.market_report_public_url.rstrip('/')}",
            "",
            "Posted-bid snapshot only, not a delivered-netback recommendation. Freight is not included. "
            "Verify prices, grades, delivery periods, futures contracts, and freight before making a sale.",
        ]
    )
    return "\n".join(lines)


def _render_html(subject: str, sections: tuple[dict[str, object], ...], data_as_of: datetime | None) -> str:
    section_html: list[str] = []
    for section in sections:
        rows = section["top_bids"]
        if rows:
            body = "".join(
                "<tr>"
                f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{escape(_row_label(row))}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{escape(_market_period_label(row))}</td>"
                "<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right'>"
                f"{escape(_format_basis(row.get('basis')))}</td>"
                "<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:700'>"
                f"{escape(_format_cash(row.get('cash_price_bu')))}</td>"
                "</tr>"
                for row in rows
            )
            table = (
                "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
                "<thead><tr><th align='left'>Buyer / location</th><th align='left'>Delivery</th>"
                "<th align='right'>Basis</th><th align='right'>Cash</th></tr></thead>"
                f"<tbody>{body}</tbody></table>"
                f"<p style='font-size:13px;color:#4b5563'>{section['market_count']} listed markets. "
                f"Cash median across listed delivery periods {_format_cash(section['median_cash_price_bu'])}; "
                f"listed range {_format_cash(section['cash_spread_bu'])} before freight.</p>"
            )
        else:
            table = "<p>No current canonical bids were available.</p>"
        section_html.append(f"<h2 style='margin-top:28px'>{escape(str(section['commodity']))}</h2>{table}")

    return (
        "<!doctype html><html><body style='margin:0;background:#f3f4f6;font-family:Arial,sans-serif;color:#111827'>"
        "<div style='max-width:680px;margin:0 auto;background:white;padding:32px'>"
        f"<h1 style='margin-top:0'>{escape(subject)}</h1>"
        f"<p style='color:#4b5563'>Data as of {_format_as_of(data_as_of)}</p>"
        f"{''.join(section_html)}"
        "<p><a style='color:#166534' "
        f"href='{escape(settings.market_report_public_url.rstrip('/'))}'>View current GrainBids</a></p>"
        "<p style='font-size:12px;color:#6b7280'>Posted-bid snapshot only, not a delivered-netback "
        "recommendation. Freight is not included. Verify prices, grades, delivery periods, futures contracts, "
        "and freight before making a sale.</p>"
        "</div></body></html>"
    )


def _build_message(report: MarketReport, subscriber: NewsletterSubscriber) -> EmailMessage:
    unsubscribe_base = settings.market_report_unsubscribe_url
    if not unsubscribe_base:
        raise RuntimeError("MARKET_REPORT_UNSUBSCRIBE_URL is required")
    unsubscribe_url = f"{unsubscribe_base.rstrip('/')}?token={subscriber.unsubscribe_token}"
    greeting = f"Hi {subscriber.first_name},\n\n" if subscriber.first_name else ""
    text = f"{greeting}{report.text}\n\nUnsubscribe: {unsubscribe_url}"
    html = report.html.replace(
        "</div></body></html>",
        "<p style='font-size:12px;color:#6b7280'>"
        f"<a href='{escape(unsubscribe_url)}'>Unsubscribe</a></p></div></body></html>",
    )
    if subscriber.first_name:
        html = html.replace("<h1", f"<p>Hi {escape(subscriber.first_name)},</p><h1", 1)

    message = EmailMessage()
    message["Subject"] = report.subject
    message["From"] = settings.market_report_email_from
    message["To"] = subscriber.email
    message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


def _validate_delivery_config() -> None:
    missing: list[str] = []
    if not settings.market_report_email_enabled:
        missing.append("MARKET_REPORT_EMAIL_ENABLED=true")
    if not settings.market_report_email_from:
        missing.append("MARKET_REPORT_EMAIL_FROM")
    if not settings.market_report_unsubscribe_url:
        missing.append("MARKET_REPORT_UNSUBSCRIBE_URL")
    if not settings.alert_smtp_host:
        missing.append("ALERT_SMTP_HOST")
    if missing:
        raise RuntimeError("Market report delivery is disabled or incomplete: " + ", ".join(missing))


def _as_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_cash(value: object) -> str:
    number = _as_number(value)
    return "n/a" if number is None else f"${number:,.2f}/bu"


def _format_basis(value: object) -> str:
    number = _as_number(value)
    return "n/a" if number is None else f"{number:+.2f}/bu"


def _format_as_of(value: datetime | None) -> str:
    if value is None:
        return "not available"
    return f"{value:%B} {value.day}, {value:%Y at %H:%M UTC}"


def _row_label(row: dict[str, object]) -> str:
    company = str(row.get("company_name") or "").strip()
    location = str(row.get("location") or "").strip()
    if company and location and company.casefold() != location.casefold():
        return f"{company} — {location}"
    return company or location or "Unlabelled market"


def _market_period_label(row: dict[str, object]) -> str:
    delivery = str(row.get("delivery_label") or "").strip()
    futures = str(row.get("futures_month") or "").strip()
    if delivery and futures:
        return f"{delivery} delivery / {futures} futures"
    if delivery:
        return f"{delivery} delivery"
    if futures:
        return f"{futures} futures"
    return "Delivery / futures month not listed"
