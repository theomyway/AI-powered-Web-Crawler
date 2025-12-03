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

export const opportunitiesApi = {
  list: async (page = 1, pageSize = 10, status?: string): Promise<PaginatedResponse<Opportunity>> => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
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

