import os
import sys
import argparse
from pathlib import Path

# ---------------------------
# PDF -> images (PyMuPDF)
# ---------------------------
import pymupdf  # package name is pymupdf; module exposes pymupdf namespace
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

# ---------------------------
# OCR (Surya)
# ---------------------------
from surya.foundation import FoundationPredictor
from surya.recognition import RecognitionPredictor
from surya.detection import DetectionPredictor

# ---------------------------
# Translation (Argos)
# ---------------------------
import argostranslate.package
import argostranslate.translate


# ===========================
# Argos helpers
# ===========================
def setup_argos_translation(from_code: str = "ar", to_code: str = "id") -> None:
    """
    Ensure Argos translation packages are installed.
    Tries to find a direct package (from_code -> to_code). If not found,
    it falls back to installing intermediate packages via English
    (from_code -> en, and en -> to_code).
    """
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()

    # Filter out None values from packages list
    valid_packages = [p for p in available_packages if p]

    def find_package(f_code, t_code):
        try:
            return next(
                p for p in valid_packages
                if p.from_code == f_code and p.to_code == t_code
            )
        except StopIteration:
            return None

    # 1. Try to find direct translation package
    direct_package = find_package(from_code, to_code)
    if direct_package:
        print(f"Found direct translation package: {from_code} -> {to_code}")
        argostranslate.package.install_from_path(direct_package.download())
        return

    # 2. Fallback to intermediate translation via English
    if from_code != "en" and to_code != "en":
        print(f"No direct package found. Trying intermediate translation via 'en'.")
        from_en_package = find_package(from_code, "en")
        en_to_package = find_package("en", to_code)

        if from_en_package and en_to_package:
            print(f"Found intermediate packages: {from_code}->en and en->{to_code}")
            argostranslate.package.install_from_path(from_en_package.download())
            argostranslate.package.install_from_path(en_to_package.download())
            return

    # 3. If no path found, raise an error
    raise RuntimeError(
        f"Could not find a translation path for {from_code} -> {to_code}. "
        f"Neither a direct package nor an intermediate path via 'en' was found."
    )


def translate_text(text: str, from_code: str = "ar", to_code: str = "id") -> str:
    """
    Translate text with Argos. Assumes packages are already installed.
    Argos can auto-pivot via intermediate languages if needed.
    """
    # Simple one-liner API:
    return argostranslate.translate.translate(text, from_code, to_code)


# ===========================
# PDF -> PIL images
# ===========================
def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[Image.Image]:
    doc = pymupdf.open(pdf_path)
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)

    images: list[Image.Image] = []
    for page_index in tqdm(range(len(doc)), desc="Rendering PDF pages"):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        images.append(img)

    doc.close()
    return images


# ===========================
# OCR with Surya
# ===========================
def init_surya_ocr():
    foundation_predictor = FoundationPredictor()
    recognition_predictor = RecognitionPredictor(foundation_predictor)
    detection_predictor = DetectionPredictor()
    return recognition_predictor, detection_predictor


def run_ocr_on_page(
    image: Image.Image,
    recognition_predictor: RecognitionPredictor,
    detection_predictor: DetectionPredictor,
):
    """
    Run Surya OCR on a single PIL Image page.
    Returns the page prediction dict (with text_lines, etc.).
    """
    predictions = recognition_predictor([image], det_predictor=detection_predictor)
    return predictions[0]  # list of pages; we only passed one


# ===========================
# Drawing / overlay helpers
# ===========================
def load_font(font_size: int = 16) -> ImageFont.FreeTypeFont:
    """
    Load a TTF font. Adjust path as needed for your environment.
    For Indonesian text, any Latin font is fine.
    """
    # Try a common font; fallback to default if not found
    possible_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/System/Library/Fonts/Supplemental/Arial.ttf",     # macOS
        "C:/Windows/Fonts/arial.ttf",                       # Windows
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, font_size)

    return ImageFont.load_default()


def get_dynamic_font(bbox, font_path: str | None) -> ImageFont.FreeTypeFont:
    """
    Determines an appropriate font size based on the bbox height and loads the font.
    A simple heuristic is to use the bbox height as the font size.
    bbox: (x1, y1, x2, y2)
    """
    _x1, y1, _x2, y2 = bbox
    bbox_height = y2 - y1

    # Heuristic: font size is often close to pixel height of the line.
    # We can use a slightly smaller size to ensure it fits.
    font_size = int(bbox_height * 0.8)
    if font_size <= 0:
        font_size = 1 # fallback for tiny boxes

    if font_path:
        return ImageFont.truetype(font_path, font_size)

    return ImageFont.load_default(size=font_size)


def draw_text_in_box(draw: ImageDraw.ImageDraw, text: str, bbox, font) -> None:
    """
    Simple word-wrapping inside a bbox using PIL.
    bbox: (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = bbox
    max_width = x2 - x1
    max_height = y2 - y1

    if max_width <= 0 or max_height <= 0 or not text.strip():
        return

    words = text.split()
    lines = []
    current = ""

    for w in words:
        tmp = (current + " " + w).strip()
        if draw.textlength(tmp, font=font) <= max_width:
            current = tmp
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)

    ascent, descent = font.getmetrics()
    line_height = ascent + descent + 2

    y = y1
    for line in lines:
        if y + line_height > y2:
            break  # don't overflow box
        draw.text((x1, y), line, font=font, fill="black")
        y += line_height


def overlay_translations_on_image(
    image: Image.Image,
    page_prediction: dict,
    from_code: str = "ar",
    to_code: str = "id",
) -> Image.Image:
    """
    Create a new image with Indonesian text drawn in the same locations
    as the original Arabic lines.
    """
    # You can choose: draw on a copy of original or on white background.
    # Here we use white background for a clean translated PDF.
    translated_img = Image.new("RGB", image.size, "white")
    draw = ImageDraw.Draw(translated_img)

    # Find a valid font path once to avoid searching for it in a loop
    font_path = next(
        (p for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ] if os.path.exists(p)),
        None
    )

    text_lines = page_prediction.text_lines  # list of dicts
    for line in text_lines:
        src_text = line.text
        bbox = line.bbox  # (x1, y1, x2, y2)
        try:
            dest_text = translate_text(src_text, from_code=from_code, to_code=to_code)
        except AttributeError as e:
            eng_text = translate_text(src_text, from_code=from_code, to_code='en')
            dest_text = translate_text(eng_text, from_code='en', to_code=to_code)
        except Exception as e:
            # Fallback: keep original text if translation fails
            dest_text = src_text + f" (ERR: {e})"

        font = get_dynamic_font(bbox, font_path)
        draw_text_in_box(draw, dest_text, bbox, font)

    return translated_img


# ===========================
# Images -> PDF
# ===========================
def images_to_pdf(images: list[Image.Image], output_pdf_path: str, dpi: int = 300) -> None:
    """
    Save a list of PIL Images as a multi-page PDF.
    """
    if not images:
        raise ValueError("No images to save")

    # Convert all to RGB (PDF requirement)
    images_rgb = [img.convert("RGB") for img in images]

    first, *rest = images_rgb
    first.save(
        output_pdf_path,
        "PDF",
        resolution=dpi,
        save_all=True,
        append_images=rest,
    )


# ===========================
# Main pipeline
# ===========================
def translate_pdf(input_pdf: str, output_pdf: str, from_code: str = "ar", to_code: str = "id", dpi: int = 300):
    # 1. Prepare translation models (Argos)
    print(f"Setting up Argos translation ({from_code} -> {to_code})...")
    setup_argos_translation(from_code=from_code, to_code=to_code)

    # 2. Convert PDF to images
    print("Rendering PDF to images...")
    page_images = pdf_to_images(input_pdf, dpi=dpi)

    # 3. Init Surya OCR
    print("Initializing Surya OCR...")
    recognition_predictor, detection_predictor = init_surya_ocr()

    translated_images: list[Image.Image] = []

    # 4. For each page: OCR -> translate -> overlay
    for idx, img in enumerate(tqdm(page_images, desc="OCR + translate pages")):
        page_pred = run_ocr_on_page(img, recognition_predictor, detection_predictor)
        translated_img = overlay_translations_on_image(
            img,
            page_pred,
            from_code=from_code,
            to_code=to_code,
        )
        translated_images.append(translated_img)

    # 5. Save new PDF
    print(f"Saving translated PDF to {output_pdf} ...")
    images_to_pdf(translated_images, output_pdf_path=output_pdf, dpi=dpi)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translate an Arabic PDF to Indonesian (renders, OCR, translate, overlay, save)."
    )
    parser.add_argument("input_pdf", help="Path to input PDF file (Arabic)")
    parser.add_argument("output_base", help="Base output directory where per-file subdirectory will be created")
    parser.add_argument("--src_lang", type=str, default="ar", help="Source language code (default: ar)")
    parser.add_argument("--dst_lang", type=str, default="id", help="Destination language code (default: id)")
    parser.add_argument("--dpi", type=int, default=300, help="Rendering DPI (default: 300)")
    args = parser.parse_args()

    input_pdf_path = args.input_pdf
    output_base = args.output_base

    if not os.path.exists(input_pdf_path):
        print(f"Error: input PDF not found: {input_pdf_path}", file=sys.stderr)
        raise SystemExit(2)

    if not input_pdf_path.lower().endswith(".pdf"):
        print(f"Error: input file is not a PDF: {input_pdf_path}", file=sys.stderr)
        raise SystemExit(3)

    # Create per-file subdirectory under output_base named after input PDF (without extension)
    pdf_basename = os.path.splitext(os.path.basename(input_pdf_path))[0]
    final_output_dir = os.path.join(output_base, pdf_basename)
    os.makedirs(final_output_dir, exist_ok=True)

    # Build output PDF path inside the per-file directory
    output_pdf_path = os.path.join(final_output_dir, f"{pdf_basename}_en.pdf")

    try:
        translate_pdf(input_pdf_path, output_pdf_path, from_code=args.src_lang, to_code=args.dst_lang, dpi=args.dpi)
    except Exception as e:
        print(f"Translation failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    else:
        print(f"Saved translated PDF to: {output_pdf_path}")
