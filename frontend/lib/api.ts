// API client with env-based base URL

import type { Job, JobDetail, Question, VariationResult } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// Jobs
export async function createJob(file: File, customInstruction = ""): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  form.append("custom_instruction", customInstruction);
  const res = await fetch(`${BASE_URL}/api/jobs`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listJobs(limit = 50, offset = 0): Promise<Job[]> {
  return request<Job[]>(`/api/jobs?limit=${limit}&offset=${offset}`);
}

export async function getJob(jobId: string): Promise<JobDetail> {
  return request<JobDetail>(`/api/jobs/${jobId}`);
}

// Questions
export async function getQuestions(jobId: string): Promise<{ questions: Question[]; total: number }> {
  return request(`/api/jobs/${jobId}/questions`);
}

export async function getQuestion(jobId: string, qid: string): Promise<Question> {
  return request<Question>(`/api/jobs/${jobId}/questions/${qid}`);
}

export async function updateQuestion(
  jobId: string,
  qid: string,
  updates: Partial<Pick<Question, "question_text" | "options" | "correct_answer" | "stimulus">>
): Promise<Question> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/questions/${qid}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function selectQuestion(jobId: string, qid: string): Promise<void> {
  await request(`/api/jobs/${jobId}/questions/${qid}/select`, { method: "POST" });
}

export async function bulkSelectQuestions(jobId: string, indices: number[]): Promise<Job> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected_indices: indices }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// Variations
export async function triggerVariations(jobId: string, customInstruction = ""): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/variations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ custom_instruction: customInstruction }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
}

export async function getVariations(
  jobId: string
): Promise<{ variations: VariationResult[]; total: number }> {
  return request(`/api/jobs/${jobId}/variations`);
}

// Export
export async function triggerExport(jobId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/export`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
}

export function getExportUrl(jobId: string): string {
  return `${BASE_URL}/api/jobs/${jobId}/export`;
}

// Health
export async function healthCheck(): Promise<{ status: string; version: string }> {
  return request("/health");
}
