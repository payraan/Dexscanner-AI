"""add_scan_tracking_fields_to_tokens

Revision ID: 167114e5ed28
Revises: bafad5d8b61b
Create Date: 2025-09-03 19:38:02.752211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '167114e5ed28'
down_revision: Union[str, Sequence[str], None] = '95cfdbf1bbc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tokens', sa.Column('last_scan_price', sa.Float(), nullable=True))
    op.add_column('tokens', sa.Column('message_id', sa.BigInteger(), nullable=True))
    op.add_column('tokens', sa.Column('reply_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tokens', 'reply_count')
    op.drop_column('tokens', 'message_id')
    op.drop_column('tokens', 'last_scan_price')
