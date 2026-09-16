"""Manually verify PDF extraction or direct PNG/JPEG OCR.

Run from ``backend/``:
    python -m app.scripts.check_ocr path/to/document.pdf
    python -m app.scripts.check_ocr path/to/image.png
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from app.services.ocr import (
    MIN_NATIVE_TEXT_LENGTH,
    extract_text_from_image_bytes,
    extract_text_from_pdf_bytes,
)


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _native_text_length(pdf_bytes: bytes) -> int | None:
    """Return native text length, or None if pypdf could not read the document."""
    try:
        from pypdf import PdfReader

        return len("\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages).strip())
    except Exception as exc:
        print(f"Native extraction could not read this PDF: {exc}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SPYDER PDF or image OCR extraction.")
    parser.add_argument("file", type=Path, help="Path to a PDF, PNG, JPG, or JPEG file")
    parser.add_argument("--preview-chars", type=int, default=500, help="Characters of extracted text to print")
    args = parser.parse_args()

    if args.preview_chars < 1:
        parser.error("--preview-chars must be at least 1")
    if not args.file.is_file() or args.file.suffix.lower() not in SUPPORTED_EXTENSIONS:
        parser.error("file must be an existing .pdf, .png, .jpg, or .jpeg file")

    file_bytes = args.file.read_bytes()
    extension = args.file.suffix.lower()
    if extension == ".pdf":
        native_length = _native_text_length(file_bytes)
        extracted_text = extract_text_from_pdf_bytes(file_bytes)
        mode = (
            "native pypdf extraction"
            if native_length is not None and native_length >= MIN_NATIVE_TEXT_LENGTH
            else "OCR fallback attempted (pdf2image + pytesseract)"
        )
    else:
        extracted_text = extract_text_from_image_bytes(file_bytes)
        mode = "direct image OCR (Pillow + pytesseract)"

    print(f"File: {args.file}")
    print(f"Mode: {mode}")
    print(f"Extracted characters: {len(extracted_text)}")
    if extracted_text:
        print("\nText preview:\n")
        print(extracted_text[:args.preview_chars])
        return 0

    print("\nNo text was extracted. Check that Tesseract is installed and on PATH;")
    if extension == ".pdf":
        print("also check that Poppler is installed and on PATH for scanned PDFs.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
