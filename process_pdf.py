"""
Wednesday Folder PDF Processor
Extracts text from PTA PDFs and saves structured JSON data.
Usage: python process_pdf.py <pdf_path> [--date YYYY-MM-DD]
"""
import sys
import json
import os
import re
from datetime import datetime
from pathlib import Path

try:
    import PyPDF2
except ImportError:
    print("Installing PyPDF2...")
    os.system(f"{sys.executable} -m pip install PyPDF2 -q")
    import PyPDF2


def extract_text(pdf_path):
    """Extract all text from a PDF."""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
    return pages


def parse_events(pages, folder_date):
    """Parse extracted text into structured events."""
    full_text = "\n\n".join(pages)
    events = []

    # Known patterns to look for
    # Dates like "March 13", "March 17-20", "Wednesday, March 11th"
    date_pattern = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?,?\s*(?:March|April|May|June|January|February|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{1,2}(?:st|nd|rd|th)?)?'

    return {
        "folder_date": folder_date,
        "raw_text": full_text,
        "page_count": len(pages),
        "pages": pages
    }


def save_data(data, data_dir):
    """Save extracted data as JSON."""
    date_str = data["folder_date"]
    output_path = os.path.join(data_dir, f"{date_str}.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {output_path}")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_pdf.py <pdf_path> [--date YYYY-MM-DD]")
        sys.exit(1)

    pdf_path = sys.argv[1]

    # Parse optional date
    folder_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        folder_date = sys.argv[idx + 1]
    else:
        # Try to extract from filename
        basename = os.path.basename(pdf_path)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', basename)
        if match:
            folder_date = match.group(1)
        else:
            folder_date = datetime.now().strftime("%Y-%m-%d")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"Processing: {pdf_path}")
    pages = extract_text(pdf_path)
    print(f"Extracted {len(pages)} pages with text")

    data = parse_events(pages, folder_date)
    save_data(data, data_dir)


if __name__ == "__main__":
    main()
