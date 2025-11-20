import os
import argparse
import sys
import pymupdf  # PyMuPDF


def split_pdf(input_pdf_path, output_folder, pages_per_file=1, verbose=False):
    """
    Splits a PDF file into multiple smaller PDF files, each containing a specified
    number of pages.

    Args:
        input_pdf_path (str): Path to the input PDF file.
        output_folder (str): Directory where the split PDF files will be saved.
        pages_per_file (int): Number of pages per output PDF file.
        verbose (bool): Print progress messages when True.
    """
    if not os.path.exists(input_pdf_path):
        raise FileNotFoundError(f"Input PDF not found: {input_pdf_path}")
    if not input_pdf_path.lower().endswith(".pdf"):
        raise ValueError(f"Input file is not a PDF: {input_pdf_path}")
    if pages_per_file <= 0:
        raise ValueError("pages_per_file must be a positive integer.")

    os.makedirs(output_folder, exist_ok=True)
    if verbose:
        print(f"Output directory: {output_folder}")

    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as e:
        raise RuntimeError(f"Error opening PDF '{input_pdf_path}': {e}")

    total_pages = doc.page_count
    base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]

    if verbose:
        print(f"Splitting '{input_pdf_path}' ({total_pages} pages) into files with {pages_per_file} pages each.")

    file_index = 1
    for start_page_idx in range(0, total_pages, pages_per_file):
        end_page_idx = min(start_page_idx + pages_per_file, total_pages) - 1

        output_pdf_name = f"{base_name}_part{file_index:03d}.pdf"
        output_pdf_path = os.path.join(output_folder,
            output_pdf_name
        )

        new_pdf = pymupdf.open()
        for page_num in range(start_page_idx, end_page_idx + 1):
            new_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)

        try:
            new_pdf.save(output_pdf_path)
            if verbose:
                print(f"Created '{output_pdf_name}' with pages {start_page_idx+1}-{end_page_idx+1}")
        except Exception as e:
            print(f"Warning: Could not save part '{output_pdf_name}': {e}", file=sys.stderr)
        finally:
            new_pdf.close()
        
        file_index += 1
    
    doc.close()
    if verbose:
        print("PDF splitting complete.")


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Split a PDF file into multiple parts or extract a page range."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # --- Split command ---
    parser_split = subparsers.add_parser("split", help="Split a PDF into multiple files.")
    parser_split.add_argument("input_pdf", help="Path to the input PDF file.")
    parser_split.add_argument("output_folder", help="Directory where the split PDF files will be saved.")
    parser_split.add_argument(
        "--pages-per-file", type=int, default=1,
        help="Number of pages per output PDF file (default: 1)."
    )
    parser_split.add_argument(
        "--verbose", action="store_true", help="Print progress messages."
    )

    # --- Extract command ---
    parser_extract = subparsers.add_parser("extract", help="Extract a range of pages into a new PDF.")
    parser_extract.add_argument("input_pdf", help="Path to the input PDF file.")
    parser_extract.add_argument("output_pdf", help="Path for the output PDF file.")
    parser_extract.add_argument("start_page", type=int, help="The 1-based starting page number.")
    parser_extract.add_argument("end_page", type=int, help="The 1-based ending page number.")
    parser_extract.add_argument(
        "--verbose", action="store_true", help="Print progress messages."
    )

    return parser.parse_args(argv)

def extract_pages(input_pdf_path, output_pdf_path, start_page, end_page, verbose=False):
    """
    Extracts a specific range of pages from a PDF file and saves them as a new PDF.

    Args:
        input_pdf_path (str): Path to the input PDF file.
        output_pdf_path (str): Path to the output PDF file.
        start_page (int): The 1-based starting page number to extract.
        end_page (int): The 1-based ending page number to extract.
        verbose (bool): Print progress messages when True.
    """
    if not os.path.exists(input_pdf_path):
        raise FileNotFoundError(f"Input PDF not found: {input_pdf_path}")
    if not input_pdf_path.lower().endswith(".pdf"):
        raise ValueError(f"Input file is not a PDF: {input_pdf_path}")
    if not output_pdf_path.lower().endswith(".pdf"):
        raise ValueError(f"Output file must be a PDF: {output_pdf_path}")
    if start_page <= 0 or end_page <= 0:
        raise ValueError("Page numbers must be positive integers.")
    if start_page > end_page:
        raise ValueError("Start page cannot be greater than end page.")

    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as e:
        raise RuntimeError(f"Error opening PDF '{input_pdf_path}': {e}")

    total_pages = doc.page_count

    if start_page > total_pages:
        doc.close()
        raise ValueError(f"Start page ({start_page}) exceeds total pages ({total_pages}).")
    if end_page > total_pages:
        if verbose:
            print(f"Warning: End page ({end_page}) exceeds total pages ({total_pages}). Adjusting to {total_pages}.", file=sys.stderr)
        end_page = total_pages

    if verbose:
        print(f"Extracting pages {start_page}-{end_page} from '{input_pdf_path}' to '{output_pdf_path}'.")

    new_pdf = pymupdf.open()
    # PyMuPDF uses 0-based indexing, so we subtract 1
    try:
        new_pdf.insert_pdf(doc, from_page=start_page - 1, to_page=end_page - 1)
        output_dir = os.path.dirname(output_pdf_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        new_pdf.save(output_pdf_path)
        if verbose:
            print(f"Successfully created '{output_pdf_path}' with pages {start_page}-{end_page}.")
    except Exception as e:
        print(f"Warning: Could not save extracted PDF '{output_pdf_path}': {e}", file=sys.stderr)
    finally:
        new_pdf.close()
        doc.close()

def main(argv=None):
    """Main function to execute the script from the command line."""
    args = parse_args(argv)

    try:
        if args.command == "split":
            split_pdf(args.input_pdf, args.output_folder, args.pages_per_file, args.verbose)
        elif args.command == "extract":
            extract_pages(
                args.input_pdf, args.output_pdf,
                args.start_page, args.end_page,
                args.verbose
            )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())