"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { getJob, getVariations } from "@/lib/api";
import type { JobDetail, VariationResult } from "@/lib/types";

const DIFFICULTY_LABELS: Record<string, { label: string; color: string }> = {
  easy: { label: "Mudah", color: "bg-green-100 text-green-700" },
  medium: { label: "Sedang", color: "bg-yellow-100 text-yellow-700" },
  hard: { label: "Sulit", color: "bg-red-100 text-red-700" },
};

export default function VariationsPage() {
  const params = useParams();
  const jobId = params.id as string;
  const [job, setJob] = useState<JobDetail | null>(null);
  const [variations, setVariations] = useState<VariationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    const load = async () => {
      try {
        const [jobData, varData] = await Promise.all([getJob(jobId), getVariations(jobId)]);
        setJob(jobData);
        setVariations(varData.variations);
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

  const isProcessing = job?.phase === "varying";

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-gray-500">Memuat...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Variasi Soal</h1>
          <p className="text-sm text-gray-500">{variations.length} variasi berhasil dibuat</p>
        </div>
        <div className="flex gap-2">
          <a href={`/jobs/${jobId}`} className="text-sm text-gray-500 hover:text-gray-700">← Kembali ke Soal</a>
          <a href={`/jobs/${jobId}/export`} className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700">
            Export DOCX →
          </a>
        </div>
      </div>

      {isProcessing && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg mb-4">
          Membuat variasi... {(job!.progress * 100).toFixed(0)}%
          <div className="w-full bg-blue-200 rounded-full h-1.5 mt-2">
            <div className="bg-blue-600 h-1.5 rounded-full transition-all" style={{ width: `${job!.progress * 100}%` }} />
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">{error}</div>
      )}

      {variations.length === 0 && !isProcessing && (
        <div className="bg-white rounded-lg shadow-sm p-12 text-center text-gray-500">
          Belum ada variasi. Kembali ke halaman soal untuk membuat variasi.
        </div>
      )}

      <div className="space-y-6">
        {variations.map((vr, idx) => (
          <div key={idx} className="bg-white rounded-lg shadow-sm p-6">
            <div className="mb-4">
              <h3 className="font-medium text-sm text-gray-500 mb-2">Soal Asli</h3>
              <div className="text-sm">{vr.original.question_text}</div>
              {vr.original.options.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {vr.original.options.map((opt, i) => (
                    <div key={i} className="text-sm text-gray-600">{String.fromCharCode(65 + i)}. {opt}</div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(["easy", "medium", "hard"] as const).map((level) => {
                const q = vr.variations[level];
                const { label, color } = DIFFICULTY_LABELS[level];
                return (
                  <div key={level} className="border rounded-lg p-4">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${color}`}>{label}</span>
                    {q ? (
                      <div className="mt-2">
                        <div className="text-sm">{q.question_text}</div>
                        {q.options.length > 0 && (
                          <div className="mt-1 space-y-0.5">
                            {q.options.map((opt, i) => (
                              <div key={i} className="text-xs text-gray-600">{String.fromCharCode(65 + i)}. {opt}</div>
                            ))}
                          </div>
                        )}
                        {q.solution_by_concept && (
                          <details className="mt-2">
                            <summary className="text-xs text-blue-600 cursor-pointer">Pembahasan Konsep</summary>
                            <p className="text-xs text-gray-600 mt-1">{q.solution_by_concept}</p>
                          </details>
                        )}
                        {q.solution_by_trick && (
                          <details className="mt-1">
                            <summary className="text-xs text-blue-600 cursor-pointer">Cara Cepat</summary>
                            <p className="text-xs text-gray-600 mt-1">{q.solution_by_trick}</p>
                          </details>
                        )}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-gray-400 italic">Tidak tersedia</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
