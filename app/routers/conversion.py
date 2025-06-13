# backend/app/routers/conversion.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from typing import List, Optional
from pathlib import Path
import shutil
import os
import uuid
import json
import subprocess # For calling external tools like LibreOffice

# --- Conversion Libraries ---
# pip install PyMuPDF Pillow PyPDF2 reportlab pandas python-docx
import fitz # PyMuPDF for PDF to Image
from PIL import Image # Pillow for Image manipulation, Image to PDF
from PyPDF2 import PdfReader # PyPDF2 for PDF to Text
from reportlab.lib.pagesizes import letter # ReportLab for Text to PDF, CSV to PDF
from reportlab.pdfgen import canvas
from docx import Document # python-docx for creating .docx (not converting from PDF directly)
from pptx import Presentation # python-pptx for creating .pptx (not converting from PDF directly)
import pandas as pd # For CSV to PDF example

router = APIRouter(prefix="/api/convert", tags=["Conversion"])

TEMP_DIR = Path("temp_conversions")
TEMP_DIR.mkdir(exist_ok=True)

# --- Helper function for external LibreOffice conversions ---
def convert_via_libreoffice(input_path: Path, output_dir: Path, output_format: str) -> Path:
    """
    Converts a file using LibreOffice. Requires LibreOffice to be installed on the server.
    output_format example: 'pdf', 'docx', 'pptx', 'txt'
    """
    # Ensure output_dir exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # On Linux/macOS, 'libreoffice' or 'soffice'. On Windows, 'soffice.exe' in LibreOffice install dir.
    # It's best to have LibreOffice's bin directory in your system's PATH.
    libreoffice_cmd = ['soffice', '--headless', '--convert-to', output_format, '--outdir', str(output_dir), str(input_path)]
    
    try:
        result = subprocess.run(libreoffice_cmd, capture_output=True, text=True, check=True, timeout=300)
        print(f"LibreOffice stdout: {result.stdout}")
        print(f"LibreOffice stderr: {result.stderr}")
        
        # LibreOffice typically outputs with the same basename but new extension
        output_filename = f"{input_path.stem}.{output_format}"
        converted_file_path = output_dir / output_filename
        
        if not converted_file_path.exists():
            # Sometimes LibreOffice renames things slightly or has unexpected behavior,
            # so we look for any newly created file with the target extension.
            found_files = list(output_dir.glob(f"*.{output_format}"))
            if found_files:
                converted_file_path = found_files[0] # Take the first one
                print(f"Found LibreOffice output: {converted_file_path}")
            else:
                raise Exception(f"LibreOffice did not produce a {output_format} file. Stderr: {result.stderr}")
        
        return converted_file_path
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"LibreOffice conversion failed: {e.stderr}")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="LibreOffice not found. Please install LibreOffice on the server and ensure 'soffice' is in PATH.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="LibreOffice conversion timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"General LibreOffice error: {e}")

# --- Core Conversion Functions (using specific libs or external tools) ---

# PDF to Image/Text (from previous implementation)
def convert_pdf_to_images_lib(pdf_path: Path, output_dir: Path, output_format: str = "png") -> List[str]:
    doc = fitz.open(pdf_path)
    image_paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap()
        img_filename = f"{pdf_path.stem}_page_{i+1}.{output_format}"
        img_path = output_dir / img_filename
        pix.save(str(img_path))
        image_paths.append(str(img_path))
    doc.close()
    return image_paths

def convert_images_to_pdf_lib(image_paths: List[Path], output_pdf_path: Path) -> str:
    if not image_paths:
        raise ValueError("No images provided for PDF conversion.")
    
    images = []
    for img_path in image_paths:
        img = Image.open(img_path).convert('RGB')
        images.append(img)
    
    images[0].save(str(output_pdf_path), save_all=True, append_images=images[1:])
    return str(output_pdf_path)

def convert_pdf_to_text_lib(pdf_path: Path, output_text_path: Path) -> str:
    text_content = ""
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        for page in reader.pages:
            text_content += page.extract_text() + "\n"
    output_text_path.write_text(text_content, encoding='utf-8')
    return str(output_text_path)

def convert_text_to_pdf_lib(text_path: Path, output_pdf_path: Path) -> str:
    c = canvas.Canvas(str(output_pdf_path), pagesize=letter)
    c.setFont("Helvetica", 12)
    
    text = text_path.read_text(encoding='utf-8')
    lines = text.split('\n')
    
    y_pos = 750 # Starting Y position
    for line in lines:
        c.drawString(50, y_pos, line)
        y_pos -= 14 # Line height
        if y_pos < 50: # New page if content goes too low
            c.showPage()
            c.setFont("Helvetica", 12)
            y_pos = 750
            
    c.save()
    return str(output_pdf_path)

def convert_csv_to_pdf_lib(csv_path: Path, output_pdf_path: Path) -> str:
    df = pd.read_csv(csv_path)
    
    c = canvas.Canvas(str(output_pdf_path), pagesize=letter)
    c.setFont("Helvetica", 10)
    
    y_pos = 750
    x_pos = 50
    line_height = 12
    col_width = 100 # Adjust as needed
    
    # Draw header
    for i, col in enumerate(df.columns):
        c.drawString(x_pos + i * col_width, y_pos, str(col))
    y_pos -= line_height * 2 # Space after header

    # Draw rows
    for index, row in df.iterrows():
        if y_pos < 50: # New page if content goes too low
            c.showPage()
            c.setFont("Helvetica", 10)
            y_pos = 750
        
        for i, val in enumerate(row.values):
            c.drawString(x_pos + i * col_width, y_pos, str(val))
        y_pos -= line_height
            
    c.save()
    return str(output_pdf_path)

# --- FastAPI Endpoints ---

@router.post("/pdf_to_images")
async def pdf_to_images_endpoint(
    file: UploadFile = File(...),
    output_format: str = Form("png"), # png or jpg
    output_zip_filename: str = Form("converted_images.zip")
):
    """Converts a PDF file into a ZIP archive of images (one image per page)."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    pdf_path = processing_dir / file.filename
    try:
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        image_paths = convert_pdf_to_images_lib(pdf_path, processing_dir, output_format)
        
        zip_path = TEMP_DIR / output_zip_filename
        shutil.make_archive(str(zip_path.with_suffix("")), 'zip', processing_dir) # Creates .zip

        return FileResponse(
            path=str(zip_path.with_suffix(".zip")),
            media_type="application/zip",
            filename=output_zip_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True) or (zip_path.with_suffix(".zip")).unlink(missing_ok=True)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        pass

@router.post("/pdf_to_text")
async def pdf_to_text_endpoint(
    file: UploadFile = File(...),
    output_filename: str = Form("extracted_text.txt")
):
    """Extracts text from a PDF file."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    pdf_path = processing_dir / file.filename
    output_text_path = processing_dir / output_filename
    
    try:
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        converted_text_path = convert_pdf_to_text_lib(pdf_path, output_text_path)

        return FileResponse(
            path=str(converted_text_path),
            media_type="text/plain",
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")
    finally:
        pass

@router.post("/pdf_to_pptx")
async def pdf_to_pptx_endpoint(
    file: UploadFile = File(...),
    output_filename: str = Form("converted_slides.pptx")
):
    """
    Attempts to convert a PDF file to a PowerPoint (PPTX) presentation.
    Note: High-fidelity conversion from PDF to PPTX is extremely challenging
    and often requires advanced OCR, layout analysis, or external commercial APIs.
    This endpoint uses LibreOffice, which offers better results than pure Python libraries.
    Requires LibreOffice to be installed on the server.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    pdf_path = processing_dir / file.filename
    try:
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        converted_pptx_path = convert_via_libreoffice(pdf_path, processing_dir, "pptx")
        
        return FileResponse(
            path=str(converted_pptx_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except HTTPException:
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF to PPTX conversion failed: {e}. Ensure LibreOffice is installed on server.")
    finally:
        pass

@router.post("/images_to_pdf")
async def images_to_pdf_endpoint(
    files: List[UploadFile] = File(...),
    output_filename: str = Form("converted_from_images.pdf")
):
    """Combines multiple image files (JPG/PNG) into a single PDF."""
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")
    
    allowed_image_types = ["image/jpeg", "image/png"]
    for f in files:
        if f.content_type not in allowed_image_types:
            raise HTTPException(status_code=400, detail="Only JPG or PNG images are allowed.")

    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    uploaded_image_paths = []
    try:
        for f in files:
            img_path = processing_dir / f.filename
            with open(img_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            uploaded_image_paths.append(img_path)

        output_pdf_path = processing_dir / output_filename
        converted_pdf_path = convert_images_to_pdf_lib(uploaded_image_paths, output_pdf_path)

        return FileResponse(
            path=str(converted_pdf_path),
            media_type="application/pdf",
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        pass

@router.post("/text_to_pdf")
async def text_to_pdf_endpoint(
    file: UploadFile = File(...), # Expects a .txt file
    output_filename: str = Form("text_document.pdf")
):
    """Converts a text file (.txt) into a PDF document."""
    if file.content_type != "text/plain":
        raise HTTPException(status_code=400, detail="Only TXT files are allowed.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    text_path = processing_dir / file.filename
    output_pdf_path = processing_dir / output_filename
    
    try:
        with open(text_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        converted_pdf_path = convert_text_to_pdf_lib(text_path, output_pdf_path)

        return FileResponse(
            path=str(converted_pdf_path),
            media_type="application/pdf",
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        pass

@router.post("/pptx_to_pdf")
async def pptx_to_pdf_endpoint(
    file: UploadFile = File(...),
    output_filename: str = Form("converted_presentation.pdf")
):
    """
    Converts a PowerPoint (PPTX) file to a PDF document.
    Requires LibreOffice to be installed on the server.
    """
    if file.content_type not in ["application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.ms-powerpoint"]:
        raise HTTPException(status_code=400, detail="Only PPTX or PPT files are allowed.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    pptx_path = processing_dir / file.filename
    try:
        with open(pptx_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        converted_pdf_path = convert_via_libreoffice(pptx_path, processing_dir, "pdf")
        
        return FileResponse(
            path=str(converted_pdf_path),
            media_type="application/pdf",
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except HTTPException:
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPTX to PDF conversion failed: {e}. Ensure LibreOffice is installed on server.")
    finally:
        pass

@router.post("/any_to_pdf")
async def any_to_pdf_endpoint(
    file: UploadFile = File(...),
    output_filename: str = Form("converted_document.pdf")
):
    """
    Attempts to convert various file types to PDF.
    Currently supports: CSV, TXT, common image formats.
    Requires LibreOffice for office documents (DOCX, XLSX, PPTX, etc.).
    """
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    input_file_path = processing_dir / file.filename
    try:
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        converted_pdf_path = None
        media_type = "application/pdf" # Default output type

        if file.content_type == "text/csv":
            converted_pdf_path = convert_csv_to_pdf_lib(input_file_path, processing_dir / output_filename)
        elif file.content_type == "text/plain":
            converted_pdf_path = convert_text_to_pdf_lib(input_file_path, processing_dir / output_filename)
        elif file.content_type in ["image/jpeg", "image/png"]:
            # For a single image, convert_images_to_pdf_lib works
            converted_pdf_path = convert_images_to_pdf_lib([input_file_path], processing_dir / output_filename)
        elif file.content_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
            "application/msword", # .doc
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # .xlsx
            "application/vnd.ms-excel", # .xls
            "application/vnd.openxmlformats-officedocument.presentationml.presentation", # .pptx
            "application/vnd.ms-powerpoint" # .ppt
        ]:
            # Use LibreOffice for office documents
            converted_pdf_path = convert_via_libreoffice(input_file_path, processing_dir, "pdf")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type for direct conversion to PDF: {file.content_type}")
        
        if not converted_pdf_path or not converted_pdf_path.exists():
             raise HTTPException(status_code=500, detail="Conversion to PDF failed. Output file not found.")

        return FileResponse(
            path=str(converted_pdf_path),
            media_type=media_type,
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except HTTPException:
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion to PDF failed: {e}")
    finally:
        pass


@router.post("/pdf_to_any")
async def pdf_to_any_endpoint(
    file: UploadFile = File(...),
    target_format: str = Form(...), # e.g., 'docx', 'xlsx', 'txt', 'html'
    output_filename: str = Form("converted_output")
):
    """
    Converts a PDF file to a specified target format using LibreOffice.
    This is highly experimental and fidelity may vary greatly.
    Requires LibreOffice to be installed on the server.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed for PDF to Any conversion.")
    
    unique_id = uuid.uuid4()
    processing_dir = TEMP_DIR / str(unique_id)
    processing_dir.mkdir(exist_ok=True)
    
    pdf_path = processing_dir / file.filename
    try:
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Determine output filename extension
        if not output_filename.endswith(f".{target_format}"):
            output_filename = f"{Path(file.filename).stem}.{target_format}"

        # Use LibreOffice for conversion
        converted_file_path = convert_via_libreoffice(pdf_path, processing_dir, target_format)
        
        # Determine media type based on target format
        media_type_map = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "txt": "text/plain",
            "html": "text/html",
            "odt": "application/vnd.oasis.opendocument.text",
            "ods": "application/vnd.oasis.opendocument.spreadsheet",
            "odp": "application/vnd.oasis.opendocument.presentation",
            "rtf": "application/rtf",
            "csv": "text/csv",
            "xml": "application/xml",
            "json": "application/json",
            "jpg": "image/jpeg", # LibreOffice can convert PDF to JPG/PNG too
            "png": "image/png"
        }
        final_media_type = media_type_map.get(target_format.lower(), "application/octet-stream") # Fallback to generic

        return FileResponse(
            path=str(converted_file_path),
            media_type=final_media_type,
            filename=output_filename,
            background=lambda: shutil.rmtree(processing_dir, ignore_errors=True)
        )
    except HTTPException:
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF to {target_format.upper()} conversion failed: {e}. Ensure LibreOffice is installed on server.")
    finally:
        pass