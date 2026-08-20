"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getJob, getQuestions, updateQuestion, bulkSelectQuestions, triggerVariations } from "@/lib/api";
import { cleanAiText } from "@/lib/format";
import type { JobDetail, Question } from "@/lib/types";

const TYPE_BADGES: Record<string, { label: string; color: string }> = {
  "Pilihan Ganda": { label: "PG", color: "bg-blue-100 text-blue-700" },
  "Pilihan Ganda Kompleks": { label: "MCMA", color: "bg-purple-100 text-purple-700" },
  Kategori: { label: "Kategori", color: "bg-teal-100 text-teal-700" },
  "Benar/Salah": { label: "B/S", color: "bg-orange-100 text-orange-700" },
  "Tepat/Tidak Tepat": { label: "T/TT", color: "bg-amber-100 text-amber-700" },
  Essay: { label: "Essay", color: "bg-gray-200 text-gray-700" },
  Unknown: { label: "?", color: "bg-gray-100 text-gray-500" },
};

const VALIDATION_COLORS: Record<string, string> = {
  valid: "text-green-600",
  warnings: "text-yellow-600",
  invalid: "text-red-600",
  unchecked: "text-gray-400",
};

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const [job, setJob] = useState<JobDetail | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [editingQid, setEditingQid] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customInstruction, setCustomInstruction] = useState("");

  // Poll job status
  useEffect(() => {
    let interval: NodeJS.Timeout;
    const load = async () => {
      try {
        const [jobData, qData] = await Promise.all([getJob(jobId), getQuestions(jobId)]);
        setJob(jobData);
        setQuestions(qData.questions);
        setSelected(new Set(Array.from({ length: qData.total }, (_, i) => i)));
        setError(null);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
    interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, [jobId]);

  const isProcessing = job && !["completed", "failed", "solved", "uploaded"].includes(job.phase);

  const toggleSelect = useCallback(
    (idx: number) => {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(idx)) next.delete(idx);
        else next.add(idx);
        return next;
      });
    },
    []
  );

  const handleSaveEdit = useCallback(async () => {
    if (!editingQid) return;
    try {
      const updated = await updateQuestion(jobId, editingQid, { question_text: editText });
      setQuestions((prev) => prev.map((q) => (q.question_id === editingQid ? { ...q, ...updated } : q)));
      setEditingQid(null);
    } catch (err: any) {
      setError(err.message);
    }
  }, [jobId, editingQid, editText]);

  const handleBulkSelect = useCallback(async () => {
    try {
      await bulkSelectQuestions(jobId, Array.from(selected));
      setError(null);
    } catch (err: any) {
      setError(err.message);
    }
  }, [jobId, selected]);

  const handleGenerateVariations = useCallback(async () => {
    try {
      await triggerVariations(jobId, customInstruction);
      router.push(`/jobs/${jobId}/variations`);
    } catch (err: any) {
      setError(err.message);
    }
  }, [jobId, customInstruction, router]);

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-gray-500">Memuat...</div>;
  }

  if (!job) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-red-500">Job tidak ditemukan</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold">{job.filename}</h1>
            <div className="text-sm text-gray-500 mt-1">
              {questions.length} soal diekstrak · {selected.size} dipilih
            </div>
          </div>
          <div className="flex gap-2">
            <a href="/jobs" className="text-sm text-gray-500 hover:text-gray-700">← Kembali</a>
          </div>
        </div>

        {/* Progress */}
        {isProcessing && (
          <div className="mb-4">
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div className="bg-blue-600 h-2 rounded-full transition-all" style={{ width: `${job.progress * 100}%` }} />
            </div>
            <div className="text-sm text-gray-500 mt-1">{job.phase}...</div>
          </div>
        )}

        {job.error_message && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">{job.error_message}</div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">{error}</div>
        )}
      </div>

      {/* Questions */}
      <div className="space-y-4">
        {questions.map((q, idx) => {
          const badge = TYPE_BADGES[q.question_type] || TYPE_BADGES.Unknown;
          return (
            <div key={q.question_id} className="bg-white rounded-lg shadow-sm p-5">
              <div className="flex items-start gap-4">
                <input
                  type="checkbox"
                  checked={selected.has(idx)}
                  onChange={() => toggleSelect(idx)}
                  className="mt-1 h-5 w-5 rounded"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium text-sm">Soal {idx + 1}</span>
                    {q.page_number > 0 && (
                      <span className="text-xs text-gray-400">Hal. {q.page_number}</span>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.color}`}>
                      {badge.label}
                    </span>
                    <span className={`text-xs ${VALIDATION_COLORS[q.validation_status]}`}>
                      {q.validation_status === "valid" && "✓ Valid"}
                      {q.validation_status === "warnings" && "⚠ Peringatan"}
                      {q.validation_status === "invalid" && "✕ Invalid"}
                      {q.validation_status === "unchecked" && "? Belum dicek"}
                    </span>
                    {q.needs_human_review && (
                      <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                        Perlu Review
                      </span>
                    )}
                  </div>

                  {editingQid === q.question_id ? (
                    <div className="mb-2">
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="w-full border rounded px-2 py-1 text-sm"
                        rows={3}
                      />
                      <div className="flex gap-2 mt-1">
                        <button onClick={handleSaveEdit} className="text-xs bg-green-100 text-green-700 px-3 py-1 rounded">Simpan</button>
                        <button onClick={() => setEditingQid(null)} className="text-xs bg-gray-100 text-gray-700 px-3 py-1 rounded">Batal</button>
                      </div>
                    </div>
                  ) : (
                    <div
                      className="text-sm cursor-pointer hover:bg-gray-50 rounded p-1 -ml-1"
                      onClick={() => { setEditingQid(q.question_id); setEditText(q.question_text); }}
                    >
                      {q.question_text}
                    </div>
                  )}

                  {q.options.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {q.options.map((opt, i) => (
                        <div key={i} className="text-sm text-gray-600">
                          {String.fromCharCode(65 + i)}. {opt}
                        </div>
                      ))}
                    </div>
                  )}

                  {(q.solution_by_concept || q.solution_by_trick) && (
                    <details className="mt-3">
                      <summary className="text-sm text-blue-600 cursor-pointer">Pembahasan AI</summary>
                      <div className="mt-2 space-y-2 text-sm text-gray-600 whitespace-pre-line">
                        {q.solution_by_concept && (
                          <div><strong>Konsep Dasar:</strong> {cleanAiText(q.solution_by_concept)}</div>
                        )}
                        {q.solution_by_trick && (
                          <div><strong>Cara Cepat:</strong> {cleanAiText(q.solution_by_trick)}</div>
                        )}
                      </div>
                    </details>
                  )}

                  {q.validation_warnings.length > 0 && (
                    <div className="mt-2 text-xs text-yellow-600">
                      {q.validation_warnings.join("; ")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Actions */}
      {questions.length > 0 && (
        <div className="mt-6 bg-white rounded-lg shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium">
              {selected.size} dari {questions.length} soal dipilih
            </span>
            <button onClick={handleBulkSelect} className="text-sm bg-gray-100 px-3 py-1 rounded hover:bg-gray-200">
              Simpan Pilihan
            </button>
          </div>

          <div className="mb-4">
            <textarea
              value={customInstruction}
              onChange={(e) => setCustomInstruction(e.target.value)}
              placeholder="Instruksi tambahan untuk variasi (opsional)..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              rows={2}
            />
          </div>

          <button
            onClick={handleGenerateVariations}
            disabled={selected.size === 0}
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            Buat Variasi untuk Soal Terpilih ({selected.size} soal)
          </button>
        </div>
      )}
    </div>
  );
}
