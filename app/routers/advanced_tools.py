from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path
import json
import os

from ..services.pdf_handler import redact_pdf, scrub_pdf_metadata, fill_and_flatten_pdf_form
from ..services.ocr import perform_ocr_on_pdf, translate_text
from ..services.utils import save_temp_file, get_temp_file_path, cleanup_temp_file

router = APIRouter()

TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/redact", summary="Redact sensitive information from a PDF")
async def redact_pdf_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to redact."),
    terms_to_redact_json: str = Form(..., description="JSON string of a list of terms to redact (e.g., '[\"sensitive data\", \"email@example.com\"]')."),
    output_filename: str = Form("redacted_document.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for redaction.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    try:
        terms_to_redact = json.loads(terms_to_redact_json)
        if not isinstance(terms_to_redact, list) or not all(isinstance(t, str) for t in terms_to_redact):
            raise HTTPException(status_code=400, detail="`terms_to_redact_json` must be a JSON array of strings.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for `terms_to_redact_json`.")

    input_path = await save_temp_file(file)
    output_path = get_temp_file_path(output_filename)

    try:
        redacted_pdf_path = redact_pdf(input_path, output_path, terms_to_redact)

        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, redacted_pdf_path)

        return FileResponse(path=redacted_pdf_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error redacting PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to redact PDF: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.post("/ocr_translate", summary="Perform OCR on a PDF and optionally translate the extracted text")
async def ocr_and_translate_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to perform OCR on."),
    ocr_language: str = Form("eng", description="Language for OCR (e.g., 'eng', 'spa'). Must have Tesseract language pack installed."),
    translate_to_language: Optional[str] = Form(None, description="Optional: Target language for translation (e.g., 'es', 'fr')."),
    output_filename: str = Form("extracted_text.txt")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for OCR.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file)
    output_path = get_temp_file_path(output_filename)

    try:
        extracted_text = perform_ocr_on_pdf(input_path, ocr_language)
        
        final_text = extracted_text
        if translate_to_language:
            translated_text = translate_text(extracted_text, translate_to_language, ocr_language)
            final_text = translated_text

        async with aiofiles.open(output_path, 'w', encoding='utf-8') as out_file:
            await out_file.write(final_text)

        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, output_path)

        return FileResponse(path=output_path, filename=output_filename, media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during OCR/Translation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to perform OCR or translation: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.post("/scrub_metadata", summary="Remove all metadata from a PDF file")
async def scrub_metadata_from_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to scrub metadata from."),
    output_filename: str = Form("scrubbed_document.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for metadata scrubbing.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file)
    output_path = get_temp_file_path(output_filename)

    try:
        scrubbed_pdf_path = scrub_pdf_metadata(input_path, output_path)

        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, scrubbed_pdf_path)

        return FileResponse(path=scrubbed_pdf_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error scrubbing metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scrub metadata: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.post("/fill_form", summary="Fill a PDF form with data and optionally flatten it")
async def fill_pdf_form(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF form file to fill."),
    form_data_json: str = Form(..., description="JSON string of form field names and their values (e.g., '{\"Name\": \"John Doe\", \"Email\": \"john@example.com\"}')."),
    flatten_form: bool = Form(True, description="If true, the form fields will be flattened (uneditable)."),
    output_filename: str = Form("filled_form.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for form filling.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    try:
        form_data = json.loads(form_data_json)
        if not isinstance(form_data, dict):
            raise HTTPException(status_code=400, detail="`form_data_json` must be a JSON object.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for `form_data_json`.")

    input_path = await save_temp_file(file)
    output_path = get_temp_file_path(output_filename)

    try:
        filled_pdf_path = fill_and_flatten_pdf_form(input_path, output_path, form_data, flatten_form)

        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, filled_pdf_path)

        return FileResponse(path=filled_pdf_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error filling PDF form: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fill PDF form: {e}")
    finally:
        cleanup_temp_file(input_path)