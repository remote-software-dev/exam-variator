// API types matching backend Pydantic schemas

export type JobPhase =
  | "uploaded"
  | "extracting"
  | "extracted"
  | "solving"
  | "solved"
  | "varying"
  | "completed"
  | "failed";

export type QuestionType =
  | "Pilihan Ganda"
  | "Pilihan Ganda Kompleks"
  | "Kategori"
  | "Benar/Salah"
  | "Tepat/Tidak Tepat"
  | "Essay"
  | "Unknown";

export type ValidationStatus = "valid" | "warnings" | "invalid" | "unchecked";

export interface Question {
  question_id: string;
  page_number: number;
  question_type: QuestionType;
  question_text: string;
  options: string[];
  stimulus?: string;
  solution_by_concept?: string;
  solution_by_trick?: string;
  correct_answer?: string;
  extraction_method: string;
  confidence: number;
  needs_human_review: boolean;
  validation_status: ValidationStatus;
  validation_warnings: string[];
  is_verified_answer: boolean;
}

export interface VariationResult {
  original: Question;
  variations: {
    easy: Question | null;
    medium: Question | null;
    hard: Question | null;
  };
  page: number;
}

export interface Job {
  id: string;
  filename: string;
  phase: JobPhase;
  progress: number;
  total_pages: number | null;
  question_count: number;
  variation_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobDetail extends Job {
  custom_instruction: string;
  docx_path: string | null;
}
