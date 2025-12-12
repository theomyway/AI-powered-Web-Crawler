"""Update opportunity categories to new standardized set.

Revision ID: 20241212_004
Revises: 003_progress_percent
Create Date: 2024-12-12

Old categories: dynamics, ai, iot, erp, staff_augmentation, cloud, cybersecurity, data_analytics, other
New categories: dynamics_365, ai, iot, erp, staff_augmentation, other_it

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '004_update_categories'
down_revision: Union[str, None] = '003_progress_percent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL enum types cannot be modified directly, so we need to:
    # 1. Add new enum values
    # 2. Update existing data to use new values
    # 3. Remove old enum values
    
    # Add new enum values first
    op.execute("ALTER TYPE opportunitycategory ADD VALUE IF NOT EXISTS 'dynamics_365'")
    op.execute("ALTER TYPE opportunitycategory ADD VALUE IF NOT EXISTS 'other_it'")
    
    # Commit the enum changes (required before using new values)
    op.execute("COMMIT")
    
    # Update existing data to use new category values
    # Map 'dynamics' to 'dynamics_365'
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'dynamics', 'dynamics_365')
        WHERE 'dynamics' = ANY(categories)
    """)
    
    # Map 'cloud', 'cybersecurity', 'data_analytics', 'other' to 'other_it'
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'cloud', 'other_it')
        WHERE 'cloud' = ANY(categories)
    """)
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'cybersecurity', 'other_it')
        WHERE 'cybersecurity' = ANY(categories)
    """)
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'data_analytics', 'other_it')
        WHERE 'data_analytics' = ANY(categories)
    """)
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'other', 'other_it')
        WHERE 'other' = ANY(categories)
    """)


def downgrade() -> None:
    # Revert to old category values
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'dynamics_365', 'dynamics')
        WHERE 'dynamics_365' = ANY(categories)
    """)
    op.execute("""
        UPDATE opportunities 
        SET categories = array_replace(categories, 'other_it', 'other')
        WHERE 'other_it' = ANY(categories)
    """)
    
    # Note: We cannot remove enum values in PostgreSQL without recreating the type
    # The old values will remain in the enum type

