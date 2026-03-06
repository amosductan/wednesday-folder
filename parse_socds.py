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
    """Parse the main announcements into titled blocks.

    Strategy: look ahead — a line is only a heading if it's short, capitalized,
    and the NEXT non-empty line is a long sentence (>60 chars). This prevents
    names, dates, and list items from being treated as headings.
    """
    if not text:
        return []

    lines = [l.strip() for l in text.split('\n')]
    # Remove trailing signature lines
    while lines and lines[-1].lower() in ('annemarie', 'ms. annemarie', ''):
        lines.pop()

    def _is_sentence(s):
        """A line that looks like prose, not a name or label."""
        return len(s) > 60 or s.endswith('.') or s.endswith('!') or s.endswith('?')

    def _next_nonblank(idx):
        """Return the next non-blank line after idx, or None."""
        for j in range(idx + 1, len(lines)):
            if lines[j]:
                return lines[j]
        return None

    def _is_heading(line, idx):
        """True if line looks like a topic heading."""
        if not line or len(line) > 50:
            return False
        if not line[0].isupper():
            return False
        if line.endswith('.') or line.endswith(',') or line.endswith('!') or line.endswith('?'):
            return False
        # Date lines are not headings
        if re.match(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)', line):
            return False
        if ' - ' in line:
            return False
        # Must be followed by a sentence-like line (not another short name/label)
        nxt = _next_nonblank(idx)
        if nxt and _is_sentence(nxt):
            return True
        return False

    blocks = []
    current_title = None
    current_body_lines = []

    for i, line in enumerate(lines):
        if not line:
            if current_body_lines:
                current_body_lines.append('')
            continue

        if _is_heading(line, i) and (current_body_lines or current_title):
            # Save previous block
            body = _join_body(current_body_lines)
            if body or current_title:
                blocks.append({"title": current_title or "", "body": body})
            current_title = line
            current_body_lines = []
        elif _is_heading(line, i) and not current_title:
            current_title = line
        else:
            current_body_lines.append(line)

    # Save last block
    body = _join_body(current_body_lines)
    if body or current_title:
        blocks.append({"title": current_title or "", "body": body})

    # Merge orphan blocks: no title + short body → prepend to next block's body
    merged = []
    for b in blocks:
        if merged and not b['title'] and len(b['body']) < 60:
            # Orphan — attach to previous block
            merged[-1]['body'] = (merged[-1]['body'] + '\n' + b['body']).strip()
        elif not merged and not b['title'] and len(b['body']) < 60:
            # First block is an orphan — will become next block's prefix
            merged.append(b)
        else:
            if merged and not merged[-1]['title'] and merged[-1]['body']:
                # Previous was an untitled orphan — make it a subtitle of this block
                b['title'] = merged[-1]['body'] + ' - ' + b['title'] if b['title'] else merged[-1]['body']
                merged[-1] = b
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
