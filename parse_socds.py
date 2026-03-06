"""
Parse SOCDS newsletter text into structured sections.
Processes all week_NN.json files and outputs socds_events.json for the website.
"""
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SOCDS_DATA_DIR = SCRIPT_DIR / "socds" / "data"

# Section headers that appear consistently in newsletters
SECTION_PATTERNS = [
    (r'Art with Ms\.?\s*Jenny', 'art'),
    (r'Gardening with Ms\.?\s*Linda', 'gardening'),
    (r'^Upcoming\s*$', 'upcoming'),
    (r'^Logistics\s*$', 'logistics'),
]

# Lines that signal footer content to strip
FOOTER_MARKERS = [
    'South Orange Country Day School\n461',
    'You are receiving this email',
]

# Non-event link labels in the Upcoming section
SKIP_UPCOMING = [
    'Class Directory', 'School Calendar', 'SimplyGourmet',
    '@SOCDSMOMENTS', 'Updated School Calendar', 'SOCDS Summer Camp',
]


def parse_newsletter(raw_text, raw_links):
    """Parse raw newsletter text into structured sections."""
    text = raw_text.strip()

    # Strip footer
    for marker in FOOTER_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()

    # Strip "Email Ms. Annemarie" header
    text = re.sub(r'^Email Ms\.?\s*Annemarie\s*\n*', '', text).strip()

    # Split text into major sections by known headers
    parts = _split_by_sections(text)

    # Build structured output
    sections = {
        "announcements": _clean_announcements(parts.get('main', '')),
        "art": _clean_paragraph(parts.get('art', '')),
        "gardening": _clean_paragraph(parts.get('gardening', '')),
        "upcoming": _parse_upcoming(parts.get('upcoming', '')),
        "logistics": _clean_paragraph(parts.get('logistics', '')),
    }

    # Filter links
    filtered_links = [
        l for l in raw_links
        if 'unsubscribe' not in l.get('url', '').lower()
        and 'Email Ms' not in l.get('label', '')
    ]

    return sections, filtered_links


def _split_by_sections(text):
    """Split newsletter text by known section headers."""
    lines = text.split('\n')
    parts = {}
    current_key = 'main'
    current_lines = []

    for line in lines:
        stripped = line.strip()
        matched = False
        for pattern, key in SECTION_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                parts[current_key] = '\n'.join(current_lines).strip()
                current_key = key
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)

    parts[current_key] = '\n'.join(current_lines).strip()
    return parts


def _clean_paragraph(text):
    """Clean up paragraph text — collapse excessive whitespace."""
    if not text:
        return None
    # Remove leading/trailing blanks per line, collapse multiple blank lines
    lines = [l.strip() for l in text.split('\n')]
    result = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                result.append('')
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    return '\n'.join(result).strip() or None


def _clean_announcements(text):
    """Parse the main announcements into titled blocks using bold/heading detection."""
    if not text:
        return []

    lines = text.split('\n')
    blocks = []
    current_title = None
    current_body_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_body_lines:
                current_body_lines.append('')
            continue

        # Heuristic for headings: short, no ending punctuation, standalone
        looks_like_heading = (
            len(stripped) < 55
            and not stripped.endswith('.')
            and not stripped.endswith(',')
            and not stripped.endswith(':')
            and not stripped.startswith('If you')
            and not stripped.startswith('Please')
            and not stripped.startswith('We ')
            and not stripped.startswith('I ')
            and not stripped.startswith('In ')
            and not stripped.startswith('A ')
            and not stripped.startswith('To ')
            and not stripped.startswith('On ')
            and not stripped.startswith('For ')
            and not stripped.startswith('The ')
            and not stripped.startswith('Our ')
            and not stripped.startswith('(')
            and not stripped.startswith('"')
            and stripped[0].isupper()
        )

        if looks_like_heading and current_body_lines:
            # Save previous block
            body = _join_body(current_body_lines)
            if body or current_title:
                blocks.append({"title": current_title or "", "body": body})
            current_title = stripped
            current_body_lines = []
        elif looks_like_heading and not current_title:
            current_title = stripped
        else:
            current_body_lines.append(stripped)

    # Save last block
    body = _join_body(current_body_lines)
    if body or current_title:
        blocks.append({"title": current_title or "", "body": body})

    # Merge tiny orphan blocks (body < 30 chars) into previous block
    merged = []
    for b in blocks:
        if merged and len(b['body']) < 30 and not b['title']:
            merged[-1]['body'] += ' ' + b['body']
        elif merged and not b['body'] and b['title'] and len(b['title']) < 20:
            # Orphan title with no body — append as subtitle to previous
            merged[-1]['body'] += ' ' + b['title']
        else:
            merged.append(b)

    return merged


def _join_body(lines):
    """Join body lines, collapsing blanks into paragraph breaks."""
    text = '\n'.join(lines).strip()
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _parse_upcoming(text):
    """Parse upcoming section into event items."""
    if not text:
        return []

    events = []
    for line in text.split('\n'):
        line = line.strip()
        if not line or len(line) < 5:
            continue
        if any(s in line for s in SKIP_UPCOMING):
            continue
        events.append(line)
    return events


def build_socds_events():
    """Build the structured SOCDS events JSON for the website."""
    weeks = []

    for f in sorted(SOCDS_DATA_DIR.glob("week_*.json"), reverse=True):
        with open(f, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)

        sections, links = parse_newsletter(raw['text'], raw.get('links', []))

        week_data = {
            "week_number": raw['week_number'],
            "date": raw['date'],
            "subject": raw['subject'],
            "sections": sections,
            "links": links
        }
        weeks.append(week_data)

    output = {
        "school": "South Orange Country Day School",
        "class": "PreK Orange",
        "teacher": "Ms. Annemarie",
        "last_updated": weeks[0]["date"] if weeks else "",
        "weeks": weeks
    }

    output_path = SCRIPT_DIR / "socds" / "socds_events.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Built socds_events.json: {len(weeks)} weeks")
    return output_path


if __name__ == "__main__":
    build_socds_events()
