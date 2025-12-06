"""Initial schema - create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2024-12-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUM types
    op.execute("CREATE TYPE sourcetype AS ENUM ('government_portal', 'press_release', 'corporate_website', 'rss_feed', 'api')")
    op.execute("CREATE TYPE sourcestatus AS ENUM ('active', 'inactive', 'error', 'maintenance')")
    op.execute("CREATE TYPE opportunitystatus AS ENUM ('new', 'reviewing', 'qualified', 'not_relevant', 'applied', 'won', 'lost', 'expired', 'archived')")
    op.execute("CREATE TYPE opportunitycategory AS ENUM ('dynamics', 'ai', 'iot', 'erp', 'staff_augmentation', 'cloud', 'data_analytics', 'cybersecurity', 'other')")
    op.execute("CREATE TYPE crawlsessionstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE documenttype AS ENUM ('rfp', 'rfq', 'rfi', 'amendment', 'attachment', 'specification', 'contract', 'other')")
    op.execute("CREATE TYPE processingstatus AS ENUM ('pending', 'downloading', 'downloaded', 'processing', 'completed', 'failed')")

    # Create crawl_sources table
    op.create_table(
        'crawl_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('source_type', sa.Enum('government_portal', 'press_release', 'corporate_website', 'rss_feed', 'api', name='sourcetype', create_type=False), nullable=False),
        sa.Column('status', sa.Enum('active', 'inactive', 'error', 'maintenance', name='sourcestatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('county', sa.String(100), nullable=True),
        sa.Column('region', sa.String(100), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('search_url', sa.String(500), nullable=True),
        sa.Column('config', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('schedule_cron', sa.String(50), nullable=True),
        sa.Column('crawl_delay', sa.Float, nullable=False, server_default='2.0'),
        sa.Column('requires_auth', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('auth_config', postgresql.JSONB, nullable=True),
        sa.Column('is_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer, nullable=False, server_default='5'),
        sa.Column('last_crawl_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.Text, nullable=True),
        sa.Column('total_opportunities_found', sa.Integer, nullable=False, server_default='0'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_crawl_sources_state_code', 'crawl_sources', ['state_code'])
    op.create_index('ix_crawl_sources_source_type', 'crawl_sources', ['source_type'])
    op.create_index('ix_crawl_sources_is_enabled', 'crawl_sources', ['is_enabled'])

    # Create opportunities table
    op.create_table(
        'opportunities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('crawl_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_opportunity_id', sa.String(100), nullable=True),
        sa.Column('source_url', sa.String(1000), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('county', sa.String(100), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('department', sa.String(255), nullable=True),
        sa.Column('categories', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('relevance_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('status', sa.Enum('new', 'reviewing', 'qualified', 'not_relevant', 'applied', 'won', 'lost', 'expired', 'archived', name='opportunitystatus', create_type=False), nullable=False, server_default='new'),
        sa.Column('published_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submission_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('estimated_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('value_currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('requires_prequalification', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('prequalification_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_discretionary', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('contact_info', postgresql.JSONB, nullable=True),
        sa.Column('eligibility_requirements', sa.Text, nullable=True),
        sa.Column('certifications_required', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('raw_data', postgresql.JSONB, nullable=True),
        sa.Column('ai_analysis', postgresql.JSONB, nullable=True),
        sa.Column('internal_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_opportunities_source_id', 'opportunities', ['source_id'])
    op.create_index('ix_opportunities_state_code', 'opportunities', ['state_code'])
    op.create_index('ix_opportunities_status', 'opportunities', ['status'])
    op.create_index('ix_opportunities_submission_deadline', 'opportunities', ['submission_deadline'])
    op.create_index('ix_opportunities_created_at', 'opportunities', ['created_at'])
    op.create_unique_constraint('uq_opportunities_source_url', 'opportunities', ['source_url'])

    # Create crawl_sessions table
    op.create_table(
        'crawl_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('crawl_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', name='crawlsessionstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pages_crawled', sa.Integer, nullable=False, server_default='0'),
        sa.Column('opportunities_found', sa.Integer, nullable=False, server_default='0'),
        sa.Column('opportunities_new', sa.Integer, nullable=False, server_default='0'),
        sa.Column('opportunities_updated', sa.Integer, nullable=False, server_default='0'),
        sa.Column('documents_downloaded', sa.Integer, nullable=False, server_default='0'),
        sa.Column('errors_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('errors', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('last_error_message', sa.Text, nullable=True),
        sa.Column('config_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('triggered_by', sa.String(50), nullable=False, server_default='scheduler'),
        sa.Column('progress', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_crawl_sessions_source_id', 'crawl_sessions', ['source_id'])
    op.create_index('ix_crawl_sessions_status', 'crawl_sessions', ['status'])
    op.create_index('ix_crawl_sessions_created_at', 'crawl_sessions', ['created_at'])

    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('opportunity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('opportunities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('document_type', sa.Enum('rfp', 'rfq', 'rfi', 'amendment', 'attachment', 'specification', 'contract', 'other', name='documenttype', create_type=False), nullable=False, server_default='other'),
        sa.Column('source_url', sa.String(1000), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=True),
        sa.Column('sharepoint_item_id', sa.String(100), nullable=True),
        sa.Column('file_extension', sa.String(10), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger, nullable=True),
        sa.Column('checksum', sa.String(64), nullable=True),
        sa.Column('processing_status', sa.Enum('pending', 'downloading', 'downloaded', 'processing', 'completed', 'failed', name='processingstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('processing_error', sa.Text, nullable=True),
        sa.Column('extracted_text', sa.Text, nullable=True),
        sa.Column('ai_summary', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_documents_opportunity_id', 'documents', ['opportunity_id'])
    op.create_index('ix_documents_processing_status', 'documents', ['processing_status'])

    # Create prequalification_requirements table
    op.create_table(
        'prequalification_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('opportunity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('opportunities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requirement_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('registration_url', sa.String(500), nullable=True),
        sa.Column('portal_name', sa.String(255), nullable=True),
        sa.Column('is_mandatory', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('ai_confidence', sa.Numeric(3, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_prequalification_requirements_opportunity_id', 'prequalification_requirements', ['opportunity_id'])


def downgrade() -> None:
    op.drop_table('prequalification_requirements')
    op.drop_table('documents')
    op.drop_table('crawl_sessions')
    op.drop_table('opportunities')
    op.drop_table('crawl_sources')

    op.execute("DROP TYPE IF EXISTS processingstatus")
    op.execute("DROP TYPE IF EXISTS documenttype")
    op.execute("DROP TYPE IF EXISTS crawlsessionstatus")
    op.execute("DROP TYPE IF EXISTS opportunitycategory")
    op.execute("DROP TYPE IF EXISTS opportunitystatus")
    op.execute("DROP TYPE IF EXISTS sourcestatus")
    op.execute("DROP TYPE IF EXISTS sourcetype")

