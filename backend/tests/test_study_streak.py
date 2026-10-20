import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all SQLAlchemy models before schema creation
from app.models.base import Base
from app.models.learning import ReviewHistory
from app.models.user import User
from app.services.learning_service import study_activity
from app.utils.enums import ContentType

TODAY = date(2026, 10, 20)


class StudyStreakTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Factory = sessionmaker(engine, expire_on_commit=False)
        with self.Factory() as db:
            self.user = User(email="streak@example.test", full_name="Streak", hashed_password="test")
            db.add(self.user)
            db.commit()

    def answer_on(self, *days_ago: int):
        with self.Factory() as db:
            for offset in days_ago:
                at = datetime.combine(TODAY - timedelta(days=offset), datetime.min.time()).replace(hour=12).astimezone()
                db.add(ReviewHistory(user_id=self.user.id, content_type=ContentType.vocabulary, content_id="x", rating=3, created_at=at))
            db.commit()

    def activity(self):
        with self.Factory() as db:
            return study_activity(db, self.user.id, today=TODAY)

    def test_new_account_has_no_streak(self):
        self.assertEqual(self.activity(), (0, []))

    def test_consecutive_days_ending_today(self):
        self.answer_on(0, 0, 1, 2, 4)
        streak, days = self.activity()
        self.assertEqual(streak, 3)
        self.assertEqual(days, [TODAY - timedelta(days=n) for n in (4, 2, 1, 0)])

    def test_streak_survives_until_today_ends(self):
        self.answer_on(1, 2)
        self.assertEqual(self.activity()[0], 2)

    def test_gap_before_yesterday_breaks_streak(self):
        self.answer_on(2, 3)
        self.assertEqual(self.activity()[0], 0)

    def test_window_keeps_only_last_fourteen_days(self):
        self.answer_on(0, 13, 14, 30)
        self.assertEqual(self.activity()[1], [TODAY - timedelta(days=13), TODAY])


if __name__ == "__main__":
    unittest.main()
