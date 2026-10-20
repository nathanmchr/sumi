"""Persist the optional furigana colour helper."""
from alembic import op
import sqlalchemy as sa

revision = '0006_furigana_helper'
down_revision = '0005_romaji_search'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_settings', sa.Column('furigana_helper_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('user_settings', 'furigana_helper_enabled')
