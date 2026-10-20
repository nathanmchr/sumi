"""Freeze cumulative end-of-lesson tests without rewriting completed lessons."""
from alembic import op
import sqlalchemy as sa

revision = "0011_lesson_recap"
down_revision = "0010_lesson_step_order"
branch_labels = None
depends_on = None


def upgrade():
    if not op.get_context().as_sql:
        columns = {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("lesson_progress")}
        if "recap_steps" in columns:
            column = columns["recap_steps"]
            if not isinstance(column["type"], sa.JSON) or not column["nullable"]:
                raise RuntimeError("Existing recap_steps must be nullable JSON")
            return
    op.add_column("lesson_progress", sa.Column("recap_steps", sa.JSON(), nullable=True))


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Downgrade requires an online progress check")
    if op.get_bind().execute(sa.text("SELECT 1 FROM lesson_progress WHERE recap_steps IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot remove saved cumulative tests")
    op.drop_column("lesson_progress", "recap_steps")
