"""Publish theme-final cumulative lessons; preview (rollback) unless --apply is passed."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.core.database import engine
from app.services.theme_recaps import publish_theme_recaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with Session(engine) as db:
        try:
            report = publish_theme_recaps(db)
            db.commit() if args.apply else db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps({"applied": args.apply, **report}))


if __name__ == "__main__":
    main()
