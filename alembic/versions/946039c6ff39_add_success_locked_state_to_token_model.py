"""Add SUCCESS_LOCKED state to Token model

Revision ID: 946039c6ff39
Revises: 47f325dd1e1d
Create Date: 2025-09-11 01:06:04.575189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '946039c6ff39'
down_revision: Union[str, Sequence[str], None] = '47f325dd1e1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Define the ENUM with ALL possible values, including the old ones
    token_state_enum = sa.Enum(
        'WATCHING', 'SIGNALED', 'COOLDOWN', 'SUCCESS_LOCKED', 'INVALIDATED',
        'RANGING', 'TRENDING',  # <-- Now includes RANGING and TRENDING
        name='tokenstate'
    )
    token_state_enum.create(op.get_bind(), checkfirst=True)

    # Alter the column using an explicit cast
    op.execute("ALTER TABLE tokens ALTER COLUMN state TYPE tokenstate USING state::text::tokenstate")


def downgrade() -> None:
    """Downgrade schema."""
    # The existing type must also contain all possible values for a clean downgrade
    existing_enum = sa.Enum(
        'WATCHING', 'SIGNALED', 'COOLDOWN', 'SUCCESS_LOCKED', 'INVALIDATED',
        'RANGING', 'TRENDING',
        name='tokenstate'
    )

    op.alter_column('tokens', 'state',
                    existing_type=existing_enum,
                    type_=sa.VARCHAR(),
                    existing_nullable=False)

    # Drop the ENUM type
    existing_enum.drop(op.get_bind(), checkfirst=True)
