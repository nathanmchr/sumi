"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    content_type_enum = postgresql.ENUM("vocabulary", "kanji", "grammar", name="content_type")
    review_status_enum = postgresql.ENUM("new", "learning", "fragile", "known", "review", "master", name="review_status")

    op.create_table(
        "jlpt_levels",
        sa.Column("code", sa.String(length=8), primary_key=True),
        sa.Column("rank", sa.Integer(), nullable=False, unique=True),
        sa.Column("label", sa.String(length=32), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "vocabulary_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False, unique=True),
        sa.Column("japanese", sa.String(length=255), nullable=False),
        sa.Column("reading", sa.String(length=255), nullable=False),
        sa.Column("furigana_segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("translation", sa.String(length=255), nullable=False),
        sa.Column("part_of_speech", sa.String(length=64), nullable=False),
        sa.Column("jlpt_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vocabulary_items_jlpt_level_code", "vocabulary_items", ["jlpt_level_code"])
    op.create_table(
        "kanji_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("character", sa.String(length=8), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=32), nullable=False, unique=True),
        sa.Column("meanings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("onyomi", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("kunyomi", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("radicals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mnemonic", sa.Text(), nullable=True),
        sa.Column("jlpt_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kanji_items_jlpt_level_code", "kanji_items", ["jlpt_level_code"])
    op.create_table(
        "grammar_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("jlpt_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("nuances", sa.Text(), nullable=False),
        sa.Column("counter_examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_grammar_slug"),
    )
    op.create_index("ix_grammar_items_jlpt_level_code", "grammar_items", ["jlpt_level_code"])
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("vocabulary_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("grammar_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("kanji_level_code", sa.String(length=8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("furigana_display_mode", sa.String(length=16), nullable=False),
        sa.Column("daily_goal_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "example_sentences",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=False),
        sa.Column("furigana_segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("vocabulary_item_id", sa.String(), sa.ForeignKey("vocabulary_items.id"), nullable=True),
        sa.Column("grammar_item_id", sa.String(), sa.ForeignKey("grammar_items.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "vocabulary_kanji_links",
        sa.Column("vocabulary_item_id", sa.String(), sa.ForeignKey("vocabulary_items.id"), nullable=False),
        sa.Column("kanji_item_id", sa.String(), sa.ForeignKey("kanji_items.id"), nullable=False),
        sa.Column("kanji_position", sa.Integer(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("vocabulary_item_id", "kanji_item_id"),
        sa.UniqueConstraint("vocabulary_item_id", "kanji_item_id", name="uq_vocab_kanji_link"),
    )
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("planned_items", sa.Integer(), nullable=False),
        sa.Column("completed_items", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "learning_states",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("content_id", sa.String(length=64), nullable=False),
        sa.Column("status", review_status_enum, nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("lapses_count", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_session_id", sa.String(), sa.ForeignKey("study_sessions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "content_type", "content_id", name="uq_learning_state_item"),
    )
    op.create_index("ix_learning_states_user_id", "learning_states", ["user_id"])
    op.create_index("ix_learning_states_next_review_at", "learning_states", ["next_review_at"])
    op.create_table(
        "review_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("content_id", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("review_window", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("study_sessions.id"), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("review_history")
    op.drop_index("ix_learning_states_next_review_at", table_name="learning_states")
    op.drop_index("ix_learning_states_user_id", table_name="learning_states")
    op.drop_table("learning_states")
    op.drop_table("study_sessions")
    op.drop_table("vocabulary_kanji_links")
    op.drop_table("example_sentences")
    op.drop_table("refresh_tokens")
    op.drop_table("user_settings")
    op.drop_index("ix_grammar_items_jlpt_level_code", table_name="grammar_items")
    op.drop_table("grammar_items")
    op.drop_index("ix_kanji_items_jlpt_level_code", table_name="kanji_items")
    op.drop_table("kanji_items")
    op.drop_index("ix_vocabulary_items_jlpt_level_code", table_name="vocabulary_items")
    op.drop_table("vocabulary_items")
    op.drop_table("users")
    op.drop_table("jlpt_levels")
    postgresql.ENUM(name="review_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="content_type").drop(op.get_bind(), checkfirst=True)
