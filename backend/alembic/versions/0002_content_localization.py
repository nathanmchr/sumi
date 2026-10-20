"""add user locales and localized content

Revision ID: 0002_content_localization
Revises: 0001_initial
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_content_localization"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _locale_columns(item_column: sa.Column, *content_columns: sa.Column) -> list[sa.Column | sa.CheckConstraint]:
    return [
        item_column,
        sa.Column("locale", sa.String(length=5), primary_key=True),
        *content_columns,
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("locale IN ('en', 'fr')", name=f"ck_{item_column.name}_locale"),
    ]


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("interface_locale", sa.String(length=5), nullable=False, server_default="en"))
    op.add_column("user_settings", sa.Column("content_locale", sa.String(length=5), nullable=False, server_default="en"))
    op.create_check_constraint("ck_user_settings_interface_locale", "user_settings", "interface_locale IN ('en', 'fr')")
    op.create_check_constraint("ck_user_settings_content_locale", "user_settings", "content_locale IN ('en', 'fr')")

    op.create_table(
        "vocabulary_translations",
        *_locale_columns(
            sa.Column("vocabulary_item_id", sa.String(), sa.ForeignKey("vocabulary_items.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("translation", sa.String(length=255), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
        ),
    )
    op.create_table(
        "kanji_translations",
        *_locale_columns(
            sa.Column("kanji_item_id", sa.String(), sa.ForeignKey("kanji_items.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("meanings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("mnemonic", sa.Text(), nullable=True),
        ),
    )
    op.create_table(
        "grammar_translations",
        *_locale_columns(
            sa.Column("grammar_item_id", sa.String(), sa.ForeignKey("grammar_items.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("nuances", sa.Text(), nullable=False, server_default=""),
        ),
    )
    op.create_table(
        "example_sentence_translations",
        *_locale_columns(
            sa.Column("example_sentence_id", sa.String(), sa.ForeignKey("example_sentences.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("translation", sa.Text(), nullable=False),
        ),
    )

    op.execute("""
        INSERT INTO vocabulary_translations (vocabulary_item_id, locale, translation, notes)
        SELECT id, 'en', translation, notes FROM vocabulary_items
    """)
    op.execute("""
        INSERT INTO kanji_translations (kanji_item_id, locale, meanings, mnemonic)
        SELECT id, 'en', meanings, mnemonic FROM kanji_items
    """)
    op.execute("""
        INSERT INTO grammar_translations (grammar_item_id, locale, explanation, nuances)
        SELECT id, 'en', explanation, nuances FROM grammar_items
    """)
    op.execute("""
        INSERT INTO example_sentence_translations (example_sentence_id, locale, translation)
        SELECT id, 'en', translation FROM example_sentences
    """)


def downgrade() -> None:
    op.drop_table("example_sentence_translations")
    op.drop_table("grammar_translations")
    op.drop_table("kanji_translations")
    op.drop_table("vocabulary_translations")
    op.drop_constraint("ck_user_settings_content_locale", "user_settings", type_="check")
    op.drop_constraint("ck_user_settings_interface_locale", "user_settings", type_="check")
    op.drop_column("user_settings", "content_locale")
    op.drop_column("user_settings", "interface_locale")
