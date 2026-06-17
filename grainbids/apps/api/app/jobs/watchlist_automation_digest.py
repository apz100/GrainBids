from __future__ import annotations

import argparse

from app.db.session import get_sessionmaker
from app.services.watchlist_automation import run_watchlist_automation_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GrainBids watchlist automation digest cycle.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum preview rows per watchlist digest.")
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        results = run_watchlist_automation_cycle(db, limit=max(1, args.limit))
        sent = sum(1 for result in results if result.sent)
        skipped = sum(1 for result in results if result.status == "skipped")
        empty = sum(1 for result in results if result.status == "empty")
        failed = sum(1 for result in results if result.status == "failed")
        for result in results:
            print(
                f"watchlist={result.watchlist_id} automation={result.automation_id} "
                f"status={result.status} rows={result.row_count} sent={result.sent}"
            )
        print(
            f"cycle_watchlists={len(results)} sent={sent} skipped={skipped} empty={empty} failed={failed}"
        )
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
