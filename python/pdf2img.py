import os
import argparse
import sys
import pymupdf  # PyMuPDF


def convert_pdf_to_images(pdf_path, output_folder, dpi=300, first_page=None, last_page=None, image_format="png", verbose=False):
    """Convert a PDF into images using PyMuPDF.

    Args:
        pdf_path (str): Path to input PDF.
        output_folder (str): Directory to save images.
        dpi (int): Resolution in DPI for output images (default 200).
        first_page (int|None): 1-based first page to convert. If None, starts at 1.
        last_page (int|None): 1-based last page to convert. If None, ends at last page.
        image_format (str): Image file format/extension (png, jpg, etc.).
        verbose (bool): Print progress when True.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        if verbose:
            print(f"Created output directory: {output_folder}")

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Unable to open PDF '{pdf_path}': {e}")

    page_count = doc.page_count
    start = 0 if first_page is None else max(0, first_page - 1)
    end = page_count - 1 if last_page is None else min(page_count - 1, last_page - 1)

    if start > end:
        doc.close()
        raise ValueError("Invalid page range: start page is after end page")

    if verbose:
        print(f"Converting '{pdf_path}' pages {start+1}..{end+1} to images (dpi={dpi}, format={image_format})...")

    matrix = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)

    try:
        for i in range(start, end + 1):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=matrix)
            image_name = f"page_{i+1}.{image_format}"
            image_path = os.path.join(output_folder, image_name)
            pix.save(image_path)
            if verbose:
                print(f"Saved: {image_path}")
    finally:
        doc.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Convert a PDF file into a series of images.")
    parser.add_argument("pdf_path", help="Path to the input PDF file.")
    parser.add_argument("output_folder", help="Directory where the output images will be saved.")
    parser.add_argument("--dpi", type=int, default=200, help="DPI/resolution for output images (default: 200)")
    parser.add_argument("--first", type=int, default=None, help="First page to convert (1-based)")
    parser.add_argument("--last", type=int, default=None, help="Last page to convert (1-based)")
    parser.add_argument("--format", default="png", choices=["png", "jpg", "jpeg"], help="Output image format (png, jpg)")
    parser.add_argument("--verbose", action="store_true", help="Print progress messages")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    input_pdf_file = args.pdf_path
    output_directory = args.output_folder
    # create a subdirectory inside output_directory named after the PDF (without extension)
    pdf_basename = os.path.splitext(os.path.basename(input_pdf_file))[0]
    final_output_dir = os.path.join(output_directory, pdf_basename)

    if not os.path.exists(input_pdf_file):
        print(f"Error: PDF file not found at '{input_pdf_file}'", file=sys.stderr)
        return 2

    if not input_pdf_file.lower().endswith(".pdf"):
        print(f"Error: The specified file '{input_pdf_file}' is not a PDF.", file=sys.stderr)
        return 3

    try:
        convert_pdf_to_images(
            input_pdf_file,
            final_output_dir,
            dpi=args.dpi,
            first_page=args.first,
            last_page=args.last,
            image_format=args.format,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"Error converting PDF: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print("Conversion completed successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
