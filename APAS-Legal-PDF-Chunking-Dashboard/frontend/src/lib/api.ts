const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API request failed');
  }
  return res.json();
}

export async function uploadPDF(file: File, enrich: boolean = true) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('enrich', String(enrich));
  return fetchAPI('/upload', { method: 'POST', body: formData });
}

export async function getJobs() {
  return fetchAPI('/jobs');
}

export async function getJob(jobId: string) {
  return fetchAPI(`/jobs/${jobId}`);
}

export async function getJobStats(jobId: string) {
  return fetchAPI(`/jobs/${jobId}/stats`);
}

export async function getJobChunks(
  jobId: string,
  page: number = 1,
  pageSize: number = 50,
  contentType?: string,
  search?: string,
) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (contentType) params.set('content_type', contentType);
  if (search) params.set('search', search);
  return fetchAPI(`/jobs/${jobId}/chunks?${params}`);
}

export async function getHierarchyTree(jobId: string) {
  return fetchAPI(`/jobs/${jobId}/tree`);
}

export async function pushToNeo4j(jobId: string) {
  return fetchAPI(`/jobs/${jobId}/push`, { method: 'POST' });
}

export async function getNeo4jStatus() {
  return fetchAPI('/neo4j/status');
}

export async function runCypherQuery(query: string) {
  return fetchAPI('/neo4j/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
}

export async function clearNeo4jData(jobId: string) {
  return fetchAPI(`/jobs/${jobId}/neo4j`, { method: 'DELETE' });
}

export async function exportChunks(jobId: string) {
  return fetchAPI(`/jobs/${jobId}/export`, { method: 'POST' });
}

export async function getExportDir() {
  return fetchAPI('/export-dir');
}

export function downloadChunksUrl(jobId: string) {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return `${base}/jobs/${jobId}/download`;
}

export async function getLogs() {
  return fetchAPI('/logs');
}
