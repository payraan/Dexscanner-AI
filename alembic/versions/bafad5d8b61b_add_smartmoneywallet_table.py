"""Add SmartMoneyWallet table

Revision ID: bafad5d8b61b
Revises: 347b80404f1a
Create Date: 2025-08-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bafad5d8b61b'
down_revision: Union[str, Sequence[str], None] = '347b80404f1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
