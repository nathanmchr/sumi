"""Add FSRS memory and server-owned questions without rescheduling existing items."""

from alembic import op
import sqlalchemy as sa

revision = "0003_fsrs_questions"
down_revision = "0002_content_localization"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade():
    # No UPDATE of last_review_at, next_review_at, or historical reviews.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE review_status ADD VALUE IF NOT EXISTS 'relearning'")
    op.add_column(
        "learning_states", sa.Column("scheduler_version", sa.String(16), nullable=True)
    )
    op.add_column("learning_states", sa.Column("fsrs_card", sa.JSON(), nullable=True))
    op.add_column(
        "learning_states",
        sa.Column(
            "consecutive_correct", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "learning_states",
        sa.Column("recent_results", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "learning_states",
        sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "grammar_exercises",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column(
            "grammar_item_id",
            sa.String(),
            sa.ForeignKey("grammar_items.id"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.String(255), nullable=False),
        sa.Column("distractors", sa.JSON(), nullable=False),
        sa.Column("completed_sentence", sa.Text(), nullable=False),
        sa.Column("translations", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index(
        "ix_grammar_exercises_grammar_item_id", "grammar_exercises", ["grammar_item_id"]
    )
    op.create_table(
        "study_questions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("study_sessions.id"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column("prompt", sa.JSON(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("correct_option_id", sa.String(64), nullable=False),
        sa.Column("feedback", sa.JSON(), nullable=False),
        sa.Column("baseline_revision", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_option_id", sa.String(64), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_study_questions_session_id", "study_questions", ["session_id"])
    op.create_index("ix_study_questions_user_id", "study_questions", ["user_id"])


def downgrade():
    op.drop_table("study_questions")
    op.drop_table("grammar_exercises")
    for column in (
        "review_revision",
        "recent_results",
        "consecutive_correct",
        "fsrs_card",
        "scheduler_version",
    ):
        op.drop_column("learning_states", column)
    # PostgreSQL cannot remove an enum member safely; retain 'relearning'.
