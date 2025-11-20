import os
import argparse
import sys
from PIL import Image


def convert_images_to_pdf(image_paths, output_pdf_path, dpi=300, verbose=False):
    """
    Convert a list of image files into a single PDF document.

    Args:
        image_paths (list): A list of paths to input image files.
        output_pdf_path (str): Path to the output PDF file.
        dpi (int): Resolution in DPI for the output PDF (default 300).
        verbose (bool): Print progress when True.
    """
    if not image_paths:
        raise ValueError("No image paths provided.")

    images = []
    for i, img_path in enumerate(image_paths):
        if verbose:
            print(f"Processing image {i+1}/{len(image_paths)}: {img_path}")
        try:
            img = Image.open(img_path).convert("RGB")
            images.append(img)
        except Exception as e:
            print(f"Warning: Could not open or convert image '{img_path}': {e}", file=sys.stderr)
            continue

    if not images:
        raise RuntimeError("No valid images were processed to create the PDF.")

    first_image = images[0]
    rest_images = images[1:]

    try:
        first_image.save(
            output_pdf_path,
            "PDF",
            resolution=dpi,
            save_all=True,
            append_images=rest_images,
        )
        if verbose:
            print(f"Successfully created PDF: {output_pdf_path}")
    except Exception as e:
        raise RuntimeError(f"Error saving PDF '{output_pdf_path}': {e}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert images from a directory or specified files into a single PDF."
    )
    parser.add_argument(
        "input_path", help="Path to an image file or a directory containing image files."
    )
    parser.add_argument(
        "output_pdf", help="Path to the output PDF file (e.g., output.pdf)"
    )
    parser.add_argument(
        "--dpi", type=int, default=300, help="Resolution in DPI for the output PDF (default: 300)"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print progress messages"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    input_path = args.input_path
    output_pdf = args.output_pdf

    image_paths = []
    if os.path.isdir(input_path):
        # Collect all common image file types from the directory
        for filename in sorted(os.listdir(input_path)):
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
                image_paths.append(os.path.join(input_path, filename))
        if not image_paths:
            print(f"Error: No image files found in directory '{input_path}'.", file=sys.stderr)
            return 1
    elif os.path.isfile(input_path):
        if not input_path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
            print(f"Error: Input file '{input_path}' is not a recognized image format.", file=sys.stderr)
            return 1
        image_paths.append(input_path)
    else:
        print(f"Error: Input path '{input_path}' is neither a file nor a directory.", file=sys.stderr)
        return 1

    try:
        convert_images_to_pdf(image_paths, output_pdf, dpi=args.dpi, verbose=args.verbose)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())