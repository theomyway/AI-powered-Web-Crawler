"""Add company_info table

Revision ID: 20250128_007
Revises: 20250123_006_app_settings
Create Date: 2025-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007_add_company_info'
down_revision: Union[str, None] = '006_app_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'company_info',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(length=255), nullable=False),
        sa.Column('company_name', sa.String(length=500), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('street_address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('zip_code', sa.String(length=20), nullable=True),
        sa.Column('company_bio', sa.Text(), nullable=True),
        sa.Column('relevant_experience', sa.Text(), nullable=True),
        sa.Column('certifications', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create unique index on tenant_id (one company info per tenant)
    op.create_index('ix_company_info_tenant_id', 'company_info', ['tenant_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_company_info_tenant_id', table_name='company_info')
    op.drop_table('company_info')

