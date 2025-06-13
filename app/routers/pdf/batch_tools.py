from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import List, Optional
from pathlib import Path
import json
import os
import aiofiles

from ...services.pdf_handler import redact_pdf, scrub_pdf_metadata
from ...services.ocr import perform_ocr_on_pdf, translate_text
from ...services.utils import save_temp_file, get_temp_file_path, cleanup_temp_file, cleanup_temp_files, extract_zip_archive, create_zip_archive

router = APIRouter(prefix="/api/pdf", tags=["Batch PDF Tools"])

TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/batch_redact", summary="Redact sensitive information from multiple PDFs in a ZIP archive")
async def batch_redact_pdfs(
    background_tasks: BackgroundTasks,
    zip_file: UploadFile = File(..., description="ZIP file containing PDF files to redact."),
    terms_to_redact_json: str = Form(..., description="JSON string of a list of terms to redact (e.g., '[\"sensitive data\"]')."),
    output_zip_filename: str = Form("redacted_pdfs.zip")
):
    if not zip_file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Input must be a ZIP file.")

    try:
        terms_to_redact = json.loads(terms_to_redact_json)
        if not isinstance(terms_to_redact, list) or not all(isinstance(t, str) for t in terms_to_redact):
            raise HTTPException(status_code=400, detail="`terms_to_redact_json` must be a JSON array of strings.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for `terms_to_redact_json`.")

    temp_zip_input_path = await save_temp_file(zip_file)
    extracted_dir = get_temp_file_path(directory_only=True)
    output_files = []
    output_zip_path = get_temp_file_path(output_zip_filename)

    try:
        # Extract the incoming ZIP file
        extracted_pdf_paths = extract_zip_archive(temp_zip_input_path, extracted_dir)
        
        if not extracted_pdf_paths:
            raise HTTPException(status_code=400, detail="No PDF files found in the uploaded ZIP archive.")

        # Process each extracted PDF
        for pdf_path in extracted_pdf_paths:
            if pdf_path.suffix.lower() == '.pdf':
                output_pdf_path = get_temp_file_path(f"redacted_{pdf_path.name}")
                try:
                    redacted_pdf_path = redact_pdf(pdf_path, output_pdf_path, terms_to_redact)
                    output_files.append(redacted_pdf_path)
                except Exception as e:
                    print(f"Error redacting {pdf_path.name}: {e}")
                    # Continue processing other files even if one fails
                    continue 

        if not output_files:
            raise HTTPException(status_code=500, detail="No PDFs were successfully redacted.")

        # Create a new ZIP file from the processed output files
        final_zip_path = create_zip_archive(output_files, output_zip_path)
        
        # Add cleanup tasks for all temporary files and directories
        background_tasks.add_task(cleanup_temp_file, temp_zip_input_path)
        background_tasks.add_task(cleanup_temp_files, extracted_dir) # Cleans up the directory and its contents
        for file_path in output_files: # Individual processed files before zipping
            background_tasks.add_task(cleanup_temp_file, file_path)
        background_tasks.add_task(cleanup_temp_file, final_zip_path) # Clean up the final ZIP after sending

        # Return the final ZIP file directly as a response
        return FileResponse(path=final_zip_path, filename=output_zip_filename, media_type="application/zip")

    except HTTPException:
        raise # Re-raise any HTTPException raised by this function or its dependencies
    except Exception as e:
        print(f"Error during batch redaction: {e}") # Log the detailed error
        raise HTTPException(status_code=500, detail=f"Failed to perform batch redaction: {e}")
    finally:
        # Ensure initial input ZIP and extracted directory are cleaned up even on early errors
        cleanup_temp_file(temp_zip_input_path)
        cleanup_temp_files(extracted_dir)


@router.post("/batch_ocr_translate", summary="Perform OCR and optional translation on multiple PDFs in a ZIP archive")
async def batch_ocr_translate_pdfs(
    background_tasks: BackgroundTasks,
    zip_file: UploadFile = File(..., description="ZIP file containing PDF files for OCR and translation."),
    ocr_language: str = Form("eng", description="Language for OCR (e.g., 'eng', 'spa')."),
    translate_to_language: Optional[str] = Form(None, description="Optional: Target language for translation (e.g., 'es', 'fr')."),
    output_zip_filename: str = Form("ocr_translated_texts.zip")
):
    if not zip_file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Input must be a ZIP file.")

    temp_zip_input_path = await save_temp_file(zip_file)
    extracted_dir = get_temp_file_path(directory_only=True)
    output_text_files = [] # This will store paths to .txt files
    output_zip_path = get_temp_file_path(output_zip_filename)

    try:
        # Extract the incoming ZIP file
        extracted_pdf_paths = extract_zip_archive(temp_zip_input_path, extracted_dir)

        if not extracted_pdf_paths:
            raise HTTPException(status_code=400, detail="No PDF files found in the uploaded ZIP archive.")

        # Process each extracted PDF for OCR and optional translation
        for pdf_path in extracted_pdf_paths:
            if pdf_path.suffix.lower() == '.pdf':
                # Create a unique path for the output text file for each PDF
                output_txt_path = get_temp_file_path(f"{pdf_path.stem}.txt")
                try:
                    # Perform OCR
                    extracted_text = perform_ocr_on_pdf(pdf_path, ocr_language)
                    final_text = extracted_text
                    
                    # Perform translation if a target language is provided
                    if translate_to_language:
                        final_text = translate_text(extracted_text, translate_to_language, ocr_language)
                    
                    # Write the extracted/translated text to a temporary .txt file
                    async with aiofiles.open(output_txt_path, 'w', encoding='utf-8') as out_file:
                        await out_file.write(final_text)
                    output_text_files.append(output_txt_path)
                except Exception as e:
                    print(f"Error processing {pdf_path.name} for OCR/Translation: {e}")
                    continue # Continue to next file even if this one fails
        
        if not output_text_files:
            raise HTTPException(status_code=500, detail="No PDFs were successfully processed for OCR/translation.")

        # Create a new ZIP file containing all the generated text files
        final_zip_path = create_zip_archive(output_text_files, output_zip_path)

        # Add background tasks for cleanup
        background_tasks.add_task(cleanup_temp_file, temp_zip_input_path)
        background_tasks.add_task(cleanup_temp_files, extracted_dir)
        for file_path in output_text_files:
            background_tasks.add_task(cleanup_temp_file, file_path)
        background_tasks.add_task(cleanup_temp_file, final_zip_path)

        # Return the final ZIP file directly as a response
        return FileResponse(path=final_zip_path, filename=output_zip_filename, media_type="application/zip")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during batch OCR/Translation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to perform batch OCR/Translation: {e}")
    finally:
        cleanup_temp_file(temp_zip_input_path)
        cleanup_temp_files(extracted_dir)


@router.post("/batch_scrub_metadata", summary="Remove all metadata from multiple PDFs in a ZIP archive")
async def batch_scrub_metadata_pdfs(
    background_tasks: BackgroundTasks,
    zip_file: UploadFile = File(..., description="ZIP file containing PDF files to scrub metadata from."),
    output_zip_filename: str = Form("scrubbed_pdfs.zip")
):
    if not zip_file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Input must be a ZIP file.")

    temp_zip_input_path = await save_temp_file(zip_file)
    extracted_dir = get_temp_file_path(directory_only=True)
    output_files = [] # This will store paths to the scrubbed PDF files
    output_zip_path = get_temp_file_path(output_zip_filename)

    try:
        # Extract the incoming ZIP file
        extracted_pdf_paths = extract_zip_archive(temp_zip_input_path, extracted_dir)

        if not extracted_pdf_paths:
            raise HTTPException(status_code=400, detail="No PDF files found in the uploaded ZIP archive.")

        # Process each extracted PDF for metadata scrubbing
        for pdf_path in extracted_pdf_paths:
            if pdf_path.suffix.lower() == '.pdf':
                # Create a unique path for the scrubbed output PDF
                output_pdf_path = get_temp_file_path(f"scrubbed_{pdf_path.name}")
                try:
                    scrubbed_pdf_path = scrub_pdf_metadata(pdf_path, output_pdf_path)
                    output_files.append(scrubbed_pdf_path)
                except Exception as e:
                    print(f"Error scrubbing metadata from {pdf_path.name}: {e}")
                    continue # Continue to next file even if this one fails
        
        if not output_files:
            raise HTTPException(status_code=500, detail="No PDFs were successfully scrubbed of metadata.")

        # Create a new ZIP file containing all the scrubbed PDF files
        final_zip_path = create_zip_archive(output_files, output_zip_path)

        # Add background tasks for cleanup
        background_tasks.add_task(cleanup_temp_file, temp_zip_input_path)
        background_tasks.add_task(cleanup_temp_files, extracted_dir)
        for file_path in output_files:
            background_tasks.add_task(cleanup_temp_file, file_path)
        background_tasks.add_task(cleanup_temp_file, final_zip_path)

        # Return the final ZIP file directly as a response
        return FileResponse(path=final_zip_path, filename=output_zip_filename, media_type="application/zip")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during batch metadata scrubbing: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to perform batch metadata scrubbing: {e}")
    finally:
        cleanup_temp_file(temp_zip_input_path)
        cleanup_temp_files(extracted_dir)