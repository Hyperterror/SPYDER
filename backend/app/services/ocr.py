"""Text extraction helpers for uploaded PDF and raster-image evidence.

Extraction is always best-effort: a missing OCR binary, a scanned page or a
corrupt image must never prevent the original evidence from being hashed,
stored and audited. Failures return whatever text was recovered, or "".
"""
from __future__ import annotations

import logging
import os
from io import BytesIO


logger = logging.getLogger(__name__)

# Below this many native characters a PDF is treated as scanned/image-only and
# an OCR fallback is attempted.
MIN_NATIVE_TEXT_LENGTH = 50

# Extensions handled by this module
OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract searchable PDF text, falling back to page-image OCR when needed."""
    native_text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        native_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        ).strip()
    except Exception:
        logger.warning("Native PDF text extraction failed; attempting OCR fallback", exc_info=True)

    if len(native_text) >= MIN_NATIVE_TEXT_LENGTH:
        return native_text

    logger.info(
        "Native PDF text was insufficient (%d characters); attempting OCR fallback",
        len(native_text),
    )
    try:
        from pdf2image import convert_from_bytes
        import pytesseract

        pages = convert_from_bytes(pdf_bytes)
        ocr_text = "\n".join(
            pytesseract.image_to_string(page) for page in pages
        ).strip()
        return ocr_text or native_text
    except Exception:
        logger.warning("PDF OCR fallback failed; storing available native text", exc_info=True)
        return native_text


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    """Extract text directly from PNG/JPEG evidence using Tesseract OCR."""
    try:
        from PIL import Image
        import pytesseract

        with Image.open(BytesIO(image_bytes)) as image:
            return pytesseract.image_to_string(image).strip()
    except Exception:
        logger.warning("Image OCR failed; storing an empty extracted-text result", exc_info=True)
        return ""


def extract_text_for_upload(filename: str, file_bytes: bytes) -> str | None:
    """Dispatch to the correct extractor, or return None for non-document uploads."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf_bytes(file_bytes)
    if ext in {".png", ".jpg", ".jpeg"}:
        return extract_text_from_image_bytes(file_bytes)
    return None
