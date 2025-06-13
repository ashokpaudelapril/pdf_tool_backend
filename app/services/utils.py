from fastapi import UploadFile
import os
import aiofiles
import uuid
import shutil
from pathlib import Path
from typing import Union, List, Optional
import zipfile

TEMP_FILES_ROOT_DIR = Path(os.getenv("TEMP_FILES_DIR", "temp_files"))
TEMP_FILES_ROOT_DIR.mkdir(parents=True, exist_ok=True)

async def save_temp_file(upload_file: UploadFile) -> Path:
    unique_dir = TEMP_FILES_ROOT_DIR / str(uuid.uuid4())
    unique_dir.mkdir(parents=True, exist_ok=True)

    file_extension = Path(upload_file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = unique_dir / unique_filename

    async with aiofiles.open(file_path, 'wb') as out_file:
        while content := await upload_file.read(1024 * 1024):
            await out_file.write(content)
    
    return file_path

def get_temp_file_path(filename: str = None, directory_only: bool = False) -> Path:
    if directory_only:
        unique_dir = TEMP_FILES_ROOT_DIR / str(uuid.uuid4())
        unique_dir.mkdir(parents=True, exist_ok=True)
        return unique_dir
    else:
        if filename:
            unique_dir = TEMP_FILES_ROOT_DIR / str(uuid.uuid4())
            unique_dir.mkdir(parents=True, exist_ok=True)
            return unique_dir / filename
        unique_dir = TEMP_FILES_ROOT_DIR / str(uuid.uuid4())
        unique_dir.mkdir(parents=True, exist_ok=True)
        return unique_dir / str(uuid.uuid4())


def cleanup_temp_file(file_path: Path):
    try:
        if file_path.is_file():
            os.remove(file_path)
            parent_dir = file_path.parent
            if parent_dir != TEMP_FILES_ROOT_DIR and not list(parent_dir.iterdir()):
                shutil.rmtree(parent_dir)
            print(f"Cleaned up temporary file: {file_path}")
        elif file_path.is_dir():
            shutil.rmtree(file_path)
            print(f"Cleaned up temporary directory: {file_path}")
    except OSError as e:
        print(f"Error cleaning up temp file {file_path}: {e}")

def cleanup_temp_files(path: Union[Path, str] = TEMP_FILES_ROOT_DIR):
    target_path = Path(path)
    try:
        if target_path.exists():
            if target_path.is_file():
                os.remove(target_path)
                print(f"Cleaned up temporary file: {target_path}")
                parent_dir = target_path.parent
                if parent_dir != TEMP_FILES_ROOT_DIR and not list(parent_dir.iterdir()):
                    shutil.rmtree(parent_dir)
            elif target_path.is_dir():
                shutil.rmtree(target_path)
                print(f"Cleaned up temporary directory: {target_path}")
        else:
            print(f"No temp files/directory found at {target_path} to clean up.")
    except OSError as e:
        print(f"Error cleaning up temp files at {target_path}: {e}")

def encrypt_file(file_path: Path, password: Optional[str]) -> Path:
    print(f"Encrypting {file_path} (placeholder)")
    return file_path

def decrypt_file(file_path: Path, password: Optional[str]) -> Path:
    print(f"Decrypting {file_path} (placeholder)")
    return file_path


def extract_zip_archive(zip_path: Path, extract_to_dir: Path) -> List[Path]:
    extracted_files = []
    extract_to_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                if member.endswith('/'):
                    continue
                member_path = (extract_to_dir / member).resolve()
                if not member_path.starts_with(extract_to_dir.resolve()):
                    print(f"Skipping potentially malicious path: {member}")
                    continue
                
                member_path.parent.mkdir(parents=True, exist_ok=True)
                
                with zip_ref.open(member) as source, open(member_path, 'wb') as target:
                    shutil.copyfileobj(source, target)
                extracted_files.append(member_path)
        return extracted_files
    except zipfile.BadZipFile:
        raise Exception("Invalid ZIP file provided.")
    except Exception as e:
        raise Exception(f"Failed to extract ZIP archive: {e}")

def create_zip_archive(files_to_zip: List[Path], output_zip_path: Path) -> Path:
    try:
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for file_path in files_to_zip:
                if file_path.is_file():
                    zip_ref.write(file_path, arcname=file_path.name)
                else:
                    print(f"Warning: Skipped non-existent file for zipping: {file_path}")
        return output_zip_path
    except Exception as e:
        raise Exception(f"Failed to create ZIP archive: {e}")