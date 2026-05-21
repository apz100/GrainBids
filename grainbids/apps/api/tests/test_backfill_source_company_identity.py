from __future__ import annotations

import uuid

from app.jobs.backfill_source_company_identity import (
    _desired_company_id_for_row,
    _infer_location_company_id,
    _is_trusted_company_id,
)


def test_is_trusted_company_id_rejects_aggregator_and_region_names() -> None:
    agricharts_id = uuid.uuid4()
    ontario_id = uuid.uuid4()
    glg_id = uuid.uuid4()
    company_name_map = {
        agricharts_id: "Agricharts",
        ontario_id: "Ontario Cash Bids",
        glg_id: "GLG",
    }

    assert _is_trusted_company_id(agricharts_id, company_name_map=company_name_map) is False
    assert _is_trusted_company_id(ontario_id, company_name_map=company_name_map) is False
    assert _is_trusted_company_id(glg_id, company_name_map=company_name_map) is True


def test_infer_location_company_id_prefers_single_trusted_candidate() -> None:
    agricharts_id = uuid.uuid4()
    glg_id = uuid.uuid4()
    company_name_map = {
        agricharts_id: "Agricharts",
        glg_id: "GLG",
    }

    inferred_company_id, is_ambiguous = _infer_location_company_id(
        current_company_id=agricharts_id,
        candidate_company_ids={agricharts_id, glg_id},
        company_name_map=company_name_map,
    )

    assert inferred_company_id == glg_id
    assert is_ambiguous is False


def test_infer_location_company_id_keeps_current_trusted_mapping_when_candidates_conflict() -> None:
    glg_id = uuid.uuid4()
    hensall_id = uuid.uuid4()
    company_name_map = {
        glg_id: "GLG",
        hensall_id: "Hensall",
    }

    inferred_company_id, is_ambiguous = _infer_location_company_id(
        current_company_id=glg_id,
        candidate_company_ids={glg_id, hensall_id},
        company_name_map=company_name_map,
    )

    assert inferred_company_id == glg_id
    assert is_ambiguous is True


def test_desired_company_id_for_row_uses_location_company_for_aggregator_and_region_sources() -> None:
    glg_id = uuid.uuid4()
    company_name_map = {glg_id: "GLG"}

    agricharts_result = _desired_company_id_for_row(
        source_name="Agricharts",
        current_company_id=None,
        trusted_location_company_id=glg_id,
        company_name_map=company_name_map,
        trusted_company_lookup={},
    )
    ontario_result = _desired_company_id_for_row(
        source_name="Ontario Cash Bids",
        current_company_id=None,
        trusted_location_company_id=glg_id,
        company_name_map=company_name_map,
        trusted_company_lookup={},
    )

    assert agricharts_result == glg_id
    assert ontario_result == glg_id


def test_desired_company_id_for_row_resolves_company_source_from_source_name() -> None:
    glg_id = uuid.uuid4()
    company_name_map: dict[uuid.UUID, str] = {}

    resolved_company_id = _desired_company_id_for_row(
        source_name="GLG",
        current_company_id=None,
        trusted_location_company_id=None,
        company_name_map=company_name_map,
        trusted_company_lookup={"glg": glg_id},
    )

    assert resolved_company_id == glg_id


def test_desired_company_id_for_row_corrects_mismatched_trusted_company() -> None:
    glg_id = uuid.uuid4()
    hensall_id = uuid.uuid4()
    company_name_map = {
        hensall_id: "Hensall",
    }

    resolved_company_id = _desired_company_id_for_row(
        source_name="GLG",
        current_company_id=hensall_id,
        trusted_location_company_id=None,
        company_name_map=company_name_map,
        trusted_company_lookup={"glg": glg_id},
    )

    assert resolved_company_id == glg_id
