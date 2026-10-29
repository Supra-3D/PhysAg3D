"""Extract Figure 2 from a locally supplied manuscript as a self-contained SVG.

Requires PyMuPDF. The verified crop is for page 4 of the current paper.
The source PDF is never modified.
"""
from pathlib import Path
import argparse
import hashlib
import xml.etree.ElementTree as ET
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets/method.svg"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper", type=Path, help="Local manuscript PDF (not published with the site)")
    paper = parser.parse_args().paper.resolve(strict=True)
    with pymupdf.open(paper) as document:
        page = document[3]
        # Bounds of the original /Im2 figure form, transformed into page coordinates.
        scale, x, bottom = 0.37344, 62.362, 538.736
        width, height = 1260 * scale, 667.56 * scale
        clip = pymupdf.Rect(x, page.rect.height - bottom - height,
                           x + width, page.rect.height - bottom)
        caption = page.search_for("Figure 2.")
        if not caption or caption[0].y0 <= clip.y1:
            raise ValueError("The paper layout changed; verify the Figure 2 crop before exporting")
        text = page.get_text(clip=clip)
        for label in ["Geometric and Physical Priors", "Interactive Asset Synthesis", "Shared interaction representation"]:
            if label not in text:
                raise ValueError(f"The method figure crop does not contain {label!r}")
        page.set_cropbox(clip)
        root = ET.fromstring(page.get_svg_image(text_as_path=True))

    # Large intrinsic dimensions make the full-size dialog useful; vectors remain scalable.
    root.set("width", "3840")
    root.set("height", str(round(3840 * height / width)))
    title = ET.Element(f"{{{SVG_NS}}}title")
    title.text = "PhysAg3D method overview — Figure 2"
    desc = ET.Element(f"{{{SVG_NS}}}desc")
    desc.text = "Extracted from page 4 of the paper. Text and lines are preserved as vectors; source image detail is retained."
    root.insert(0, title)
    root.insert(1, desc)
    root.insert(2, ET.Element(f"{{{SVG_NS}}}rect", {"width": "100%", "height": "100%", "fill": "white"}))
    for element in root.iter():
        if element.tag == f"{{{SVG_NS}}}script":
            raise ValueError("Unexpected script in extracted SVG")
        for key in ["href", f"{{{XLINK_NS}}}href"]:
            href = element.get(key)
            if href and not href.startswith(("#", "data:image/")):
                raise ValueError("The SVG must not depend on external resources")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    OUTPUT.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Extracted Figure 2: {OUTPUT.name}, {OUTPUT.stat().st_size} bytes")
    print("Paper SHA256:", hashlib.sha256(paper.read_bytes()).hexdigest())
    print("SVG viewBox:", root.get("viewBox"))


if __name__ == "__main__":
    main()
