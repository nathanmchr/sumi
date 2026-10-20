"""Keep display romanization separate from search keys and make it opt-in."""
from alembic import op
import sqlalchemy as sa

revision = '0008_romaji_display'
down_revision = '0007_jlpt_level_ranges'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_settings', sa.Column('romaji_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('vocabulary_items', sa.Column('romaji', sa.Text(), nullable=False, server_default=''))


def downgrade():
    op.drop_column('vocabulary_items', 'romaji')
    op.drop_column('user_settings', 'romaji_enabled')
