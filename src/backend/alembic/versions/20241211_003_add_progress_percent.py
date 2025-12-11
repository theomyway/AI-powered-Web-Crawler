"""Add progress_percent and current_url to crawl_sources for real-time progress tracking.

Revision ID: 20241211_003
Revises: 20241207_002
Create Date: 2024-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_progress_percent'
down_revision: Union[str, None] = '002_processing_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add progress_percent column (0-100)
    op.add_column(
        'crawl_sources',
        sa.Column(
            'progress_percent',
            sa.Integer(),
            nullable=True,
            server_default='0',
            comment='Current crawl progress percentage (0-100)'
        )
    )
    
    # Add current_url being processed
    op.add_column(
        'crawl_sources',
        sa.Column(
            'current_processing_url',
            sa.String(500),
            nullable=True,
            comment='URL currently being processed'
        )
    )
    
    # Add progress_message for detailed status
    op.add_column(
        'crawl_sources',
        sa.Column(
            'progress_message',
            sa.String(200),
            nullable=True,
            comment='Human-readable progress message'
        )
    )


def downgrade() -> None:
    op.drop_column('crawl_sources', 'progress_message')
    op.drop_column('crawl_sources', 'current_processing_url')
    op.drop_column('crawl_sources', 'progress_percent')

