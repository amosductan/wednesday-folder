"""
SOCDS Newsletter Email Fetcher
Fetches Isaac's PreK Orange weekly updates from Gmail.
Saves email HTML and extracted text.

Usage: python fetch_socds.py [--backfill]
"""
import sys
import os
import json
import base64
import re
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system(f"{sys.executable} -m pip install beautifulsoup4 -q")
    from bs4 import BeautifulSoup

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
SCRIPT_DIR = Path(__file__).parent.resolve()
CRED_DIR = SCRIPT_DIR / "credentials"
TOKEN_FILE = CRED_DIR / "gmail_token.json"
CRED_FILE = CRED_DIR / "gmail_credentials.json"
SOCDS_DIR = SCRIPT_DIR / "socds"
SOCDS_HTML_DIR = SOCDS_DIR / "emails"
SOCDS_DATA_DIR = SOCDS_DIR / "data"


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CRED_FILE.exists():
                print(f"ERROR: Gmail credentials not found at {CRED_FILE}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)


def extract_body_html(msg):
    """Extract HTML body from Gmail message."""
    payload = msg['payload']

    def find_html_part(part):
        if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
            return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        for sub in part.get('parts', []):
            result = find_html_part(sub)
            if result:
                return result
        return None

    html = find_html_part(payload)
    if not html:
        body = payload.get('body', {})
        if 'data' in body:
            html = base64.urlsafe_b64decode(body['data']).decode('utf-8')
    return html


def extract_text_sections(html):
    """Extract structured text from SOCDS newsletter HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)

    # Extract links
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        label = a.get_text(strip=True)
        if label and href and 'unsubscribe' not in href.lower() and 'mailto:' not in href.lower():
            links.append({"label": label, "url": href})

    return {
        "text": text,
        "links": links
    }


def get_week_number(subject):
    """Extract week number from subject line."""
    match = re.search(r'Week\s*#(\d+)', subject)
    return int(match.group(1)) if match else None


def get_email_date(msg):
    """Get date from email headers."""
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    try:
        dt = parsedate_to_datetime(headers.get('Date', ''))
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def process_email(msg, dry_run=False):
    """Process a single SOCDS email."""
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    subject = headers.get('Subject', 'Unknown')
    email_date = get_email_date(msg)
    week_num = get_week_number(subject)

    print(f"  Processing: Week #{week_num} ({email_date}) - {subject[:60]}")

    # Check if already saved
    json_path = SOCDS_DATA_DIR / f"week_{week_num:02d}.json"
    if json_path.exists():
        print(f"    SKIP: Already processed")
        return "skipped"

    if dry_run:
        print(f"    [DRY RUN]")
        return "dry_run"

    html = extract_body_html(msg)
    if not html:
        print(f"    ERROR: No HTML body")
        return "failed"

    # Save raw HTML
    html_path = SOCDS_HTML_DIR / f"week_{week_num:02d}_{email_date}.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Extract and save structured data
    content = extract_text_sections(html)
    data = {
        "week_number": week_num,
        "subject": subject,
        "date": email_date,
        "text": content["text"],
        "links": content["links"]
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"    Saved: {json_path.name} + {html_path.name}")
    return "downloaded"


def main():
    backfill = '--backfill' in sys.argv
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("SOCDS Newsletter Fetcher")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if backfill:
        print("Mode: BACKFILL")
    print("=" * 60)

    # Create directories
    SOCDS_HTML_DIR.mkdir(parents=True, exist_ok=True)
    SOCDS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    service = get_gmail_service()

    # Search for SOCDS emails
    query = 'subject:"SOCDS 2025/26 Update"'
    max_results = 100 if backfill else 3

    all_msgs = []
    page_token = None
    while True:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=100, pageToken=page_token
        ).execute()
        all_msgs.extend(results.get('messages', []))
        page_token = results.get('nextPageToken')
        if not page_token or len(all_msgs) >= max_results:
            break

    all_msgs = all_msgs[:max_results]
    print(f"Found {len(all_msgs)} email(s)")

    # Fetch full messages
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    for m in reversed(all_msgs):  # Oldest first
        msg = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
        result = process_email(msg, dry_run)
        if result in stats:
            stats[result] += 1

    print(f"\n{'=' * 50}")
    print(f"COMPLETE: {stats['downloaded']} downloaded, {stats['skipped']} skipped, {stats['failed']} failed")


if __name__ == "__main__":
    main()
