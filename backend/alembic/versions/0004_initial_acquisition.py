"""Track initial acquisition without rescheduling existing reviews."""

from alembic import op
import sqlalchemy as sa

revision = "0004_initial_acquisition"
down_revision = "0003_fsrs_questions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_states", sa.Column("acquisition", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("learning_states", "acquisition")
