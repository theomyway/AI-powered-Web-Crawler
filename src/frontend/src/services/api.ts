import axios from 'axios';
import type { DashboardStats, Opportunity, CrawlSession, CrawlSource, PaginatedResponse } from '../types';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    const response = await api.get<DashboardStats>('/dashboard/stats');
    return response.data;
  },
};

export interface OpportunityFilters {
  page?: number;
  page_size?: number;
  status?: string[];
  categories?: string[];
  state_codes?: string[];
  requires_prequalification?: boolean;
  is_discretionary?: boolean;
  deadline_after?: string;
  deadline_before?: string;
  search?: string;
  source_id?: string;
  sort_by?: 'created_at' | 'deadline' | 'relevance' | 'title';
  sort_order?: 'asc' | 'desc';
}

export const opportunitiesApi = {
  list: async (page = 1, pageSize = 10, status?: string): Promise<PaginatedResponse<Opportunity>> => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const response = await api.get<PaginatedResponse<Opportunity>>('/opportunities', { params });
    return response.data;
  },

  listWithFilters: async (filters: OpportunityFilters): Promise<PaginatedResponse<Opportunity>> => {
    const params: Record<string, unknown> = {
      page: filters.page || 1,
      page_size: filters.page_size || 20,
    };

    if (filters.search) params.search = filters.search;
    if (filters.categories?.length) params.categories = filters.categories;
    if (filters.status?.length) params.status = filters.status;
    if (filters.state_codes?.length) params.state_codes = filters.state_codes;
    if (filters.requires_prequalification !== undefined) params.requires_prequalification = filters.requires_prequalification;
    if (filters.is_discretionary !== undefined) params.is_discretionary = filters.is_discretionary;
    if (filters.deadline_after) params.deadline_after = filters.deadline_after;
    if (filters.deadline_before) params.deadline_before = filters.deadline_before;
    if (filters.source_id) params.source_id = filters.source_id;
    if (filters.sort_by) params.sort_by = filters.sort_by;
    if (filters.sort_order) params.sort_order = filters.sort_order;

    const response = await api.get<PaginatedResponse<Opportunity>>('/opportunities', { params });
    return response.data;
  },

  get: async (id: string): Promise<Opportunity> => {
    const response = await api.get<Opportunity>(`/opportunities/${id}`);
    return response.data;
  },
};

export const crawlApi = {
  getSessions: async (page = 1, pageSize = 10): Promise<PaginatedResponse<CrawlSession>> => {
    const response = await api.get<PaginatedResponse<CrawlSession>>('/crawl/sessions', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  triggerCrawl: async (sourceId: string): Promise<CrawlSession> => {
    const response = await api.post<CrawlSession>(`/crawl/trigger/${sourceId}`);
    return response.data;
  },
};

export const sourcesApi = {
  list: async (page = 1, pageSize = 10): Promise<PaginatedResponse<CrawlSource>> => {
    const response = await api.get<PaginatedResponse<CrawlSource>>('/sources', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },
};

export default api;

