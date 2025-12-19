"""Fix opportunity unique constraint for proper deduplication.

Revision ID: 20241215_005
Revises: 004_update_categories
Create Date: 2024-12-15

Changes:
- Remove unique constraint on source_url (multiple RFPs can come from same page)
- Add unique constraint on source_opportunity_id (the actual RFP document ID)
- This allows multiple crawl sessions to update existing opportunities gracefully
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '005_fix_opportunity_unique'
down_revision: Union[str, None] = '004_update_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing unique constraint on source_url
    # Multiple opportunities can come from the same page URL
    op.drop_constraint('uq_opportunities_source_url', 'opportunities', type_='unique')
    
    # Add unique constraint on source_opportunity_id instead
    # This is the actual RFP document ID which should be unique
    op.create_unique_constraint(
        'uq_opportunities_source_opportunity_id',
        'opportunities',
        ['source_opportunity_id']
    )
    
    # Add index on source_url for faster lookups (not unique)
    op.create_index('ix_opportunities_source_url', 'opportunities', ['source_url'])


def downgrade() -> None:
    # Remove the new index
    op.drop_index('ix_opportunities_source_url', 'opportunities')
    
    # Remove unique constraint on source_opportunity_id
    op.drop_constraint('uq_opportunities_source_opportunity_id', 'opportunities', type_='unique')
    
    # Restore unique constraint on source_url
    op.create_unique_constraint('uq_opportunities_source_url', 'opportunities', ['source_url'])

