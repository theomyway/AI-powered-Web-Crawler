"""Add missing document columns (content_type, is_primary).

Revision ID: 20260204_008
Revises: 007_add_company_info, 7005c4490c5e
Create Date: 2026-02-04

This is a merge revision that consolidates both company_info migrations
and adds the missing document columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260204_008'
down_revision: Union[str, Sequence[str], None] = ('007_add_company_info', '7005c4490c5e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content_type column (model uses content_type, database had mime_type)
    # Check if mime_type exists and rename it, otherwise add content_type
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('documents')]
    
    if 'mime_type' in columns and 'content_type' not in columns:
        # Rename mime_type to content_type
        op.alter_column('documents', 'mime_type', new_column_name='content_type')
    elif 'content_type' not in columns:
        # Add content_type column
        op.add_column('documents', sa.Column('content_type', sa.String(100), nullable=True))
    
    # Add is_primary column if it doesn't exist
    if 'is_primary' not in columns:
        op.add_column('documents', sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove is_primary column
    op.drop_column('documents', 'is_primary')
    
    # Rename content_type back to mime_type
    op.alter_column('documents', 'content_type', new_column_name='mime_type')

