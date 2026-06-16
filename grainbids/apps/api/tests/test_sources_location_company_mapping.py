from __future__ import annotations

from contextlib import contextmanager
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.request_context import RequestContext, get_request_context
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.company import Company
from app.models.location import Location
from app.models.organization import Organization


@contextmanager
def _client_with_context(session, *, org_id: uuid.UUID, role: str = "admin"):
    context = RequestContext(org_id=org_id, user_email="ops@example.com", user_role=role)
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Organization.__table__, Company.__table__, Location.__table__])
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed_org(session, *, name: str) -> uuid.UUID:
    org = Organization(name=name)
    session.add(org)
    session.flush()
    return org.id


def _seed_company(session, *, org_id: uuid.UUID, name: str) -> Company:
    company = Company(org_id=org_id, name=name, canonical_key=name.casefold())
    session.add(company)
    session.flush()
    return company


def _seed_location(session, *, org_id: uuid.UUID, name: str, company_id: uuid.UUID | None = None) -> Location:
    location = Location(
        org_id=org_id,
        company_id=company_id,
        name=name,
        canonical_key=name.casefold(),
        region="Ontario",
    )
    session.add(location)
    session.flush()
    return location


def test_update_location_company_mapping_sets_company_for_active_org() -> None:
    session = _session()
    try:
        org_id = _seed_org(session, name="Org")
        company = _seed_company(session, org_id=org_id, name="GLG")
        location = _seed_location(session, org_id=org_id, name="Alliston")
        session.commit()

        with _client_with_context(session, org_id=org_id) as client:
            response = client.put(
                f"/api/sources/locations/{location.id}/company",
                json={"company_id": str(company.id)},
            )

        assert response.status_code == 200
        assert response.json()["company_id"] == str(company.id)
        assert session.get(Location, location.id).company_id == company.id
    finally:
        session.close()


def test_update_location_company_mapping_can_clear_company() -> None:
    session = _session()
    try:
        org_id = _seed_org(session, name="Org")
        company = _seed_company(session, org_id=org_id, name="GLG")
        location = _seed_location(session, org_id=org_id, name="Alliston", company_id=company.id)
        session.commit()

        with _client_with_context(session, org_id=org_id) as client:
            response = client.put(
                f"/api/sources/locations/{location.id}/company",
                json={"company_id": None},
            )

        assert response.status_code == 200
        assert response.json()["company_id"] is None
        assert session.get(Location, location.id).company_id is None
    finally:
        session.close()


def test_update_location_company_mapping_rejects_cross_org_company() -> None:
    session = _session()
    try:
        org_id = _seed_org(session, name="Org")
        other_org_id = _seed_org(session, name="Other Org")
        other_company = _seed_company(session, org_id=other_org_id, name="Other")
        location = _seed_location(session, org_id=org_id, name="Alliston")
        session.commit()

        with _client_with_context(session, org_id=org_id) as client:
            response = client.put(
                f"/api/sources/locations/{location.id}/company",
                json={"company_id": str(other_company.id)},
            )

        assert response.status_code == 404
        assert session.get(Location, location.id).company_id is None
    finally:
        session.close()


def test_update_location_company_mapping_rejects_cross_org_location() -> None:
    session = _session()
    try:
        org_id = _seed_org(session, name="Org")
        other_org_id = _seed_org(session, name="Other Org")
        company = _seed_company(session, org_id=org_id, name="GLG")
        other_location = _seed_location(session, org_id=other_org_id, name="Alliston")
        session.commit()

        with _client_with_context(session, org_id=org_id) as client:
            response = client.put(
                f"/api/sources/locations/{other_location.id}/company",
                json={"company_id": str(company.id)},
            )

        assert response.status_code == 404
        assert session.get(Location, other_location.id).company_id is None
    finally:
        session.close()


def test_update_location_company_mapping_requires_admin() -> None:
    session = _session()
    try:
        org_id = _seed_org(session, name="Org")
        company = _seed_company(session, org_id=org_id, name="GLG")
        location = _seed_location(session, org_id=org_id, name="Alliston")
        session.commit()

        with _client_with_context(session, org_id=org_id, role="member") as client:
            response = client.put(
                f"/api/sources/locations/{location.id}/company",
                json={"company_id": str(company.id)},
            )

        assert response.status_code == 403
        assert session.get(Location, location.id).company_id is None
    finally:
        session.close()
