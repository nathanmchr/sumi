"""Persist each learner's step order without rewriting their completed steps."""
from alembic import op
import sqlalchemy as sa

revision = "0010_lesson_step_order"
down_revision = "0009_lessons"
branch_labels = None
depends_on = None


def upgrade():
    if not op.get_context().as_sql:
        columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("lesson_progress")}
        if "step_order" in columns:
            column = columns["step_order"]
            if not isinstance(column["type"], sa.JSON) or not column["nullable"]:
                raise RuntimeError("Existing lesson_progress.step_order must be nullable JSON")
            return
    op.add_column("lesson_progress", sa.Column("step_order", sa.JSON(), nullable=True))


def downgrade():
    # Dropping the order of an active lesson would reinterpret its cursor.
    if op.get_context().as_sql:
        raise RuntimeError("Downgrade requires an online check of lesson progression")
    if op.get_bind().execute(sa.text("SELECT 1 FROM lesson_progress WHERE step_order IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot drop step orders while learners have sequenced progress")
    op.drop_column("lesson_progress", "step_order")
