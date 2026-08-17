"use client";

import { useState, useEffect } from "react";
import { listJobs } from "@/lib/api";
import type { Job } from "@/lib/types";

const PHASE_LABELS: Record<string, string> = {
  uploaded: "Diunggah",
  extracting: "Mengekstrak...",
  extracted: "Diekstrak",
  solving: "Menyelesaikan...",
  solved: "Selesai Dikerjakan",
  varying: "Membuat Variasi...",
  completed: "Selesai",
  failed: "Gagal",
};

const PHASE_COLORS: Record<string, string> = {
  uploaded: "bg-gray-100 text-gray-700",
  extracting: "bg-blue-100 text-blue-700",
  extracted: "bg-blue-100 text-blue-700",
  solving: "bg-yellow-100 text-yellow-700",
  solved: "bg-green-100 text-green-700",
  varying: "bg-purple-100 text-purple-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    const load = async () => {
      try {
        const data = await listJobs();
        setJobs(data);
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
  }, []);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 text-center text-gray-500">
        Memuat...
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Daftar Job</h1>
        <a href="/" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
          + Upload Baru
        </a>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm p-12 text-center text-gray-500">
          Belum ada job. Unggah PDF soal ujian untuk memulai.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <a
              key={job.id}
              href={`/jobs/${job.id}`}
              className="block bg-white rounded-lg shadow-sm p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">{job.filename}</div>
                  <div className="text-sm text-gray-500 mt-1">
                    {job.question_count} soal · {job.total_pages || "?"} halaman
                    {job.variation_count > 0 && ` · ${job.variation_count} variasi`}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${PHASE_COLORS[job.phase] || ""}`}>
                    {PHASE_LABELS[job.phase] || job.phase}
                  </span>
                  {job.phase !== "completed" && job.phase !== "failed" && (
                    <div className="w-16">
                      <div className="w-full bg-gray-200 rounded-full h-1.5">
                        <div
                          className="bg-blue-600 h-1.5 rounded-full transition-all"
                          style={{ width: `${job.progress * 100}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
              {job.error_message && (
                <div className="text-sm text-red-600 mt-2">{job.error_message}</div>
              )}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
