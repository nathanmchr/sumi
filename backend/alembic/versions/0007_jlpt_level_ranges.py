"""Add a minimum difficulty without widening existing learning preferences."""
from alembic import op
import sqlalchemy as sa

revision = '0007_jlpt_level_ranges'
down_revision = '0006_furigana_helper'
branch_labels = None
depends_on = None

CATEGORIES = ('vocabulary', 'grammar', 'kanji')


def upgrade():
    for category in CATEGORIES:
        minimum = f'{category}_min_level_code'
        maximum = f'{category}_level_code'
        op.add_column('user_settings', sa.Column(minimum, sa.String(8), sa.ForeignKey('jlpt_levels.code'), nullable=True))
        op.execute(sa.text(f'UPDATE user_settings SET {minimum} = {maximum}'))
        op.alter_column('user_settings', minimum, nullable=False)
        # JLPT numbers run opposite to difficulty: N5 is easier than N1.
        op.create_check_constraint(f'ck_settings_{category}_range', 'user_settings', f'{minimum} >= {maximum}')


def downgrade():
    for category in reversed(CATEGORIES):
        op.drop_constraint(f'ck_settings_{category}_range', 'user_settings', type_='check')
        op.drop_column('user_settings', f'{category}_min_level_code')
