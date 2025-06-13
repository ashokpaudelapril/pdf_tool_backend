# 🚀 Backend (FastAPI)

This part of the repository contains the FastAPI backend for the Secure PDF Toolkit. It handles all the heavy-lifting of PDF processing, conversion, and manipulation.

## Technologies Used

- **Python 3.9+**
- **FastAPI**: A modern, fast (high-performance) web framework for building APIs.
- **Uvicorn**: The ASGI server used for running FastAPI applications.
- **PyPDF2**: Utilized for fundamental PDF operations like merging, splitting, and basic content manipulation.
- **PyMuPDF (fitz)**: Provides advanced capabilities for PDF handling, including rendering pages to images, powerful text/image extraction, and precise redaction.
- **Pillow (PIL)**: An imaging library used for general image processing, particularly in converting images to PDF.
- **ReportLab**: Employed for generating new PDF documents from scratch, such as converting text or CSV data into PDF.
- **Pandas**: A data manipulation library essential for processing tabular data, especially when converting CSV files to PDF.
- **python-docx**: Used for interacting with Word documents, specifically in conversion workflows (e.g., DOCX to PDF).
- **python-pptx**: Used for interacting with PowerPoint presentations, specifically in conversion workflows (e.g., PPTX to PDF).
- **aiofiles**: Enables asynchronous file operations, improving performance for file I/O.
- **subprocess module**: Facilitates interaction with external command-line tools like LibreOffice for more complex or high-fidelity conversions.

## System Dependencies (Crucial for Functionality!)

The backend relies on several external system-level tools. You must install these on your development machine and your deployment environment for full functionality.

### LibreOffice

**Purpose**: Essential for converting various office document formats (DOCX, XLSX, PPTX) to and from PDF.

- macOS (Homebrew): `brew install --cask libreoffice`
- Linux (apt): `sudo apt update && sudo apt install libreoffice`
- Windows: Download from the LibreOffice website and add `soffice.exe` to your system's PATH.

### Tesseract-OCR

**Purpose**: The core engine for Optical Character Recognition (OCR), enabling text extraction from scanned PDFs.

- macOS (Homebrew): `brew install tesseract`
- Linux (apt): `sudo apt update && sudo apt install tesseract-ocr`
- Windows: Download from the Tesseract GitHub and add to PATH.

### Poppler

**Purpose**: A command-line utility toolkit that `pdf2image` relies on for converting PDF pages into images.

- macOS (Homebrew): `brew install poppler`
- Linux (apt): `sudo apt update && sudo apt install poppler-utils`
- Windows: Download Poppler for Windows and add the `bin` directory to PATH.

## Setup (Local Development)

### 1. Clone the repository:

```bash
git clone <your-repo-url>
cd "PDF Editor"
```

### 2. Navigate to the backend directory:

```bash
cd backend
```

### 3. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# On Windows:
.env\Scriptsctivate
```

### 4. Install Python dependencies:

```bash
pip install -r requirements.txt
```

Ensure your `requirements.txt` includes:
```
fastapi
uvicorn[standard]
PyPDF2
PyMuPDF
pdf2image
pytesseract
Pillow
python-docx
python-pptx
translate
reportlab
pandas
aiofiles
python-multipart
```

### 5. Install system dependencies listed above.

## Running the Backend (Local Development)

Activate your virtual environment and run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:
- API base: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Backend Structure

- **app/main.py**: Sets up the FastAPI app, CORS, and registers routers.
- **app/routers/pdf/basic_tools.py**: Endpoints for simple PDF operations like merge/split.
- **app/routers/pdf/advanced_tools.py**: Endpoints for OCR, redaction, metadata scrubbing, etc.
- **app/routers/pdf/batch_tools.py**: For batch operations on ZIP files of PDFs.
- **app/routers/convert/conversion.py**: Conversion to/from PDF (DOCX, PPTX, Image, etc).
- **app/services/pdf_handler.py**: Core logic for handling PDF operations.
- **app/services/ocr.py**: OCR logic using Tesseract.
- **app/services/utils.py**: Helper functions for temp files, zipping, etc.
- **temp_files/**: Auto-created directory to store intermediate files (auto-cleaned).

## Deployment (Railway)

Add a `Procfile` in your `backend/` folder with:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

If using cloud storage (e.g., AWS S3), set the following in Railway:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `S3_BUCKET_NAME`
