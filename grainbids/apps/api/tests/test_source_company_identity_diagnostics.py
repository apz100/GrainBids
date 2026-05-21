from __future__ import annotations

from collections import defaultdict
import uuid

from app.models.location import Location
from app.services.source_company_identity_diagnostics import _build_ambiguous_location_rows


def _location(*, name: str, region: str | None = None) -> Location:
    return Location(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        company_id=None,
        name=name,
        canonical_key=name.casefold(),
        region=region,
    )


def test_build_ambiguous_location_rows_includes_only_ambiguous_locations() -> None:
    loc_a = _location(name="Alliston", region="Ontario")
    loc_b = _location(name="Blenheim", region="Ontario")
    glg_id = uuid.uuid4()
    andersons_id = uuid.uuid4()

    by_location = {
        loc_a.id: {
            "location": loc_a,
            "current_company_id": glg_id,
            "company_counts": defaultdict(int, {glg_id: 5, andersons_id: 2}),
            "source_counts": defaultdict(int, {"GLG": 5, "Andersons": 2}),
        },
        loc_b.id: {
            "location": loc_b,
            "current_company_id": glg_id,
            "company_counts": defaultdict(int, {glg_id: 3}),
            "source_counts": defaultdict(int, {"GLG": 3}),
        },
    }
    trusted_names = {
        glg_id: "GLG",
        andersons_id: "Andersons",
    }

    rows = _build_ambiguous_location_rows(
        by_location=by_location,
        trusted_company_name_by_id=trusted_names,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["location_name"] == "Alliston"
    assert row["candidate_company_count"] == 2
    assert row["candidate_row_count"] == 7
    assert row["current_company_name"] == "GLG"
    assert [entry["company_name"] for entry in row["candidate_companies"]] == ["GLG", "Andersons"]


def test_build_ambiguous_location_rows_sorts_by_candidate_and_row_counts() -> None:
    loc_a = _location(name="A", region="Ontario")
    loc_b = _location(name="B", region="Ontario")
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    c3 = uuid.uuid4()

    by_location = {
        loc_a.id: {
            "location": loc_a,
            "current_company_id": c1,
            "company_counts": defaultdict(int, {c1: 4, c2: 3}),
            "source_counts": defaultdict(int, {"S1": 4, "S2": 3}),
        },
        loc_b.id: {
            "location": loc_b,
            "current_company_id": c1,
            "company_counts": defaultdict(int, {c1: 2, c2: 1, c3: 1}),
            "source_counts": defaultdict(int, {"S1": 2, "S2": 1, "S3": 1}),
        },
    }
    trusted_names = {
        c1: "Company A",
        c2: "Company B",
        c3: "Company C",
    }

    rows = _build_ambiguous_location_rows(
        by_location=by_location,
        trusted_company_name_by_id=trusted_names,
    )

    assert len(rows) == 2
    assert rows[0]["location_name"] == "B"
    assert rows[0]["candidate_company_count"] == 3
    assert rows[1]["location_name"] == "A"
    assert rows[1]["candidate_company_count"] == 2
