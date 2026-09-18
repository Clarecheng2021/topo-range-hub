"""Run CPU OCR for a topology image and save machine-readable artifacts.

This is the local, low-resource recognizer used before the project switches
to a DeepSeek-OCR-2 GPU adapter. It deliberately outputs raw OCR evidence
(text, boxes and scores) rather than inventing devices or links.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from paddleocr import PaddleOCR


def main() -> None:
    parser = argparse.ArgumentParser(description="Recognize topology-image text on CPU.")
    parser.add_argument("image", type=Path, help="Path to a PNG, JPG, JPEG or WebP image")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "ocr",
        help="Folder for OCR JSON and annotated image",
    )
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"Image not found: {image}")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine="paddle",
    )

    results = ocr.predict(str(image))
    page_count = 0
    for result in results:
        result.save_to_json(save_path=str(output))
        result.save_to_img(save_path=str(output))
        page_count += 1

    print(f"OCR completed: {page_count} page(s)")
    print(f"Artifacts saved to: {output}")


if __name__ == "__main__":
    main()
