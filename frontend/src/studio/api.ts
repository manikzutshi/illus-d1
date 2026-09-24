import type { ComponentDetails, EditOp, ExampleInfo, JobInfo, LibraryItem, ProviderInfo, StudioDocument, StudioState } from './types';

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'OFFLINE', 'Cannot reach the studio server. Start it with: python -m cli.main studio serve');
  }
  const type = res.headers.get('content-type') || '';
  if (!res.ok) {
    if (type.includes('application/json')) {
      const data = await res.json();
      throw new ApiError(res.status, data?.error?.code ?? 'ERROR', data?.error?.message ?? res.statusText);
    }
    throw new ApiError(res.status, 'ERROR', res.statusText);
  }
  return (type.includes('application/json') ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  library: () => request<{ components: LibraryItem[] }>('GET', '/api/library').then(r => r.components),
  component: (id: string) => request<ComponentDetails>('GET', `/api/library/${encodeURIComponent(id)}`),
  examples: () => request<{ examples: ExampleInfo[] }>('GET', '/api/examples').then(r => r.examples),
  providers: () => request<{ providers: ProviderInfo[] }>('GET', '/api/providers').then(r => r.providers),
  openExample: (id: string) => request<StudioState>('POST', `/api/examples/${encodeURIComponent(id)}`),
  state: (document: StudioDocument) => request<StudioState>('POST', '/api/state', { document }),
  edit: (document: StudioDocument, ops: EditOp[]) => request<StudioState>('POST', '/api/edit', { document, ops }),
  exportSvg: (document: StudioDocument) => request<string>('POST', '/api/export/svg', { document }),
  generate: (prompt: string, provider?: string, model?: string) =>
    request<{ job_id: string }>('POST', '/api/generate', { prompt, provider, model }),
  job: (id: string) => request<JobInfo>('GET', `/api/jobs/${id}`),
};
