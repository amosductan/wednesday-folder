"""
Auto-curate Maya (St. Cloud) events from raw PDF text.

Reads data/YYYY-MM-DD.json (output of process_pdf.py), extracts structured
events using heuristics, and merges into data/events.json.

Usage:
    python auto_curate.py                  # Process all unprocessed PDFs
    python auto_curate.py --date 2026-03-11  # Process a specific date
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
EVENTS_FILE = DATA_DIR / "events.json"

# Month name → number
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Category keywords (checked against title + details text)
CATEGORY_RULES = [
    ("fundraiser", ["fundrais", "dine at", "chipotle", "panera", "bake sale", "pie sale"]),
    ("meeting", ["pta general meeting", "pta meeting", "diversity council meeting"]),
    ("deadline", ["registration", "deadline", "sign up by", "closes", "enrollment"]),
    ("school-spirit", ["dress-up", "spirit day", "spirit wear", "pajama", "read across"]),
    ("community-event", ["ice skating", "trunk or treat", "holiday bazaar", "celebration"]),
    ("volunteer", ["volunteer", "donations needed", "costume drive", "food drive", "winter drive"]),
    ("membership", ["pta membership", "join the pta"]),
    ("school-event", ["career week", "book fair", "stem festival", "veterans day",
                       "picture retake", "character parade"]),
]

# Recurring items — detected by keyword in raw text, added as-is
RECURRING_TEMPLATES = [
    {
        "trigger": "benevity",
        "event": {
            "title": "PTA Matching Gifts via Benevity",
            "date": None,
            "date_display": "Ongoing",
            "category": "fundraiser",
            "details": "PTA accepts matching gifts through Benevity. PTA TIN: 51-0224833",
            "links": [],
        },
    },
    {
        "trigger": "membership@stcloudpta",
        "event": {
            "title": "PTA Membership",
            "date": None,
            "date_display": "2025-26 School Year",
            "category": "membership",
            "details": "$15 membership. Email membership@stcloudpta.org",
            "links": [{"label": "Join the PTA", "url": "https://stcloudpta.givebacks.com/shop"}],
        },
    },
    {
        "trigger": "diversitycouncilstc@gmail",
        "event": {
            "title": "Diversity Council - Heritage Month Contributions",
            "date": None,
            "date_display": "Ongoing",
            "category": "volunteer",
            "details": "Seeking families with info to share for heritage months. Contact diversitycouncilstc@gmail.com",
            "links": [],
        },
    },
]

# School year range for resolving month → year
SCHOOL_YEAR_START = 8  # August

# Known event patterns — if raw text matches, use a clean title
KNOWN_EVENTS = [
    {
        "pattern": r"pta\s*(?:general\s*)?meeting|march\s*pta|tonight.*meeting",
        "title": "PTA General Meeting",
        "category": "meeting",
    },
    {
        "pattern": r"ice\s*skating|codey\s*arena",
        "title": "Family Ice Skating Night",
        "category": "community-event",
    },
    {
        "pattern": r"career\s*week",
        "title": "Career Week",
        "category": "school-event",
    },
    {
        "pattern": r"trunk\s*or\s*treat",
        "title": "Trunk or Treat",
        "category": "community-event",
    },
    {
        "pattern": r"book\s*fair|scholastic",
        "title": "Scholastic Book Fair",
        "category": "school-event",
    },
    {
        "pattern": r"holiday\s*bazaar",
        "title": "Holiday Bazaar",
        "category": "community-event",
    },
    {
        "pattern": r"stem\s*festival",
        "title": "Family STEM Festival",
        "category": "school-event",
    },
    {
        "pattern": r"food\s*drive",
        "title": "Food Drive",
        "category": "community-event",
    },
    {
        "pattern": r"winter\s*drive",
        "title": "Winter Drive - Donations",
        "category": "volunteer",
    },
    {
        "pattern": r"veterans?\s*day",
        "title": "Veterans Day March",
        "category": "school-event",
    },
    {
        "pattern": r"bake\s*sale|election\s*day.*bake",
        "title": "Election Day Bake Sale",
        "category": "fundraiser",
    },
    {
        "pattern": r"pie\s*sale|splurge\s*bakery",
        "title": "Holiday Pie Sale",
        "category": "fundraiser",
    },
    {
        "pattern": r"costume\s*drive",
        "title": "Costume Drive",
        "category": "volunteer",
    },
    {
        "pattern": r"spirit\s*day|spirit\s*wear",
        "title": "Spirit Day",
        "category": "school-spirit",
    },
    {
        "pattern": r"read\s*across\s*america|dress.up\s*week",
        "title": "Read Across America Week",
        "category": "school-spirit",
    },
    {
        "pattern": r"black\s*history.*celebration",
        "title": "Black History Family Celebration Night",
        "category": "school-event",
    },
    {
        "pattern": r"chipotle",
        "title": "Chipotle Fundraiser Night",
        "category": "fundraiser",
    },
    {
        "pattern": r"panera",
        "title": "Panera Fundraiser Night",
        "category": "fundraiser",
    },
    {
        "pattern": r"asp\s*(?:spring\s*)?registration|after\s*school\s*program",
        "title": "After School Program (ASP) Registration",
        "category": "deadline",
    },
    {
        "pattern": r"diversity\s*council\s*meeting",
        "title": "Diversity Council Meeting",
        "category": "meeting",
    },
    {
        "pattern": r"kindergarten\s*pre.?registration",
        "title": "Kindergarten Pre-Registration",
        "category": "school-event",
    },
]

# Skip pages that are purely boilerplate (PTA membership flyer, Benevity, etc.)
SKIP_PAGE_PATTERNS = [
    r"^E\s*L\s*E",  # OCR header "E L E M ENTARY SCHOOL"
    r"^(?:ST\.?\s*CLOUD)\s",
    r"^JOIN\s+(?:THE\s+PTA|NOW)",
    r"^O\s*UR\s+PTA\s+NO",
    r"^GET\s+YOUR",
    r"^ENTARY",
]


def resolve_year(month_num, folder_date_str):
    """Resolve the year for an event month based on the folder date's school year."""
    fd = datetime.strptime(folder_date_str, "%Y-%m-%d")
    # School year spans Aug-Jul. If folder is Jan-Jul, events in Aug-Dec are prev year.
    if month_num >= SCHOOL_YEAR_START:
        # Fall semester month
        if fd.month < SCHOOL_YEAR_START:
            return fd.year - 1
        return fd.year
    else:
        # Spring semester month
        if fd.month >= SCHOOL_YEAR_START:
            return fd.year + 1
        return fd.year


def extract_dates(text, folder_date):
    """Find date mentions in text. Returns list of (date_str, display_str, span_info)."""
    results = []

    # Pattern: "Month Day" or "Month Day-Day" with optional weekday prefix
    pattern = (
        r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s*)?"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?)?"
    )

    for m in re.finditer(pattern, text, re.IGNORECASE):
        month_name = m.group(1).lower()
        day_start = int(m.group(2))
        day_end = int(m.group(3)) if m.group(3) else None
        month_num = MONTHS[month_name]
        year = resolve_year(month_num, folder_date)

        date_str = f"{year}-{month_num:02d}-{day_start:02d}"
        display = m.group(0).strip()
        # Clean up display
        display = re.sub(r"\s+", " ", display)

        if day_end:
            date_end_str = f"{year}-{month_num:02d}-{day_end:02d}"
            results.append({
                "date_start": date_str,
                "date_end": date_end_str,
                "date_display": display,
            })
        else:
            results.append({
                "date": date_str,
                "date_display": display,
            })

    return results


def extract_urls(text):
    """Find URLs in text."""
    urls = []
    # Full URLs
    for m in re.finditer(r"https?://[^\s<>\"')\]]+", text):
        url = m.group(0).rstrip(".,;:")
        urls.append(url)
    # bit.ly shortlinks
    for m in re.finditer(r"bit\.ly/[\w-]+", text):
        urls.append("https://" + m.group(0))
    # tinyurl
    for m in re.finditer(r"tinyurl\.com/[\w-]+", text):
        urls.append("https://" + m.group(0))
    # Deduplicate preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def classify_category(title, details):
    """Determine event category from title and details text."""
    combined = (title + " " + details).lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return "school-event"


def make_link_label(url):
    """Generate a short label for a URL."""
    lower = url.lower()
    if "signup" in lower or "signupgenius" in lower or "volunteer" in lower:
        return "Sign Up / Volunteer"
    if "register" in lower or "homeroom" in lower:
        return "Register"
    if "bit.ly" in lower or "tinyurl" in lower:
        return "More Info"
    if "givebacks" in lower:
        return "Join the PTA"
    return "Link"


def segment_pages(pages):
    """Split pages into logical event blocks.

    Each page of a Wednesday Folder PDF is typically one flyer/announcement.
    Returns the list of page texts as-is (each page = one potential event block).
    """
    return pages


def should_skip_page(page_text):
    """Check if a page is pure boilerplate that should be skipped."""
    # Check first line
    first_line = page_text.strip().split("\n")[0].strip()
    for pat in SKIP_PAGE_PATTERNS:
        if re.match(pat, first_line, re.IGNORECASE):
            return True
    # Also check collapsed text (no newlines) for OCR junk like E\nL\nE\nM\nENTARY
    collapsed = re.sub(r"\s+", " ", page_text.strip())[:80]
    if re.match(r"^E L E M ENTARY", collapsed, re.IGNORECASE):
        return True
    if re.match(r"^O UR PTA", collapsed, re.IGNORECASE):
        return True
    # Skip if page has no meaningful content (just school name/logo text)
    alpha_text = re.sub(r"[^a-zA-Z ]", "", collapsed).strip()
    if len(alpha_text) < 15:
        return True
    return False


def clean_ocr_text(text):
    """Fix common OCR spacing artifacts from PDF extraction."""
    # Fix spaced-out words like "FAM ILY" → "FAMILY", "SP ECIA L" → "SPECIAL"
    # Only fix ALL-CAPS sequences
    def fix_spaced_caps(m):
        return m.group(0).replace(" ", "")

    text = re.sub(r"\b(?:[A-Z] ){2,}[A-Z]\b", fix_spaced_caps, text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def match_known_event(block_text):
    """Check if block text matches a known event pattern. Returns (title, category) or None."""
    lower = block_text.lower()
    for ke in KNOWN_EVENTS:
        if re.search(ke["pattern"], lower):
            return ke["title"], ke["category"]
    return None


def extract_event_from_block(block_text, folder_date, all_urls):
    """Try to extract a structured event from a block of text."""
    if should_skip_page(block_text):
        return None

    clean = clean_ocr_text(block_text)

    # Check known events first
    known = match_known_event(block_text)

    # Find dates in this block
    dates = extract_dates(block_text, folder_date)

    # Find URLs in this block
    block_urls = extract_urls(block_text)

    if known:
        title, category = known
    else:
        # Build a title from the first meaningful line
        lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]
        title_candidates = []
        for line in lines[:5]:
            stripped = re.sub(r"[^a-zA-Z0-9 ]", "", line).strip()
            if 5 < len(stripped) < 80 and not stripped.startswith("http"):
                title_candidates.append(line.strip())

        if not title_candidates:
            return None

        title = title_candidates[0]
        title = re.sub(r"\s+", " ", title).strip()
        # Remove trailing punctuation/junk
        title = re.sub(r"[:\-–,]+$", "", title).strip()
        category = None

    # Build details from the text (truncated, cleaned)
    details_lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]
    details = " ".join(details_lines[:8])
    if len(details) > 300:
        details = details[:297] + "..."

    if not category:
        category = classify_category(title, details)

    # Build event dict
    event = {
        "title": title,
        "category": category,
        "details": details,
        "links": [{"label": make_link_label(u), "url": u} for u in block_urls],
    }

    # Attach date info
    if dates:
        best = dates[0]
        event.update(best)
    else:
        event["date"] = None
        event["date_display"] = "See details"

    return event


def curate_from_raw(raw_data):
    """Extract events from raw PDF data dict."""
    folder_date = raw_data["folder_date"]
    pages = raw_data.get("pages", [])
    full_text = raw_data.get("raw_text", "")
    all_urls = extract_urls(full_text)

    events = []
    seen_titles = set()

    # Process each page as a potential event block
    for page_text in pages:
        if not page_text or len(page_text.strip()) < 20:
            continue

        event = extract_event_from_block(page_text, folder_date, all_urls)
        if event:
            # Deduplicate by normalized title
            norm_title = re.sub(r"[^a-z0-9]", "", event["title"].lower())
            if norm_title not in seen_titles:
                seen_titles.add(norm_title)
                events.append(event)

    # Check for recurring items in full text
    lower_text = full_text.lower()
    for tmpl in RECURRING_TEMPLATES:
        if tmpl["trigger"] in lower_text:
            norm = re.sub(r"[^a-z0-9]", "", tmpl["event"]["title"].lower())
            if norm not in seen_titles:
                seen_titles.add(norm)
                events.append(dict(tmpl["event"]))  # Copy

    # Build summary
    dated_events = [e for e in events if e.get("date") or e.get("date_start")]
    titles = [e["title"] for e in dated_events[:4]]
    summary = ", ".join(titles) + "." if titles else "See events for details."

    return {
        "folder_date": folder_date,
        "pdf_file": f"{folder_date}_wednesday_folder.pdf",
        "summary": summary,
        "events": events,
        "auto_curated": True,
    }


def load_events():
    """Load existing events.json."""
    if EVENTS_FILE.exists():
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "school": "St. Cloud Elementary School",
        "mascot": "Jaguars",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "weeks": [],
    }


def save_events(data):
    """Save events.json."""
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def merge_week(events_data, new_week):
    """Add or replace a week in events_data. Keeps weeks sorted newest-first."""
    folder_date = new_week["folder_date"]
    weeks = events_data["weeks"]

    # Remove existing week with same date (if any)
    weeks = [w for w in weeks if w["folder_date"] != folder_date]

    # Insert new week
    weeks.append(new_week)

    # Sort newest first
    weeks.sort(key=lambda w: w["folder_date"], reverse=True)

    events_data["weeks"] = weeks
    events_data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    return events_data


def find_unprocessed():
    """Find data/YYYY-MM-DD.json files not yet in events.json."""
    events_data = load_events()
    existing_dates = {w["folder_date"] for w in events_data["weeks"]}

    unprocessed = []
    for f in sorted(DATA_DIR.glob("????-??-??.json")):
        date_str = f.stem
        # Validate it's a real date
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if date_str not in existing_dates:
            unprocessed.append(f)

    return unprocessed


def read_json_safe(path):
    """Read JSON file with encoding fallback."""
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Could not read {path} with any encoding")


def process_date(date_str):
    """Process a single date's raw PDF data into events."""
    raw_path = DATA_DIR / f"{date_str}.json"
    if not raw_path.exists():
        print(f"No raw data for {date_str}")
        return None

    raw_data = read_json_safe(raw_path)

    new_week = curate_from_raw(raw_data)
    print(f"  {date_str}: extracted {len(new_week['events'])} events")
    return new_week


def main():
    specific_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            specific_date = sys.argv[idx + 1]

    events_data = load_events()

    if specific_date:
        targets = [DATA_DIR / f"{specific_date}.json"]
    else:
        targets = find_unprocessed()

    if not targets:
        print("No new PDFs to curate")
        return 0

    processed = 0
    for raw_path in targets:
        date_str = raw_path.stem
        new_week = process_date(date_str)
        if new_week:
            events_data = merge_week(events_data, new_week)
            processed += 1

    if processed > 0:
        save_events(events_data)
        total_events = sum(len(w["events"]) for w in events_data["weeks"])
        print(f"Updated events.json: {len(events_data['weeks'])} weeks, {total_events} events")

    return processed


if __name__ == "__main__":
    count = main()
    print(f"Processed {count} week(s)")
