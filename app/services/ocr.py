import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from pathlib import Path
from typing import List, Optional
import os

from translate import Translator

def perform_ocr_on_pdf(pdf_path: Path, lang: str = 'eng') -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found for OCR: {pdf_path}")

    extracted_text = []
    images = []
    try:
        images = convert_from_path(str(pdf_path), dpi=300)

        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image, lang=lang)
            extracted_text.append(f"\n--- Page {i+1} ---\n")
            extracted_text.append(text)
            
    except Exception as e:
        raise Exception(f"Failed to perform OCR on {pdf_path}: {e}. Ensure Tesseract and Poppler are installed and in PATH.")
    finally:
        pass

    return "\n".join(extracted_text)


def translate_text(text: str, target_language: str = 'en', source_language: Optional[str] = None) -> str:
    if not text.strip():
        return ""

    try:
        translator = Translator(to_lang=target_language, from_lang=source_language)
        translated_text = translator.translate(text)
        return translated_text

    except Exception as e:
        print(f"Translation failed: {e}")
        return f"Translation failed: {e}. Original text: {text}"