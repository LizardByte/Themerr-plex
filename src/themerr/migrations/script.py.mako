"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

# lib imports
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the schema changes."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the schema changes."""
    ${downgrades if downgrades else "pass"}
