"""Associate stable application records with the consolidated editorial catalogue."""
from alembic import op
import sqlalchemy as sa

revision = "0012_consolidated_catalog"
down_revision = "0011_lesson_recap"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("vocabulary_items", "grammar_items", "kanji_items"):
        columns = set() if op.get_context().as_sql else {
            c["name"] for c in sa.inspect(op.get_bind()).get_columns(name)
        }
        for field, kind in (("catalog_id", sa.String(36)), ("source_order", sa.Integer())):
            if field not in columns:
                op.add_column(name, sa.Column(field, kind, nullable=True))
        indexes = set() if op.get_context().as_sql else {
            i["name"] for i in sa.inspect(op.get_bind()).get_indexes(name)
        }
        index = f"ix_{name}_catalog_id"
        if index not in indexes:
            op.create_index(index, name, ["catalog_id"], unique=True)
    columns = set() if op.get_context().as_sql else {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("vocabulary_items")
    }
    if "kanji_level_code" not in columns:
        op.add_column("vocabulary_items", sa.Column("kanji_level_code", sa.String(8), nullable=True))
    if op.get_context().as_sql or not sa.inspect(op.get_bind()).has_table("content_aliases"):
        op.create_table(
            "content_aliases",
            sa.Column("content_type", sa.String(16), primary_key=True),
            sa.Column("alias", sa.String(160), primary_key=True),
            sa.Column("content_id", sa.String(64), nullable=False),
        )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Downgrade requires an online catalogue check")
    for name in ("vocabulary_items", "grammar_items", "kanji_items"):
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {name} WHERE catalog_id IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Restore the pre-catalogue backup before removing catalogue identities")
    if op.get_bind().execute(sa.text("SELECT 1 FROM content_aliases LIMIT 1")).first():
        raise RuntimeError("Cannot remove live legacy URL aliases")
    op.drop_table("content_aliases")
    op.drop_column("vocabulary_items", "kanji_level_code")
    for name in ("vocabulary_items", "grammar_items", "kanji_items"):
        op.drop_index(f"ix_{name}_catalog_id", table_name=name)
        op.drop_column(name, "source_order")
        op.drop_column(name, "catalog_id")
