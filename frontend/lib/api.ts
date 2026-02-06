const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// Dashboard
export async function getDashboardStats() {
  return fetchAPI<DashboardStats>("/api/dashboard/stats");
}

export async function getPipeline() {
  return fetchAPI<PipelineResponse>("/api/dashboard/pipeline");
}

// Leads
export async function getLeads(params?: {
  page?: number;
  per_page?: number;
  status?: string;
  min_score?: number;
}) {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.per_page) query.set("per_page", String(params.per_page));
  if (params?.status) query.set("status", params.status);
  if (params?.min_score) query.set("min_score", String(params.min_score));
  return fetchAPI<LeadListResponse>(`/api/leads?${query}`);
}

export async function getLead(id: string) {
  return fetchAPI<Lead>(`/api/leads/${id}`);
}

export async function updateLeadStatus(id: string, status: string, note?: string) {
  return fetchAPI<Lead>(`/api/leads/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, note }),
  });
}

// Letters
export async function getLetters(status?: string) {
  const query = status ? `?status=${status}` : "";
  return fetchAPI<LetterListResponse>(`/api/letters${query}`);
}

export async function approveLetter(id: string) {
  return fetchAPI<Letter>(`/api/letters/${id}/approve`, { method: "POST" });
}

export async function sendLetter(id: string) {
  return fetchAPI<Letter>(`/api/letters/${id}/send`, { method: "POST" });
}

// Planning
export async function getPlanningApps(params?: { page?: number; postcode?: string }) {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.postcode) query.set("postcode", params.postcode);
  return fetchAPI<PlanningApp[]>(`/api/planning?${query}`);
}

export async function triggerSync(daysBack: number = 7) {
  return fetchAPI<{ status: string; fetched?: number; new?: number }>(
    `/api/planning/sync?days_back=${daysBack}`,
    { method: "POST" }
  );
}

export async function addPlanningApp(params: {
  reference: string;
  address: string;
  postcode: string;
  description?: string;
  detail_url?: string;
  local_authority?: string;
}) {
  const query = new URLSearchParams();
  query.set("reference", params.reference);
  query.set("address", params.address);
  query.set("postcode", params.postcode);
  if (params.description) query.set("description", params.description);
  if (params.detail_url) query.set("detail_url", params.detail_url);
  if (params.local_authority) query.set("local_authority", params.local_authority);
  return fetchAPI<{ status: string; id: string; reference: string }>(
    `/api/planning/add?${query}`,
    { method: "POST" }
  );
}

export async function processApplication(appId: string) {
  return fetchAPI<{
    status: string;
    lead_score: number;
    letter_generated: boolean;
    extraction_confidence: number;
    agent_logs: string[];
    total_cost_gbp: number;
  }>(`/api/planning/process/${appId}`, { method: "POST" });
}

// Settings
export async function getSettings() {
  return fetchAPI<AppSettings>("/api/settings");
}

export async function updateSettings(data: Partial<SettingsUpdateRequest>) {
  return fetchAPI<{ status: string; message: string }>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function getAvailableCouncils() {
  return fetchAPI<{ councils: string[] }>("/api/settings/councils");
}

export async function getServiceTypes() {
  return fetchAPI<{
    all_types: string[];
    primary: string[];
    secondary: string[];
    exclude: string[];
  }>("/api/settings/service-types");
}

// Types
export interface AppSettings {
  company: {
    name: string;
    owner_name: string;
    trading_since: number;
    phone: string;
    email: string;
    website: string;
    office_address: string;
    company_registration: string;
    vat_number: string;
    credentials: string[];
  };
  services: {
    primary: string[];
    secondary: string[];
    exclude: string[];
  };
  geographic_area: {
    districts: string[];
    max_distance_km: number;
    borough_councils: string[];
  };
  lead_scoring: {
    weights: Record<string, number>;
    minimum_score: number;
    auto_send_threshold: number;
  };
  letter_settings: {
    auto_approve: boolean;
    include_case_studies: number;
  };
}

export interface SettingsUpdateRequest {
  company?: {
    name?: string;
    owner_name?: string;
    phone?: string;
    email?: string;
    website?: string;
    office_address?: string;
    company_registration?: string;
    vat_number?: string;
  };
  services?: {
    primary?: string[];
    secondary?: string[];
    exclude?: string[];
  };
  geographic_area?: {
    districts?: string[];
    max_distance_km?: number;
    borough_councils?: string[];
  };
  lead_scoring?: {
    weights?: Record<string, number>;
    minimum_score?: number;
    auto_send_threshold?: number;
  };
}

export interface DashboardStats {
  new_leads_today: number;
  total_leads: number;
  letters_pending: number;
  letters_sent: number;
  qr_scans_total: number;
  conversion_rate: number;
  pipeline_value: number;
  avg_lead_score: number;
}

export interface PipelineStage {
  stage: string;
  count: number;
  value: number;
}

export interface PipelineResponse {
  stages: PipelineStage[];
}

export interface Lead {
  id: string;
  planning_app_id: string;
  epc_id?: string;
  address: string;
  postcode: string;
  work_type?: string;
  work_description?: string;
  lead_score: number;
  score_breakdown: Record<string, any>;
  status: string;
  property_value_estimate?: number;
  distance_km?: number;
  unified_data: Record<string, any>;
  notes: any[];
  created_at: string;
  updated_at: string;
  contacted_at?: string;
  quoted_at?: string;
  won_at?: string;
}

export interface LeadListResponse {
  leads: Lead[];
  total: number;
  page: number;
  per_page: number;
}

export interface Letter {
  id: string;
  lead_id: string;
  content?: string;
  pdf_url?: string;
  status: string;
  qr_scan_count: number;
  generation_cost_gbp: number;
  print_cost_gbp: number;
  created_at: string;
  approved_at?: string;
  sent_at?: string;
}

export interface LetterListResponse {
  letters: Letter[];
  total: number;
}

export interface PlanningApp {
  id: string;
  reference: string;
  address: string;
  postcode: string;
  description?: string;
  application_type?: string;
  status?: string;
  submitted_date?: string;
  decision?: string;
  local_authority?: string;
  created_at: string;
}
