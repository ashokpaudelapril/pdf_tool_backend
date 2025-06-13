from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path
import json
import os
import aiofiles # Import aiofiles for async file operations

# Import your PDF service functions from the services layer
from ...services.pdf_handler import redact_pdf, scrub_pdf_metadata, fill_and_flatten_pdf_form
from ...services.ocr import perform_ocr_on_pdf, translate_text
# Import your utility functions for temporary file management
from ...services.utils import save_temp_file, get_temp_file_path, cleanup_temp_file

# Initialize the FastAPI router for advanced PDF tools
router = APIRouter(prefix="/api/pdf", tags=["Advanced PDF Tools"])

# Define the base temporary directory for all file operations
TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_DIR.mkdir(parents=True, exist_ok=True) # Ensure the temporary directory exists

@router.post("/redact", summary="Redact sensitive information from a PDF")
async def redact_pdf_file(
    background_tasks: BackgroundTasks, # FastAPI dependency for background cleanup
    file: UploadFile = File(..., description="The PDF file to redact."),
    terms_to_redact_json: str = Form(..., description="JSON string of a list of terms to redact (e.g., '[\"sensitive data\", \"email@example.com\"]')."),
    output_filename: str = Form("redacted_document.pdf")
):
    """
    Handles redaction of text within a PDF.
    Expects a PDF file and a JSON string of terms to redact.
    Returns the redacted PDF as a direct file download.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for redaction.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    try:
        # Parse the JSON string into a Python list of strings
        terms_to_redact = json.loads(terms_to_redact_json)
        if not isinstance(terms_to_redact, list) or not all(isinstance(t, str) for t in terms_to_redact):
            raise HTTPException(status_code=400, detail="`terms_to_redact_json` must be a JSON array of strings.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for `terms_to_redact_json`.")

    # Save the uploaded input file to a temporary location
    input_path = await save_temp_file(file)
    # Generate a unique path for the redacted output file
    output_path = get_temp_file_path(output_filename)

    try:
        # Call the core redaction logic from the service layer
        redacted_pdf_path = redact_pdf(input_path, output_path, terms_to_redact)

        # Add tasks to clean up both the input and output temporary files in the background
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, redacted_pdf_path)

        # Return the redacted PDF file as a direct FileResponse
        return FileResponse(path=redacted_pdf_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise # Re-raise any HTTPException that might have been raised by service functions
    except Exception as e:
        print(f"Error redacting PDF: {e}") # Log the specific error on the server
        raise HTTPException(status_code=500, detail=f"Failed to redact PDF: {e}")
    finally:
        # Ensure input file is cleaned up even if background task fails to be added (e.g. startup errors)
        cleanup_temp_file(input_path)


@router.post("/ocr_translate", summary="Perform OCR on a PDF and optionally translate the extracted text")
async def ocr_and_translate_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to perform OCR on."),
    ocr_language: str = Form("eng", description="Language for OCR (e.g., 'eng', 'spa'). Must have Tesseract language pack installed."),
    translate_to_language: Optional[str] = Form(None, description="Optional: Target language for translation (e.g., 'es', 'fr')."),
    output_filename: str = Form("extracted_text.txt") # Output is text, not PDF here
):
    """
    Performs Optical Character Recognition (OCR) on a PDF to extract text,
    and then optionally translates that text.
    Returns the extracted/translated text as a plain text file.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for OCR.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file) # Save the uploaded PDF temporarily
    output_path = get_temp_file_path(output_filename) # Generate a unique path for the output text file

    try:
        # Perform OCR to extract text from the PDF
        extracted_text = perform_ocr_on_pdf(input_path, ocr_language)
        
        final_text = extracted_text
        # If a translation language is provided, translate the text
        if translate_to_language:
            translated_text = translate_text(extracted_text, translate_to_language, ocr_language)
            final_text = translated_text

        # Write the final (extracted or translated) text to the output file
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as out_file:
            await out_file.write(final_text)

        # Add tasks to clean up temporary files in the background
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, output_path)

        # Return the text file as a direct FileResponse
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
    """
    Handles the removal of metadata (author, creation date, software, etc.) from a PDF.
    Returns the scrubbed PDF as a direct file download.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for metadata scrubbing.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file) # Save the uploaded PDF temporarily
    output_path = get_temp_file_path(output_filename) # Generate a unique path for the scrubbed output

    try:
        # Call the core metadata scrubbing logic from the service layer
        scrubbed_pdf_path = scrub_pdf_metadata(input_path, output_path)

        # Add tasks to clean up temporary files in the background
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, scrubbed_pdf_path)

        # Return the scrubbed PDF file as a direct FileResponse
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
    """
    Handles filling interactive PDF forms with provided data and optionally flattens them.
    Returns the filled PDF as a direct file download.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for form filling.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    try:
        # Parse the JSON string into a Python dictionary
        form_data = json.loads(form_data_json)
        if not isinstance(form_data, dict):
            raise HTTPException(status_code=400, detail="`form_data_json` must be a JSON object.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for `form_data_json`.")

    input_path = await save_temp_file(file) # Save the uploaded PDF form temporarily
    output_path = get_temp_file_path(output_filename) # Generate a unique path for the filled form output

    try:
        # Call the core form filling logic from the service layer
        filled_pdf_path = fill_and_flatten_pdf_form(input_path, output_path, form_data, flatten_form)

        # Add tasks to clean up temporary files in the background
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, filled_pdf_path)

        # Return the filled PDF form as a direct FileResponse
        return FileResponse(path=filled_pdf_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error filling PDF form: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fill PDF form: {e}")
    finally:
        cleanup_temp_file(input_path)