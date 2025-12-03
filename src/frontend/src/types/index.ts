// Types matching the backend Pydantic schemas

export interface DashboardStats {
  total_opportunities: number;
  new_this_week: number;
  new_this_month: number;
  active_opportunities: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_state: Record<string, number>;
  requiring_prequalification: number;
  discretionary: number;
  deadlines_this_week: number;
  deadlines_next_week: number;
  expired: number;
  average_relevance_score: number | null;
  total_sources: number;
  active_sources: number;
}

export type OpportunityStatus = 'new' | 'reviewing' | 'qualified' | 'applied' | 'rejected' | 'expired' | 'archived';

export interface Opportunity {
  id: string;
  source_id: string;
  external_id: string | null;
  title: string;
  description: string | null;
  summary: string | null;
  department: string | null;
  agency: string | null;
  category: string | null;
  categories: string[] | null;
  source_url: string;
  state_code: string | null;
  county: string | null;
  city: string | null;
  published_date: string | null;
  submission_deadline: string | null;
  estimated_value: number | null;
  value_currency: string;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  requires_prequalification: boolean;
  is_discretionary: boolean;
  status: OpportunityStatus;
  relevance_score: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export type CrawlSessionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface CrawlSession {
  id: string;
  source_id: string;
  status: CrawlSessionStatus;
  started_at: string | null;
  completed_at: string | null;
  opportunities_found: number;
  opportunities_new: number;
  opportunities_updated: number;
  pages_crawled: number;
  errors_count: number;
  last_error_message: string | null;
  created_at: string;
}

export type SourceStatus = 'active' | 'paused' | 'disabled' | 'error';

export interface CrawlSource {
  id: string;
  name: string;
  source_type: string;
  state_code: string | null;
  county: string | null;
  base_url: string;
  status: SourceStatus;
  is_enabled: boolean;
  priority: number;
  last_crawl_at: string | null;
  last_success_at: string | null;
  total_opportunities_found: number;
  created_at: string;
  updated_at: string;
}

