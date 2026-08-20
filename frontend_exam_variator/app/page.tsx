"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createJob } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [customInstruction, setCustomInstruction] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!file) return;
      setUploading(true);
      setError(null);
      try {
        const job = await createJob(file, customInstruction);
        router.push(`/jobs/${job.id}`);
      } catch (err: any) {
        setError(err.message || "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [file, customInstruction, router]
  );

  const maxSizeMB = 50;

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <div className="bg-white rounded-lg shadow-md p-8">
        <h1 className="text-2xl font-bold mb-2">Unggah Soal Ujian</h1>
        <p className="text-gray-600 mb-6">
          Unggah file PDF soal ujian untuk mengekstrak semua soal secara otomatis,
          lalu tinjau pembahasan AI dan buat variasi.
        </p>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              File PDF
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
                id="file-upload"
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                <div className="text-4xl mb-2">📄</div>
                <div className="text-gray-600">
                  {file ? (
                    <span className="text-green-600 font-medium">{file.name} ({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
                  ) : (
                    <span>Klik untuk memilih file PDF (maks {maxSizeMB}MB)</span>
                  )}
                </div>
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Instruksi Tambahan (Opsional)
            </label>
            <textarea
              value={customInstruction}
              onChange={(e) => setCustomInstruction(e.target.value)}
              placeholder="Contoh: Buat penyelesaian dengan konsep dasar..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              rows={3}
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!file || uploading}
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {uploading ? "Mengunggah..." : "Unggah & Ekstrak Soal"}
          </button>
        </form>
      </div>

      <div className="mt-8 text-center">
        <a href="/jobs" className="text-blue-600 hover:underline">
          Lihat Daftar Job →
        </a>
      </div>
    </div>
  );
}
