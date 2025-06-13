from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import List, Optional
from pathlib import Path
import os

from ..services.pdf_handler import merge_pdfs, split_pdf
from ..services.utils import save_temp_file, get_temp_file_path, cleanup_temp_file, cleanup_temp_files

router = APIRouter()

TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/merge", summary="Merge multiple PDF files into one")
async def merge_pdf_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="List of PDF files to merge, in order."),
    output_filename: str = Form("merged_document.pdf"),
    encrypt_output: bool = Form(False),
    password: Optional[str] = Form(None)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for merging.")
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least two PDF files to merge.")

    input_paths = []
    output_path = get_temp_file_path(output_filename)

    try:
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")
            temp_input_path = await save_temp_file(file)
            input_paths.append(temp_input_path)

        merged_pdf_path = merge_pdfs(input_paths, output_path)
        final_output_path = merged_pdf_path

        background_tasks.add_task(cleanup_temp_file, final_output_path)
        for path in input_paths:
             background_tasks.add_task(cleanup_temp_file, path)

        return FileResponse(path=final_output_path, filename=output_filename, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error merging PDFs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to merge PDFs: {e}")
    finally:
        for path in input_paths:
            cleanup_temp_file(path)


@router.post("/split", summary="Split a PDF file into multiple new PDFs")
async def split_pdf_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The PDF file to split."),
    pages: Optional[str] = Form(None),
    output_prefix: str = Form("split_part"),
    encrypt_output: bool = Form(False),
    password: Optional[str] = Form(None)
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided for splitting.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF.")

    input_path = await save_temp_file(file)
    output_directory = get_temp_file_path(directory_only=True)

    try:
        split_pdf_paths = split_pdf(input_path, output_directory, pages, output_prefix)

        if not split_pdf_paths:
            raise HTTPException(status_code=500, detail="Failed to split PDF or no pages matched.")

        background_tasks.add_task(cleanup_temp_file, input_path)
        for p in split_pdf_paths:
            background_tasks.add_task(cleanup_temp_file, p)
        background_tasks.add_task(cleanup_temp_files, output_directory)

        return {"message": "PDF split successfully!", 
                "files_generated": len(split_pdf_paths), 
                "example_download_link": f"/api/pdf/download_temp_file/{Path(split_pdf_paths[0]).parent.name}/{Path(split_pdf_paths[0]).name}"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error splitting PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to split PDF: {e}")
    finally:
        cleanup_temp_file(input_path)


@router.get("/download_temp_file/{temp_dir_name}/{filename:path}", include_in_schema=False)
async def download_temp_file(temp_dir_name: str, filename: str):
    file_path = TEMP_DIR / temp_dir_name / filename
    
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    if not file_path.resolve().starts_with(TEMP_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden: Attempted directory traversal.")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")