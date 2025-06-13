from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import uuid # For generating unique directories/filenames
import tempfile # For creating temporary directories

# Import your PDF service functions
from ...services.pdf_handler import merge_pdfs, split_pdf, redact_pdf, scrub_pdf_metadata, fill_and_flatten_pdf_form
# Import your utility functions for temp file management
from ...services.utils import save_temp_file, get_temp_file_path, cleanup_temp_file, cleanup_temp_files

router = APIRouter(prefix="/api/pdf", tags=["Basic PDF Tools"])

TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/merge", summary="Merge multiple PDF files into one")
async def merge_pdf_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="List of PDF files to merge, in order."),
    output_filename: str = Form("merged_document.pdf"),
    encrypt_output: bool = Form(False), # Placeholder for future encryption
    password: Optional[str] = Form(None) # Placeholder for future encryption
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for merging.")
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least two PDF files to merge.")

    input_paths = []
    # Generate a unique path for the merged output to avoid conflicts
    # Use output_filename to determine the extension, but ensure uniqueness
    merged_output_filename = f"{Path(output_filename).stem}_{uuid.uuid4()}{Path(output_filename).suffix}"
    output_path = TEMP_DIR / merged_output_filename


    try:
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")
            # Save each input file to a temporary location
            temp_input_path = await save_temp_file(file)
            input_paths.append(temp_input_path)

        # Call the service function to merge PDFs
        final_output_path = merge_pdfs(input_paths, output_path)

        # Add background tasks to clean up temporary files after the response is sent
        background_tasks.add_task(cleanup_temp_file, final_output_path)
        for path in input_paths:
             background_tasks.add_task(cleanup_temp_file, path)

        # Return the merged PDF file as a response
        return FileResponse(path=final_output_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions directly
    except Exception as e:
        print(f"Error merging PDFs: {e}") # Log the detailed error on the server
        raise HTTPException(status_code=500, detail=f"Failed to merge PDFs: {e}")
    finally:
        # Cleanup input files even if an error occurs before BackgroundTasks are added
        for path in input_paths:
            cleanup_temp_file(path)


@router.post("/split", summary="Split a PDF file into multiple new PDFs")
async def split_pdf_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to split."),
    pages: Optional[str] = Form(None, description="Comma-separated page numbers or ranges (e.g., '1,3,5-7'). If empty, each page becomes a separate PDF."),
    output_prefix: str = Form("split_part", description="Prefix for the output filenames (e.g., 'doc_split_1.pdf')."),
    encrypt_output: bool = Form(False), # Placeholder
    password: Optional[str] = Form(None) # Placeholder
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for splitting.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file) # Save the input file temporarily
    
    # Create a unique temporary directory for this split operation's outputs
    # This ensures all split files and the final ZIP are grouped for cleanup.
    processing_directory = Path(tempfile.mkdtemp(dir=TEMP_DIR))

    try:
        # Call the service function to split the PDF
        # It should save individual split PDFs into `processing_directory`
        split_pdf_paths = split_pdf(input_path, processing_directory, pages, output_prefix)

        if not split_pdf_paths:
            # If split_pdf returns an empty list, it means no files were generated
            raise HTTPException(status_code=500, detail="Failed to split PDF or no pages matched.")

        # Determine the output ZIP filename
        original_filename_base = Path(file.filename).stem
        zip_filename = f"{original_filename_base}_split.zip"
        zip_path = processing_directory / zip_filename # The ZIP will be created inside the processing directory

        # Create a ZIP file containing all the split PDFs
        from zipfile import ZipFile
        with ZipFile(zip_path, 'w') as zipf:
            for pdf_path in split_pdf_paths:
                # Add each split PDF to the zip file using its relative name
                zipf.write(pdf_path, arcname=pdf_path.name)

        # Add background tasks for cleanup: original input, individual split PDFs, and the entire processing directory (including the ZIP)
        background_tasks.add_task(cleanup_temp_file, input_path)
        for p_path in split_pdf_paths:
            background_tasks.add_task(cleanup_temp_file, p_path) # Clean up individual PDFs
        background_tasks.add_task(cleanup_temp_files, processing_directory) # Clean up the entire temporary folder

        # Return the created ZIP file directly
        return FileResponse(path=zip_path, filename=zip_filename, media_type="application/zip")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error splitting PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to split PDF: {e}")
    finally:
        # Ensure the input file is cleaned up even if an error occurs earlier
        cleanup_temp_file(input_path)


@router.post("/redact", summary="Redact specific text from a PDF file")
async def redact_pdf_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to redact."),
    terms_to_redact_json: str = Form(..., description="JSON array of strings representing terms to redact."),
    output_filename: str = Form("redacted_document.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for redaction.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    import json
    try:
        terms_to_redact = json.loads(terms_to_redact_json)
        if not isinstance(terms_to_redact, list):
            raise ValueError("Terms to redact must be a JSON array.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for terms_to_redact.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    input_path = await save_temp_file(file)
    # Generate a unique path for the redacted output
    redacted_output_filename = f"{Path(output_filename).stem}_{uuid.uuid4()}{Path(output_filename).suffix}"
    output_path = TEMP_DIR / redacted_output_filename

    try:
        # Call the service function to redact the PDF
        final_output_path = redact_pdf(input_path, output_path, terms_to_redact)

        # Add background tasks for cleanup
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, final_output_path)

        # Return the redacted PDF file
        return FileResponse(path=final_output_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error redacting PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to redact PDF: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.post("/scrub-metadata", summary="Remove metadata from a PDF file")
async def scrub_metadata_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to scrub metadata from."),
    output_filename: str = Form("scrubbed_document.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for metadata scrubbing.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file)
    # Generate a unique path for the scrubbed output
    scrubbed_output_filename = f"{Path(output_filename).stem}_{uuid.uuid4()}{Path(output_filename).suffix}"
    output_path = TEMP_DIR / scrubbed_output_filename

    try:
        # Call the service function to scrub metadata
        final_output_path = scrub_pdf_metadata(input_path, output_path)

        # Add background tasks for cleanup
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, final_output_path)

        # Return the scrubbed PDF file
        return FileResponse(path=final_output_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error scrubbing metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scrub metadata: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.post("/fill-form", summary="Fill an interactive PDF form with data")
async def fill_pdf_form_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF form file."),
    form_data_json: str = Form(..., description="JSON string of key-value pairs for form fields."),
    flatten_form: bool = Form(True, description="Whether to flatten the form fields after filling."),
    output_filename: str = Form("filled_form.pdf")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for form filling.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    import json
    try:
        form_data = json.loads(form_data_json)
        if not isinstance(form_data, dict):
            raise ValueError("Form data must be a JSON object.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for form_data.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    input_path = await save_temp_file(file)
    # Generate a unique path for the filled form output
    filled_output_filename = f"{Path(output_filename).stem}_{uuid.uuid4()}{Path(output_filename).suffix}"
    output_path = TEMP_DIR / filled_output_filename

    try:
        # Call the service function to fill and flatten the form
        final_output_path = fill_and_flatten_pdf_form(input_path, output_path, form_data, flatten_form)

        # Add background tasks for cleanup
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, final_output_path)

        # Return the filled PDF form
        return FileResponse(path=final_output_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error filling PDF form: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fill PDF form: {e}")
    finally:
        cleanup_temp_file(input_path)


# This endpoint is kept for serving temporary files if other services (e.g., OCR)
# provide a download link to a specific temporary file instead of a direct FileResponse.
@router.get("/download_temp_file/{temp_dir_name}/{filename:path}", include_in_schema=False)
async def download_temp_file(temp_dir_name: str, filename: str):
    file_path = TEMP_DIR / temp_dir_name / filename
    
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    # Security check to prevent directory traversal attacks
    if not file_path.resolve().starts_with(TEMP_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden: Attempted directory traversal.")

    # Determine media type based on file extension (basic example)
    import mimetypes
    media_type, _ = mimetypes.guess_type(filename)
    if not media_type:
        media_type = "application/octet-stream" # Default for unknown types

    return FileResponse(path=file_path, filename=filename, media_type=media_type)