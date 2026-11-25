"""
OCR / document-evidence ingestion tests.

Covers:
- Native PDF text extraction (searchable PDFs, no external binary needed)
- Graceful degradation when OCR tooling is unavailable (scanned PDFs, images)
- Extension dispatch (CSV/XLSX/JSON leave extracted_text unset)
- Validator acceptance of PDF / PNG / JPEG and rejection of disguised payloads
"""

import sys
import unittest
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.services.evidence_validator import (  # noqa: E402
    ALLOWED_EXTENSIONS,
    EvidenceValidationError,
    validate_file_security,
)
from app.services.ocr import (  # noqa: E402
    extract_text_for_upload,
    extract_text_from_image_bytes,
    extract_text_from_pdf_bytes,
)


def build_text_pdf(text: str) -> bytes:
    """Builds a minimal, valid single-page PDF with an extractable text object."""
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    return bytes(out)


PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class TestPdfTextExtraction(unittest.TestCase):
    def test_01_native_pdf_text_is_extracted(self):
        """Searchable PDFs yield their text without any OCR binary."""
        text = "FIR 2025 Murshidabad trafficking complaint recorded by AHTU inspector"
        extracted = extract_text_from_pdf_bytes(build_text_pdf(text))
        self.assertIn("Murshidabad", extracted)
        self.assertGreaterEqual(len(extracted), 50)

    def test_02_corrupt_pdf_degrades_to_empty_string(self):
        """A malformed payload must never raise — uploads depend on it."""
        self.assertEqual(extract_text_from_pdf_bytes(b"not a pdf at all"), "")

    def test_03_empty_pdf_degrades_to_empty_string(self):
        self.assertEqual(extract_text_from_pdf_bytes(b""), "")


class TestImageTextExtraction(unittest.TestCase):
    def test_04_invalid_image_degrades_to_empty_string(self):
        self.assertEqual(extract_text_from_image_bytes(b"not-an-image"), "")

    def test_05_png_header_without_payload_does_not_raise(self):
        self.assertEqual(extract_text_from_image_bytes(PNG_HEADER), "")


class TestExtractionDispatch(unittest.TestCase):
    def test_06_pdf_dispatch_returns_text(self):
        text = "Witness statement recorded under section 161 in the trafficking dossier"
        self.assertIn("Witness", extract_text_for_upload("fir.pdf", build_text_pdf(text)))

    def test_07_image_dispatch_returns_string(self):
        self.assertIsInstance(extract_text_for_upload("scan.jpg", JPEG_HEADER), str)

    def test_08_structured_formats_are_not_ocrd(self):
        """CSV/XLSX/JSON are parsed row-wise; no text extraction is attempted."""
        for name in ("cdr.csv", "ledger.xlsx", "case.json"):
            self.assertIsNone(extract_text_for_upload(name, b"a,b\n1,2\n"))

    def test_09_unknown_extension_is_not_ocrd(self):
        self.assertIsNone(extract_text_for_upload("archive.zip", b"PK\x03\x04"))


class TestValidatorDocumentTypes(unittest.TestCase):
    def test_10_pdf_png_jpeg_are_allowed_extensions(self):
        for ext in (".pdf", ".png", ".jpg", ".jpeg"):
            self.assertIn(ext, ALLOWED_EXTENSIONS)

    def test_11_pdf_signature_accepted(self):
        sanitized = validate_file_security("fir_scan.pdf", build_text_pdf("hello world"))
        self.assertEqual(sanitized, "fir_scan.pdf")

    def test_12_png_and_jpeg_signatures_accepted(self):
        self.assertEqual(validate_file_security("scan.png", PNG_HEADER), "scan.png")
        self.assertEqual(validate_file_security("scan.jpeg", JPEG_HEADER), "scan.jpeg")

    def test_13_pdf_extension_with_wrong_payload_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("fake.pdf", b"plain text pretending to be a pdf")

    def test_14_executable_disguised_as_pdf_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("payload.pdf", b"MZ\x90\x00" + b"\x00" * 32)

    def test_15_png_payload_under_csv_extension_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("hidden.csv", PNG_HEADER)

    def test_16_pdf_payload_under_json_extension_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("hidden.json", build_text_pdf("payload"))

    def test_17_plain_csv_still_accepted(self):
        self.assertEqual(
            validate_file_security("cdr.csv", b"calling_number,called_number\n1,2\n"),
            "cdr.csv",
        )

    def test_18_executable_extension_still_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("malware.exe", b"MZ\x90\x00")

    def test_19_path_traversal_still_rejected(self):
        with self.assertRaises(EvidenceValidationError):
            validate_file_security("../../etc/passwd.csv", b"a,b\n1,2\n")


if __name__ == "__main__":
    unittest.main()
