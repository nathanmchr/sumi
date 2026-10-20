"""Add authored lessons and independent, resumable lesson progress."""
from alembic import op
import sqlalchemy as sa

revision = "0009_lessons"
down_revision = "0008_romaji_display"
branch_labels = None
depends_on = None


def create_or_adopt(name, *definitions):
    """Historical dev startup uses create_all; adopt only an equivalent table."""
    if op.get_context().as_sql or not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *definitions)
        return False
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns(name)}
    expected = {column.name: column for column in definitions if isinstance(column, sa.Column)}
    # A newer create_all may already have added nullable/defaulted columns.
    # Adopt compatible supersets, but never missing fields or required extras.
    extras = set(columns) - set(expected)
    if not set(expected).issubset(columns) or any(not columns[key]["nullable"] and columns[key]["default"] is None for key in extras):
        raise RuntimeError(f"Existing {name} has unexpected columns; migration stopped")
    for key, column in expected.items():
        actual = columns[key]
        if (actual["type"]._type_affinity != column.type._type_affinity
                or actual["nullable"] != column.nullable
                or getattr(actual["type"], "length", None) != getattr(column.type, "length", None)):
            raise RuntimeError(f"Existing {name}.{key} does not match the lesson schema")
    primary = {column.name for column in expected.values() if column.primary_key}
    if set(inspector.get_pk_constraint(name)["constrained_columns"]) != primary:
        raise RuntimeError(f"Existing {name} has an incompatible primary key")
    for column in expected.values():
        for foreign in column.foreign_keys:
            table, target = foreign.target_fullname.split(".")
            if not any(fk["constrained_columns"] == [column.name] and fk["referred_table"] == table
                       and fk["referred_columns"] == [target] for fk in inspector.get_foreign_keys(name)):
                raise RuntimeError(f"Existing {name}.{column.name} has an incompatible foreign key")
        if column.unique and not any(c["column_names"] == [column.name] for c in inspector.get_unique_constraints(name)):
            raise RuntimeError(f"Existing {name}.{column.name} is missing its unique constraint")
    if name == "lesson_progress" and not any(c["name"] == "ck_lesson_progress_nonnegative" for c in inspector.get_check_constraints(name)):
        raise RuntimeError("Existing lesson progress is missing its bounds constraint")
    return True


def upgrade():
    existing = create_or_adopt("lessons",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("level", sa.String(8), sa.ForeignKey("jlpt_levels.code"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, unique=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    if not existing or not any(i["name"] == "ix_lessons_level" for i in sa.inspect(op.get_bind()).get_indexes("lessons")):
        op.create_index("ix_lessons_level", "lessons", ["level"])
    create_or_adopt("lesson_progress",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("lesson_id", sa.String(100), sa.ForeignKey("lessons.id"), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("last_command", sa.String(64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cursor >= 0 AND revision >= 0", name="ck_lesson_progress_nonnegative"))


def downgrade():
    op.drop_table("lesson_progress")
    op.drop_index("ix_lessons_level", table_name="lessons")
    op.drop_table("lessons")
