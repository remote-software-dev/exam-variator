import json as _json
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from exam_generator.latex_utils import normalize_latex

st.set_page_config(page_title="Generator Variasi Soal", layout="centered")
st.title("🎓 Generator Variasi Soal")
st.markdown("Unggah PDF soal ujian untuk mengekstrak semua soal secara otomatis, meninjau pembahasan AI untuk setiap soal, lalu pilih soal yang ingin divariasikan dan unduh hasilnya dalam bentuk Word.")

PDF_PATH = "data/inputs/uploaded_exam.pdf"
OUTPUT_PATH = "data/outputs/final_pipeline_result.docx"

# How much of the progress bar each phase owns, in order of execution.
STAGE_FRACTIONS = {
    "extract": (0.0, 0.4),
    "solve": (0.4, 0.75),
    "vary": (0.75, 1.0),
}


def _stage_frac(stage, current, total):
    lo, hi = STAGE_FRACTIONS.get(stage, (0.0, 1.0))
    return lo + (hi - lo) * (current / max(total, 1))


def _render_solution(body, title_md="**Penyelesaian**"):
    """Render AI solution text, normalizing LaTeX so formulas render properly."""
    st.markdown(f"{title_md}\n\n{normalize_latex(body)}", unsafe_allow_html=True)


def _render_preview():
    """Live preview of the collected results (st.markdown renders $...$ LaTeX)."""
    results_json = OUTPUT_PATH.rsplit(".", 1)[0] + ".json"
    if not os.path.exists(results_json):
        return
    with open(results_json, encoding="utf-8") as f:
        results = _json.load(f)

    st.divider()
    st.subheader("📄 Pratinjau Hasil")
    for idx, q in enumerate(results.get("questions", []), 1):
        page_note = f" (Halaman {q['page']})" if q.get("page") else ""
        st.markdown(f"### Soal {idx}{page_note}")
        original = q.get("original", {})
        if original.get("id"):
            st.caption(f"ID: {original['id']}")
        st.markdown(original.get("question_text", ""))
        options = original.get("options") or []
        if options:
            for i, opt in enumerate(options):
                st.markdown(f"{chr(65 + i)}. {opt}")
        for variant in ("easier", "harder"):
            label = "Mudah" if variant == "easier" else "Sulit"
            v = q.get("variations", {}).get(variant)
            if not v:
                continue
            st.markdown(f"**Variasi Lebih {label}**\n\n{normalize_latex(v.get('question_text', ''))}")
            for i, opt in enumerate(v.get("options") or []):
                st.markdown(f"- **{chr(65 + i)}.** {opt}")
            for key, title in (("solution_by_concept", "Penyelesaian (Konsep Dasar)"),
                               ("solution_by_trick", "Penyelesaian (Cara Cepat/Trik)")):
                solution = v.get(key)
                if solution:
                    _render_solution(solution, f"*{title}*")


def _render_download_and_preview():
    """Offer the finished Word download and preview the results."""
    if os.path.exists(OUTPUT_PATH):
        st.success("✅ Pemrosesan selesai!")
        with open(OUTPUT_PATH, "rb") as file:
            st.download_button(
                label="⬇️ Download Hasil Akhir Dokumen Word",
                data=file,
                file_name="Bank_Soal_Variasi.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    _render_preview()


def _save_uploaded_pdf(uploaded_file):
    upload_key = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("upload_key") != upload_key:
        for flag in ("extraction_started", "variation_done", "questions_log",
                     "current_page", "current_idx", "total_pages",
                     "review_complete", "selected_questions"):
            st.session_state.pop(flag, None)
        for key in [k for k in st.session_state.keys() if k.startswith("sel_")]:
            st.session_state.pop(key, None)
        st.session_state.upload_key = upload_key
    with open(PDF_PATH, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.session_state.pdf_ready = True


def _run_first_extraction(custom_instruction):
    """Extract ONLY the first page's questions (auto-skipping empty pages)."""
    from exam_generator.pipeline import (
        get_pdf_page_count,
        extract_page_questions,
        solve_questions,
    )
    with st.status("🔄 Mengekstrak Soal Pertama...", expanded=True) as status:
        try:
            total_pages = get_pdf_page_count(PDF_PATH)

            def _on_status(message):
                status.update(label="⏳ Menunggu batas rate limit...")
                status.write(message)

            page = 1
            page_qs = []
            while page <= total_pages:
                status.update(label=f"🔄 Mengekstrak halaman {page} dari {total_pages}...")
                page_qs = extract_page_questions(
                    PDF_PATH,
                    page,
                    custom_instruction=custom_instruction,
                    status_callback=_on_status,
                )
                if page_qs:
                    break
                page += 1

            if not page_qs:
                raise RuntimeError(
                    "Tidak ada soal yang berhasil diekstrak. Cek log di atas."
                )

            status.update(label="🔄 Menyelesaikan pembahasan soal...")
            solve_questions(
                page_qs,
                custom_instruction=custom_instruction,
                status_callback=_on_status,
            )

            st.session_state.questions_log = page_qs
            st.session_state.current_page = page
            st.session_state.total_pages = total_pages
            st.session_state.current_idx = 0
            st.session_state.extraction_started = True
            st.session_state.review_complete = False
            status.update(
                label=f"✅ Soal 1 siap! Halaman {page} dari {total_pages}.",
                state="complete",
            )
        except Exception as e:
            status.update(label="❌ Terjadi kesalahan.", state="error")
            st.error(str(e))


def _advance(custom_instruction):
    """Move to the next question; extract the NEXT page only when the current
    page's questions are exhausted (true one-at-a-time processing)."""
    from exam_generator.pipeline import extract_page_questions, solve_questions
    log = st.session_state.questions_log
    current_idx = st.session_state.get("current_idx", 0)
    current_page = st.session_state.get("current_page", 1)
    total_pages = st.session_state.get("total_pages", 1)

    # Next question is already in the log (same page) -> no AI call needed.
    if current_idx + 1 < len(log):
        st.session_state.current_idx = current_idx + 1
        return

    with st.status("🔄 Mengekstrak Soal Berikutnya...", expanded=False) as status:
        def _on_status(message):
            status.update(label="⏳ Menunggu batas rate limit...")
            status.write(message)

        page = current_page + 1
        while page <= total_pages:
            status.update(label=f"🔄 Mengekstrak halaman {page} dari {total_pages}...")
            page_qs = extract_page_questions(
                PDF_PATH,
                page,
                custom_instruction=custom_instruction,
                status_callback=_on_status,
            )
            if page_qs:
                status.update(label="🔄 Menyelesaikan pembahasan soal...")
                solve_questions(
                    page_qs,
                    custom_instruction=custom_instruction,
                    status_callback=_on_status,
                )
                log.extend(page_qs)
                st.session_state.current_page = page
                st.session_state.current_idx = len(log) - 1
                status.update(
                    label=f"✅ Halaman {page} selesai: {len(page_qs)} soal.",
                    state="complete",
                )
                return
            page += 1

        # Every remaining page is empty — finish the review.
        st.session_state.current_page = total_pages
        st.session_state.current_idx = len(log) - 1
        st.session_state.review_complete = True
        status.update(label="✅ Semua halaman sudah diekstrak.", state="complete")


def _run_variation(custom_instruction):
    """Phase 2: generate variations for the user-selected questions and export."""
    from exam_generator.pipeline import generate_variation_results, export_results
    with st.status("🔄 Membuat Variasi Soal...", expanded=True) as status:
        progress = st.progress(0.0, text="Memulai...")
        try:
            selected = st.session_state.selected_questions
            last_frac = {"v": 0.0}

            def _on_progress(current, total, stage, message=None):
                last_frac["v"] = min(max(_stage_frac(stage, current, total), 0.0), 1.0)
                progress.progress(last_frac["v"], text=message or "")
                status.write(message or "")
                if stage == "vary":
                    status.update(label="🔄 Membuat Variasi Soal...")

            def _on_status(message):
                progress.progress(last_frac["v"], text=message)
                status.update(label="⏳ Menunggu batas rate limit...")
                status.write(message)

            results = generate_variation_results(
                selected,
                custom_instruction=custom_instruction,
                progress_callback=_on_progress,
                status_callback=_on_status,
            )
            export_results(results, OUTPUT_PATH)
            progress.progress(1.0, text="✅ Selesai!")
            status.update(label="✅ Variasi selesai dibuat!", state="complete")
        except Exception as e:
            status.update(label="❌ Terjadi kesalahan.", state="error")
            st.error(str(e))


def _render_question(idx, q):
    """Render a single question with its select checkbox and AI solution."""
    page_note = f" (Halaman {q['page']})" if q.get("page") else ""
    st.markdown(f"### Soal {idx + 1}{page_note}")
    if q.get("id"):
        st.caption(f"ID: {q['id']}")
    st.markdown(q.get("question_text", ""))
    for opt_i, opt in enumerate(q.get("options") or []):
        st.markdown(f"{chr(65 + opt_i)}. {opt}")

    st.checkbox(
        "✅ Pilih soal ini untuk divariasikan",
        key=f"sel_{idx}",
        value=True,
    )

    concept = q.get("solution_by_concept")
    trick = q.get("solution_by_trick")
    if concept or trick:
        st.markdown("---")
        st.markdown("### 📝 Pembahasan AI")
        if concept:
            _render_solution(concept, "**Penyelesaian (Konsep Dasar)**")
        if trick:
            _render_solution(trick, "**Penyelesaian (Cara Cepat/Trik)**")
    else:
        st.warning("Pembahasan belum tersedia untuk soal ini.")


uploaded_file = st.file_uploader("Pilih file PDF", type="pdf")

if uploaded_file is not None:
    _save_uploaded_pdf(uploaded_file)

custom_instruction = st.text_area(
    "Instruksi Tambahan (Opsional)",
    placeholder="Contoh: Buat penyelesaian dengan konsep dasar, atau jelaskan cara cepat/trik mengerjakan soal ini...",
)

if uploaded_file is not None and not st.session_state.get("extraction_started"):
    if st.button("📄 Ekstrak Soal Pertama", type="primary", use_container_width=True):
        _run_first_extraction(custom_instruction)

if st.session_state.get("extraction_started"):
    log = st.session_state.questions_log
    total_pages = st.session_state.get("total_pages", 1)
    current_page = st.session_state.get("current_page", 1)
    current_idx = st.session_state.get("current_idx", 0)
    total_seen = len(log)

    st.divider()
    st.subheader(f"🔍 Soal yang sudah diekstrak: {total_seen}")
    st.caption(
        "Proses SATU halaman sekaligus: tinjau pembahasan AI soal ini, centang "
        "jika ingin divariasikan, lalu klik 'Lanjutkan' untuk mengekstrak halaman "
        "berikutnya. Halaman tanpa soal dilewati otomatis."
    )

    if not st.session_state.get("review_complete"):
        # --- Show the current question, one at a time --------------------
        total_questions = len(log)
        st.markdown(
            f"### 🧭 Soal {current_idx + 1} dari {total_questions} · "
            f"Halaman {current_page} dari {total_pages}"
        )
        st.progress(current_page / total_pages,
                    text=f"Halaman {current_page} dari {total_pages}")

        _render_question(current_idx, log[current_idx])

        st.markdown("---")
        nav_prev, nav_next = st.columns([1, 3])
        if current_idx > 0:
            with nav_prev:
                if st.button("← Kembali", use_container_width=True):
                    st.session_state.current_idx = current_idx - 1
                    st.rerun()
        with nav_next:
            last_of_log = current_idx == total_seen - 1
            last_page = current_page >= total_pages
            if last_of_log and last_page:
                if st.button("✅ Selesai - Buat Variasi Sekarang",
                             key="finish_review", type="primary",
                             use_container_width=True):
                    st.session_state.review_complete = True
                    st.rerun()
            else:
                label = f"✅ Soal {current_idx + 1} dari {total_questions} — Lanjutkan ke Soal Berikutnya →"
                if st.button(label, key="next_q", type="primary",
                             use_container_width=True):
                    _advance(custom_instruction)
                    st.rerun()
    else:
        # --- All pages reviewed -------------------------------------------
        st.markdown(
            f"### 🎉 Semua halaman telah ditinjau ({total_seen} soal diekstrak)"
        )
        selected = [
            q for i, q in enumerate(log)
            if st.session_state.get(f"sel_{i}")
        ]
        st.markdown(
            f"**{len(selected)} dari {total_seen} soal** dipilih untuk divariasikan."
        )
        if st.button("← Kembali Meninjau Soal", use_container_width=True):
            st.session_state.review_complete = False
            st.session_state.current_idx = max(0, total_seen - 1)
            st.rerun()

        if not selected:
            st.warning("Pilih minimal satu soal terlebih dahulu.")
        if selected and st.button(
            "🚀 Buat Variasi untuk Soal Terpilih",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.selected_questions = selected
            _run_variation(custom_instruction)
            st.session_state.variation_done = True
            st.rerun()

    if st.session_state.get("variation_done"):
        _render_download_and_preview()
