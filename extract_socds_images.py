"""
Extract and download all images from SOCDS newsletter emails.
Saves to socds/images/week_NN/ folders.
"""
import requests
import time
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent.resolve()
EMAIL_DIR = SCRIPT_DIR / "socds" / "emails"
IMAGE_DIR = SCRIPT_DIR / "socds" / "images"


def extract_images():
    total = 0
    skipped = 0

    for html_file in sorted(EMAIL_DIR.glob("*.html")):
        week_name = html_file.stem  # e.g. week_25_2026-02-28
        week_dir = IMAGE_DIR / week_name
        week_dir.mkdir(parents=True, exist_ok=True)

        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        imgs = soup.find_all('img')
        count = 0

        for img in imgs:
            src = img.get('src', '')
            width = img.get('width', '0')

            # Skip tracking pixels (1x1), logos, badges
            if width in ('1', ''):
                continue
            src_lower = src.lower()
            if 'logo' in src_lower or 'badge' in src_lower:
                continue
            if 'SOCDS-81001' in src:
                continue
            if not src.startswith('http'):
                continue

            # Derive filename from URL
            parsed = urlparse(src)
            filename = Path(parsed.path).name
            if not filename or '.' not in filename:
                filename = f"img_{count:03d}.jpg"

            dest = week_dir / filename
            if dest.exists():
                skipped += 1
                count += 1
                continue

            try:
                resp = requests.get(src, timeout=15)
                resp.raise_for_status()
                with open(dest, 'wb') as out:
                    out.write(resp.content)
                count += 1
                total += 1
            except Exception as e:
                print(f"  FAILED: {filename} - {e}")

            # Be polite to the CDN
            if count % 20 == 0:
                time.sleep(0.5)

        print(f"{week_name}: {count} images saved")

    print(f"\nDone! {total} new images downloaded, {skipped} already existed")
    print(f"Saved to: {IMAGE_DIR}")


if __name__ == "__main__":
    extract_images()
