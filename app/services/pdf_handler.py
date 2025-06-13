from PyPDF2 import PdfWriter, PdfReader
from PyPDF2.errors import PdfReadError, DependencyError
from pathlib import Path
from typing import List, Optional, Dict, Any
import os

import fitz

def merge_pdfs(input_paths: List[Path], output_path: Path) -> Path:
    pdf_writer = PdfWriter()
    for input_path in input_paths:
        if not input_path.exists():
            raise FileNotFoundError(f"Input PDF file not found: {input_path}")
        try:
            pdf_reader = PdfReader(input_path)
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
        except PdfReadError:
            raise PdfReadError(f"Error reading PDF file: {input_path}. It might be corrupted or encrypted.")
        except Exception as e:
            raise Exception(f"An unexpected error occurred while processing {input_path}: {e}")

    try:
        with open(output_path, "wb") as out_file:
            pdf_writer.write(out_file)
        return output_path
    except Exception as e:
        raise Exception(f"Error writing merged PDF to {output_path}: {e}")


def split_pdf(input_path: Path, output_directory: Path, pages: str = None, output_prefix: str = "split_part") -> List[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF file not found: {input_path}")

    output_directory.mkdir(parents=True, exist_ok=True)

    try:
        pdf_reader = PdfReader(input_path)
        total_pages = len(pdf_reader.pages)
        split_paths = []

        if pages:
            page_ranges = []
            parts = pages.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    start_str, end_str = part.split('-')
                    try:
                        start = int(start_str)
                        end = int(end_str)
                        if not (1 <= start <= total_pages and 1 <= end <= total_pages and start <= end):
                            raise ValueError(f"Invalid page range: {part}")
                        page_ranges.append((start, end))
                    except ValueError:
                        raise ValueError(f"Invalid page range format: {part}")
                else:
                    try:
                        page_num = int(part)
                        if not (1 <= page_num <= total_pages):
                            raise ValueError(f"Page number out of range: {page_num}")
                        page_ranges.append((page_num, page_num))
                    except ValueError:
                        raise ValueError(f"Invalid page number format: {part}")
            
            for i, (start_page, end_page) in enumerate(page_ranges):
                pdf_writer = PdfWriter()
                for page_num in range(start_page - 1, end_page):
                    pdf_writer.add_page(pdf_reader.pages[page_num])
                
                output_filename = f"{output_prefix}_{i+1}_{start_page}-{end_page}.pdf"
                output_file_path = output_directory / output_filename
                with open(output_file_path, "wb") as out_file:
                    pdf_writer.write(out_file)
                split_paths.append(output_file_path)

        else:
            for i in range(total_pages):
                pdf_writer = PdfWriter()
                pdf_writer.add_page(pdf_reader.pages[i])
                output_filename = f"{output_prefix}_{i+1}.pdf"
                output_file_path = output_directory / output_filename
                with open(output_file_path, "wb") as out_file:
                    pdf_writer.write(out_file)
                split_paths.append(output_file_path)
        
        return split_paths

    except PdfReadError:
        raise PdfReadError(f"Error reading PDF file: {input_path}. It might be corrupted or encrypted.")
    except Exception as e:
        raise Exception(f"An unexpected error occurred while splitting {input_path}: {e}")


def redact_pdf(input_path: Path, output_path: Path, terms_to_redact: Optional[List[str]] = None) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF file not found: {input_path}")

    doc = None
    try:
        doc = fitz.open(input_path)
        
        if terms_to_redact:
            for page in doc:
                for term in terms_to_redact:
                    text_instances = page.search_for(term)
                    
                    for inst in text_instances:
                        page.add_redact_annot(inst, fill=(0, 0, 0), text="")
                
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)

        doc.save(output_path, garbage=3, clean=True, deflate=True)
        return output_path

    except Exception as e:
        raise Exception(f"An error occurred during PDF redaction: {e}")
    finally:
        if doc:
            doc.close()


def scrub_pdf_metadata(input_path: Path, output_path: Path) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF file not found for metadata scrubbing: {input_path}")

    try:
        pdf_reader = PdfReader(input_path)
        pdf_writer = PdfWriter()

        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

        pdf_writer.add_metadata({})

        with open(output_path, "wb") as out_file:
            pdf_writer.write(out_file)
        return output_path

    except PdfReadError:
        raise PdfReadError(f"Error reading PDF file: {input_path}. It might be corrupted or encrypted.")
    except DependencyError as e:
        raise Exception(f"PyPDF2 dependency error during metadata scrubbing for {input_path}: {e}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred during metadata scrubbing for {input_path}: {e}")


def fill_and_flatten_pdf_form(
    input_path: Path,
    output_path: Path,
    form_data: Dict[str, Any],
    flatten: bool = True
) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF form file not found: {input_path}")

    try:
        pdf_reader = PdfReader(input_path)
        pdf_writer = PdfWriter()

        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

        pdf_writer.update_page_form_field_values(pdf_reader.pages[0], form_data)
        
        if flatten:
            pdf_writer.flatten_forms()

        with open(output_path, "wb") as out_file:
            pdf_writer.write(out_file)
        return output_path

    except PdfReadError:
        raise PdfReadError(f"Error reading PDF file: {input_path}. It might be corrupted or encrypted, or not a valid PDF form.")
    except DependencyError as e:
        raise Exception(f"PyPDF2 dependency error during form filling for {input_path}: {e}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred during PDF form filling: {e}")