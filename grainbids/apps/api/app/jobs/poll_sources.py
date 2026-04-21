from __future__ import annotations

from datetime import datetime, timezone
import time

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.commodity import Commodity
from app.services.source_orchestration import poll_due_sources


def _default_commodity_id(db) -> str:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise RuntimeError("No commodity exists; create at least one commodity before polling sources.")
    return commodity.id


def run_once() -> int:
    session = get_sessionmaker()()
    try:
        commodity_id = _default_commodity_id(session)
        results = poll_due_sources(session, commodity_id=commodity_id, now=datetime.now(timezone.utc))
        failed = sum(1 for result in results if result.status != "completed")
        print(f"polled={len(results)} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        session.close()


def run_loop(sleep_seconds: int = 60) -> int:
    while True:
        exit_code = run_once()
        print(f"cycle_exit={exit_code} sleeping={sleep_seconds}s")
        time.sleep(max(5, sleep_seconds))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Poll due GrainBids sources.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--sleep-seconds", type=int, default=60, help="Loop delay in seconds.")
    args = parser.parse_args()

    if args.loop:
        return run_loop(sleep_seconds=args.sleep_seconds)
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
