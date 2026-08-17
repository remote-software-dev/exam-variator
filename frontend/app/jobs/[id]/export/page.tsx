"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { getJob, getVariations, triggerExport, getExportUrl } from "@/lib/api";
import type { JobDetail, VariationResult } from "@/lib/types";

export default function ExportPage() {
  const params = useParams();
  const jobId = params.id as string;
  const [job, setJob] = useState<JobDetail | null>(null);
  const [variations, setVariations] = useState<VariationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [jobData, varData] = await Promise.all([getJob(jobId), getVariations(jobId)]);
        setJob(jobData);
        setVariations(varData.variations);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [jobId]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setError(null);
    try {
      await triggerExport(jobId);
      // Poll for completion then download
      const checkDownload = async () => {
        try {
          const j = await getJob(jobId);
          if (j.docx_path) {
            window.open(getExportUrl(jobId), "_blank");
            setJob(j);
          } else {
            setTimeout(checkDownload, 2000);
          }
        } catch {
          setTimeout(checkDownload, 2000);
        }
      };
      setTimeout(checkDownload, 2000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }, [jobId]);

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-gray-500">Memuat...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Export ke Word</h1>
          <p className="text-sm text-gray-500">{variations.length} variasi siap diexport</p>
        </div>
        <a href={`/jobs/${jobId}/variations`} className="text-sm text-gray-500 hover:text-gray-700">
          ← Kembali ke Variasi
        </a>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">{error}</div>
      )}

      <div className="bg-white rounded-lg shadow-sm p-8 text-center">
        <div className="text-4xl mb-4">📄</div>
        <h2 className="text-lg font-semibold mb-2">Bank Soal & Variasi</h2>
        <p className="text-gray-600 mb-6">
          File Word akan berisi soal asli beserta variasi mudah, sedang, dan sulit
          untuk setiap soal yang dipilih.
        </p>

        {variations.length === 0 ? (
          <p className="text-gray-500 mb-6">Belum ada variasi untuk diexport.</p>
        ) : (
          <button
            onClick={handleExport}
            disabled={exporting}
            className="bg-green-600 text-white py-3 px-8 rounded-lg font-medium hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {exporting ? "Membuat DOCX..." : "Download DOCX"}
          </button>
        )}

        {job?.docx_path && (
          <div className="mt-4">
            <a
              href={getExportUrl(jobId)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              Download ulang
            </a>
          </div>
        )}
      </div>

      {/* Preview */}
      {variations.length > 0 && (
        <div className="mt-8 bg-white rounded-lg shadow-sm p-6">
          <h3 className="font-semibold mb-4">Pratinjau</h3>
          {variations.map((vr, idx) => (
            <div key={idx} className="border-b py-4 last:border-b-0">
              <div className="text-sm font-medium mb-1">Soal {idx + 1}</div>
              <div className="text-sm text-gray-700">{vr.original.question_text}</div>
              <div className="text-xs text-gray-400 mt-1">
                {Object.entries(vr.variations)
                  .filter(([, v]) => v)
                  .map(([k]) => DIFF_LABELS[k])
                  .join(" · ")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const DIFF_LABELS: Record<string, string> = {
  easy: "Mudah",
  medium: "Sedang",
  hard: "Sulit",
};
