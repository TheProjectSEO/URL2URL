const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// API response format from backend
interface ApiJob {
  id: string;
  name: string;
  site_a_url: string;
  site_b_url: string;
  categories?: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  total_matches?: number;
  high_confidence_matches?: number;
  needs_review_count?: number;
  products_site_a?: number;
  products_site_b?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

// Frontend-friendly Job interface
export interface Job {
  id: string;
  name: string;
  site1_url: string;
  site2_url: string;
  site1_category?: string;
  site2_category?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  total_products?: number;
  matched_products?: number;
  progress?: number;
  created_at: string;
  updated_at?: string;
}

// Transform API response to frontend format
function transformApiJob(apiJob: ApiJob): Job {
  return {
    id: apiJob.id,
    name: apiJob.name,
    site1_url: apiJob.site_a_url,
    site2_url: apiJob.site_b_url,
    site1_category: apiJob.categories?.[0],
    site2_category: apiJob.categories?.[1],
    status: apiJob.status,
    total_products: (apiJob.products_site_a || 0) + (apiJob.products_site_b || 0),
    matched_products: apiJob.total_matches || 0,
    created_at: apiJob.created_at,
    updated_at: apiJob.completed_at || apiJob.started_at || apiJob.created_at,
  };
}

export interface CreateJobRequest {
  name: string;
  site1_url: string;
  site2_url: string;
  site1_category?: string;
  site2_category?: string;
}

// Transform frontend field names to API field names
interface ApiCreateJobRequest {
  name: string;
  site_a_url: string;
  site_b_url: string;
  categories?: string[];
}

export interface Match {
  id: string;
  job_id: string;
  source_product_id: string;
  matched_product_id: string;
  source_title: string;
  source_url: string;
  matched_title: string;
  matched_url: string;
  score: number;
  confidence_tier: 'exact_match' | 'high_confidence' | 'good_match' | 'likely_match' | 'manual_review' | 'no_match';
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export interface JobStats {
  total_jobs: number;
  active_jobs: number;
  completed_jobs: number;
  total_matches: number;
  approved_matches: number;
}

export interface CSVUploadResponse {
  uploaded: number;
  failed: number;
  job_id: string;
  errors: string[];
}

const handleResponse = async (response: Response) => {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || error.message || 'An error occurred');
  }
  return response.json();
};

export const api = {
  jobs: {
    list: async (): Promise<Job[]> => {
      const response = await fetch(`${API_URL}/api/jobs`);
      const data = await handleResponse(response);
      // API returns paginated response {items: ApiJob[], total: number, ...}
      const items: ApiJob[] = Array.isArray(data) ? data : (data.items || []);
      return items.map(transformApiJob);
    },

    get: async (id: string): Promise<Job> => {
      const response = await fetch(`${API_URL}/api/jobs/${id}`);
      const apiJob: ApiJob = await handleResponse(response);
      return transformApiJob(apiJob);
    },

    create: async (data: CreateJobRequest): Promise<Job> => {
      // Transform frontend field names to API field names
      const categories: string[] = [];
      if (data.site1_category) categories.push(data.site1_category);
      if (data.site2_category) categories.push(data.site2_category);

      const apiData: ApiCreateJobRequest = {
        name: data.name,
        site_a_url: data.site1_url,
        site_b_url: data.site2_url,
        categories: categories.length > 0 ? categories : undefined,
      };

      const response = await fetch(`${API_URL}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiData),
      });
      const apiJob: ApiJob = await handleResponse(response);
      return transformApiJob(apiJob);
    },

    run: async (id: string): Promise<{ message: string }> => {
      // Use /run-background endpoint which uses products already in DB (from CSV upload)
      // The /run endpoint requires products in request body, which is for inline data
      const response = await fetch(`${API_URL}/api/jobs/${id}/run-background`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      return handleResponse(response);
    },

    matches: async (id: string): Promise<Match[]> => {
      const response = await fetch(`${API_URL}/api/jobs/${id}/matches`);
      const data = await handleResponse(response);
      // API may return paginated response {items: Match[], total: number, ...}
      return Array.isArray(data) ? data : (data.items || []);
    },

    delete: async (id: string): Promise<void> => {
      const response = await fetch(`${API_URL}/api/jobs/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to delete job' }));
        throw new Error(error.detail || 'Failed to delete job');
      }
    },
  },

  matches: {
    update: async (id: string, status: 'approved' | 'rejected'): Promise<Match> => {
      const response = await fetch(`${API_URL}/api/matches/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      return handleResponse(response);
    },
  },

  stats: {
    get: async (): Promise<JobStats> => {
      const response = await fetch(`${API_URL}/api/stats`);
      return handleResponse(response);
    },
  },

  upload: {
    /**
     * Upload CSV file with product URLs for a job.
     * @param jobId - The job ID to add products to
     * @param site - Either "site_a" (source products) or "site_b" (catalog to match against)
     * @param file - CSV file with at least a 'url' column
     */
    csv: async (jobId: string, site: 'site_a' | 'site_b', file: File): Promise<CSVUploadResponse> => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/api/upload/products/${jobId}/${site}`, {
        method: 'POST',
        body: formData,
      });
      return handleResponse(response);
    },

    /**
     * Get CSV template format information
     */
    getTemplate: async (): Promise<{ format: string; required_columns: string[]; optional_columns: string[]; example: string }> => {
      const response = await fetch(`${API_URL}/api/upload/template`);
      return handleResponse(response);
    },
  },
};
