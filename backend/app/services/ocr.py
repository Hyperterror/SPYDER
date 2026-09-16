"""Text extraction helpers for uploaded PDF and raster-image evidence."""
from __future__ import annotations

from io import BytesIO
import logging


logger = logging.getLogger(__name__)

MIN_NATIVE_TEXT_LENGTH = 50


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract searchable PDF text, falling back to page-image OCR when needed.

    OCR failures deliberately return any native text already recovered (or an empty
    string). An evidence upload must not fail solely because an optional external
    OCR executable is unavailable.
    """
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
    """Extract text directly from PNG and JPEG evidence using Tesseract OCR.

    Invalid image data or unavailable OCR tooling is logged and represented as an
    empty result so the original evidence upload remains available for review.
    """
    try:
        from PIL import Image
        import pytesseract

        with Image.open(BytesIO(image_bytes)) as image:
            return pytesseract.image_to_string(image).strip()
    except Exception:
        logger.warning("Image OCR failed; storing an empty extracted-text result", exc_info=True)
        return ""
