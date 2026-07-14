from __future__ import annotations

import sys
import unittest
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.newsletter import NewsletterSignup, normalize_email  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


class _FakeResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commit_count = 0

    def execute(self, _query):
        return _FakeResult()

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        pass


class _ExistingResult:
    def __init__(self, row) -> None:
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _ExistingSession(_FakeSession):
    def __init__(self, row) -> None:
        super().__init__()
        self.row = row

    def execute(self, _query):
        return _ExistingResult(self.row)


class NewsletterSignupTests(unittest.TestCase):
    def test_normalize_email(self) -> None:
        self.assertEqual(normalize_email(" Adam@Example.COM "), "adam@example.com")

    def test_signup_normalizes_fields(self) -> None:
        payload = NewsletterSignup(
            email=" Adam@Example.COM ",
            first_name=" Adam ",
            region=" Eastern Ontario ",
            audience="farmer",
            signup_source=" HomePage ",
            consent=True,
        )
        self.assertEqual(payload.email, "adam@example.com")
        self.assertEqual(payload.first_name, "Adam")
        self.assertEqual(payload.region, "Eastern Ontario")
        self.assertEqual(payload.signup_source, "homepage")

    def test_signup_rejects_invalid_email(self) -> None:
        with self.assertRaises(ValidationError):
            NewsletterSignup(email="not-an-email", consent=True)

    def test_signup_requires_consent(self) -> None:
        with self.assertRaises(ValidationError):
            NewsletterSignup(email="adam@example.com", consent=False)

    def test_public_endpoint_stores_consent_tracked_signup(self) -> None:
        db = _FakeSession()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).post(
                "/api/newsletter/subscribers",
                json={
                    "email": "Adam@Example.com",
                    "first_name": "Adam",
                    "audience": "farmer",
                    "signup_source": "homepage_market_report",
                    "consent": True,
                },
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "subscribed")
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].email, "adam@example.com")
        self.assertEqual(db.commit_count, 1)

    def test_honeypot_submission_is_accepted_but_not_stored(self) -> None:
        db = _FakeSession()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).post(
                "/api/newsletter/subscribers",
                json={
                    "email": "bot@example.com",
                    "consent": True,
                    "website": "https://spam.invalid",
                },
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_count, 0)

    def test_unsubscribe_requires_confirmation_post(self) -> None:
        token = uuid.uuid4()
        subscriber = type("Subscriber", (), {"status": "active", "updated_at": None})()
        db = _ExistingSession(subscriber)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            confirmation = client.get(f"/api/newsletter/unsubscribe?token={token}")
            response = client.post(f"/api/newsletter/unsubscribe?token={token}")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("Unsubscribe from GrainBids?", confirmation.text)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(subscriber.status, "unsubscribed")
        self.assertEqual(db.commit_count, 1)


if __name__ == "__main__":
    unittest.main()
