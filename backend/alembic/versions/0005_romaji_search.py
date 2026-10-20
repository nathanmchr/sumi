"""Store romaji search keys without changing displayed content."""
from alembic import op
import sqlalchemy as sa

revision = '0005_romaji_search'
down_revision = '0004_initial_acquisition'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('vocabulary_items', 'kanji_items', 'grammar_items'):
        op.add_column(table, sa.Column('romaji_search', sa.Text(), nullable=False, server_default=''))


def downgrade():
    for table in ('grammar_items', 'kanji_items', 'vocabulary_items'):
        op.drop_column(table, 'romaji_search')
