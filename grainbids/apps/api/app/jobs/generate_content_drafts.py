from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.organization import Organization
from app.services.content_engine import ALLOWED_CADENCES, generate_content_draft, list_region_keys


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate QA-gated GrainBids content drafts for review.")
    parser.add_argument("--cadence", required=True, choices=ALLOWED_CADENCES)
    parser.add_argument("--region", choices=list_region_keys(), help="Generate one region; defaults to all configured regions.")
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        organizations = db.execute(select(Organization).order_by(Organization.created_at.asc())).scalars().all()
        if not organizations:
            raise RuntimeError("No organization exists. Create one before generating content drafts.")
        region_keys = (args.region,) if args.region else list_region_keys()
        blocked = 0
        for organization in organizations:
            for region_key in region_keys:
                result = generate_content_draft(
                    db,
                    org_id=organization.id,
                    cadence=args.cadence,
                    region_key=region_key,
                )
                blocked += int(result.draft.status == "blocked")
                action = "created" if result.created else "existing"
                print(
                    f"{action} issue={result.draft.issue_key} status={result.draft.status} "
                    f"draft_id={result.draft.id}"
                )
        return 1 if blocked else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
