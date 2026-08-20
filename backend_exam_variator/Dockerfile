FROM python:3.13-slim

WORKDIR /app

# Install system deps for PyMuPDF and tesseract (optional OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev tesseract-ocr tesseract-ocr-ind \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
