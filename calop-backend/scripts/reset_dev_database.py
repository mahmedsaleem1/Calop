"""Drops every Calop table (old and new) and the Alembic version table from the database in DATABASE_URL.
Supabase Auth users are untouched. Use it once to move from the old schema to the new baseline:

    python scripts/reset_dev_database.py --yes
    alembic upgrade head
    python -m app.seeds.reference

All current data is dummy, so this is meant for the development database only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402

TABLES = [
    "food_log_entry_nutrients", "food_log_entries", "recognition_candidates", "recognition_runs", "jobs", "captures",
    "device_api_keys", "devices", "nutrition_targets", "goals", "weight_entries", "user_profiles",
    "food_search_misses", "food_aliases", "food_nutrients", "foods", "nutrients", "food_groups", "food_sources",
    "events", "users",
    "analyses",  # created by the old baseline and dropped by the old second migration
    "alembic_version",
]


def main() -> None:
    url = get_settings().database_url
    target = make_url(url)
    print(f"Database: {target.host}:{target.port}/{target.database}")
    if "--yes" not in sys.argv:
        sys.exit("Refusing to drop tables without --yes.")
    engine = create_engine(url)
    with engine.begin() as connection:
        for table in TABLES:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            print(f"dropped {table}")
    print("Done. Now run: alembic upgrade head && python -m app.seeds.reference")


if __name__ == "__main__":
    main()
