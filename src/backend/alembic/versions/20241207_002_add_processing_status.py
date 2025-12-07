"""Add processing_status fields to crawl_sources

Revision ID: 002_processing_status
Revises: 001_initial
Create Date: 2024-12-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_processing_status'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create processingstatusenum type for processing_status field
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE processingstatusenum AS ENUM ('pending', 'processing', 'success', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Add new columns to crawl_sources
    op.add_column(
        'crawl_sources',
        sa.Column(
            'processing_status',
            sa.Enum('pending', 'processing', 'success', 'failed', name='processingstatusenum', create_type=False),
            nullable=True,
            server_default='pending'
        )
    )
    
    op.add_column(
        'crawl_sources',
        sa.Column('last_crawl_started_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    op.add_column(
        'crawl_sources',
        sa.Column('last_crawl_completed_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    op.add_column(
        'crawl_sources',
        sa.Column('processing_error_message', sa.Text, nullable=True)
    )
    
    # Create index on processing_status for efficient filtering
    op.create_index(
        'ix_crawl_sources_processing_status',
        'crawl_sources',
        ['processing_status']
    )


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_crawl_sources_processing_status', table_name='crawl_sources')
    
    # Remove columns
    op.drop_column('crawl_sources', 'processing_error_message')
    op.drop_column('crawl_sources', 'last_crawl_completed_at')
    op.drop_column('crawl_sources', 'last_crawl_started_at')
    op.drop_column('crawl_sources', 'processing_status')
    
    # Drop enum type
    op.execute('DROP TYPE IF EXISTS processingstatusenum')

