"""
Wednesday Folder Email Fetcher
Connects to Gmail API, finds the latest Wednesday Folder email,
extracts the PDF download link, downloads the PDF, and triggers processing.

Usage: python fetch_email.py [--dry-run]
"""
import os
import sys
import re
import json
import base64
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system(f"{sys.executable} -m pip install beautifulsoup4 -q")
    from bs4 import BeautifulSoup

# Gmail API scope - read-only access to email
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

SCRIPT_DIR = Path(__file__).parent.resolve()
CRED_DIR = SCRIPT_DIR / "credentials"
CRED_FILE = CRED_DIR / "gmail_credentials.json"
TOKEN_FILE = CRED_DIR / "gmail_token.json"
PDF_DIR = SCRIPT_DIR / "pdfs"
DATA_DIR = SCRIPT_DIR / "data"
STATE_FILE = DATA_DIR / "fetch_state.json"


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not CRED_FILE.exists():
                print(f"ERROR: Gmail credentials not found at {CRED_FILE}")
                print("Please download OAuth credentials from Google Cloud Console")
                print("and save to: credentials/gmail_credentials.json")
                sys.exit(1)
            print("First-time auth: opening browser for Gmail authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

    return build('gmail', 'v1', credentials=creds)


def find_wednesday_folder_emails(service, after_date=None, max_results=5):
    """Search Gmail for Wednesday Folder emails."""
    query = 'subject:"Wednesday Folder"'
    if after_date:
        query += f' after:{after_date}'

    print(f"Searching Gmail: {query}")

    all_messages = []
    page_token = None
    while True:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=100, pageToken=page_token
        ).execute()
        all_messages.extend(results.get('messages', []))
        page_token = results.get('nextPageToken')
        if not page_token or len(all_messages) >= max_results:
            break

    all_messages = all_messages[:max_results]

    if not all_messages:
        print("No Wednesday Folder emails found.")
        return []

    print(f"Found {len(all_messages)} email(s)")

    msgs = []
    for m in all_messages:
        msg = service.users().messages().get(
            userId='me', id=m['id'], format='full'
        ).execute()
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        subject = headers.get('Subject', 'Unknown')
        date_str = headers.get('Date', '')
        print(f"  - \"{subject}\" ({date_str})")
        msgs.append(msg)

    return msgs


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
        # Try direct body
        body = payload.get('body', {})
        if 'data' in body:
            html = base64.urlsafe_b64decode(body['data']).decode('utf-8')

    return html


def find_pdf_link(html):
    """Find the PDF download link from the email HTML body."""
    if not html:
        print("ERROR: No HTML body found in email")
        return None

    soup = BeautifulSoup(html, 'html.parser')

    # Look for all links
    links = soup.find_all('a', href=True)
    print(f"Found {len(links)} links in email")

    # Strategy 1: Look for links with PDF-related text or URLs
    pdf_indicators = ['pdf', 'download', 'wednesday', 'folder', 'announcement',
                      'newsletter', 'flyer', 'pta', 'peachjar', 'smore', 'docs.google',
                      'drive.google', 'view', 'open']

    candidates = []
    for link in links:
        href = link['href'].lower()
        text = link.get_text(strip=True).lower()
        combined = href + ' ' + text

        score = sum(1 for ind in pdf_indicators if ind in combined)
        if score > 0:
            candidates.append((score, link['href'], link.get_text(strip=True)))

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)

    if candidates:
        print("\nTop link candidates:")
        for score, href, text in candidates[:5]:
            label = text[:60] if text else "(no text)"
            print(f"  Score {score}: {label}")
            print(f"    URL: {href[:120]}")
        return candidates[0][1]

    # Fallback: return all links for manual inspection
    print("\nNo obvious PDF link found. All links in email:")
    for link in links:
        text = link.get_text(strip=True)[:60]
        print(f"  {text}: {link['href'][:120]}")

    return None


def download_pdf(url, folder_date):
    """Download PDF from the given URL."""
    print(f"\nDownloading from: {url[:120]}")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # Follow redirects to get the final URL
    response = session.get(url, allow_redirects=True, timeout=30)

    # Check if we got a PDF directly
    content_type = response.headers.get('Content-Type', '')

    if 'pdf' in content_type.lower() or response.content[:5] == b'%PDF-':
        pdf_data = response.content
        print(f"Direct PDF download: {len(pdf_data)} bytes")
    else:
        # SchoolMessenger Secure Document Delivery page
        # Extract message-link-code and attachment-link-code from the HTML
        page_soup = BeautifulSoup(response.text, 'html.parser')

        mlc_input = page_soup.find('input', {'id': 'message-link-code'})
        alc_input = page_soup.find('input', {'id': 'attachment-link-code'})

        if mlc_input and alc_input:
            mlc = mlc_input.get('value', '')
            alc = alc_input.get('value', '')
            print(f"SchoolMessenger SDD detected (mlc={mlc[:12]}...)")

            # Get base URL from the final redirect
            from urllib.parse import urljoin
            base_url = response.url.rsplit('/', 1)[0] + '/'
            download_url = urljoin(base_url, 'requestdocument.php')

            print(f"Downloading via SDD API: {download_url}")
            r2 = session.post(download_url, data={'s': mlc, 'mal': alc}, timeout=60)

            if r2.status_code == 200 and (
                'pdf' in r2.headers.get('Content-Type', '').lower()
                or r2.content[:5] == b'%PDF-'
            ):
                pdf_data = r2.content
                print(f"SDD download success: {len(pdf_data):,} bytes")
            else:
                print(f"SDD download failed: HTTP {r2.status_code}, "
                      f"Content-Type: {r2.headers.get('Content-Type', '?')}")
                debug_path = DATA_DIR / f"{folder_date}_debug_page.html"
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"Page saved to {debug_path} for inspection.")
                return None
        else:
            # Fallback: look for direct PDF links on page
            pdf_url = None
            for a in page_soup.find_all('a', href=True):
                if '.pdf' in a['href'].lower():
                    pdf_url = a['href']
                    break
            for iframe in page_soup.find_all('iframe', src=True):
                if '.pdf' in iframe['src'].lower():
                    pdf_url = iframe['src']
                    break

            if pdf_url:
                from urllib.parse import urljoin
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(url, pdf_url)
                print(f"Found PDF link: {pdf_url[:120]}")
                r2 = session.get(pdf_url, timeout=30)
                pdf_data = r2.content
            else:
                debug_path = DATA_DIR / f"{folder_date}_debug_page.html"
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"Could not find PDF link. Page saved to {debug_path}")
                return None

    # Save PDF
    pdf_path = PDF_DIR / f"{folder_date}_wednesday_folder.pdf"
    with open(pdf_path, 'wb') as f:
        f.write(pdf_data)
    print(f"Saved PDF: {pdf_path} ({len(pdf_data):,} bytes)")
    return str(pdf_path)


def get_folder_date_from_email(msg):
    """Extract the date from email headers."""
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    date_str = headers.get('Date', '')

    # Parse email date
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def load_state():
    """Load the fetch state to track which emails we've processed."""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_processed_date": None, "processed_ids": []}


def save_state(state):
    """Save the fetch state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def process_single_email(msg, service, dry_run=False):
    """Process a single Wednesday Folder email: extract link, download PDF."""
    msg_id = msg['id']
    folder_date = get_folder_date_from_email(msg)
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    subject = headers.get('Subject', 'Unknown')

    print(f"\n{'-' * 50}")
    print(f"Processing: \"{subject}\" (date: {folder_date})")

    # Check if we already have this PDF
    existing_pdf = PDF_DIR / f"{folder_date}_wednesday_folder.pdf"
    if existing_pdf.exists():
        print(f"  SKIP: PDF already exists")
        return None

    # Extract HTML body and find link
    html = extract_body_html(msg)
    if not html:
        print("  ERROR: Could not extract email body")
        return None

    link = find_pdf_link(html)
    if not link:
        print("  ERROR: Could not find download link in email")
        return None

    if dry_run:
        print(f"  [DRY RUN] Would download from: {link[:80]}")
        return None

    # Download PDF
    import time
    pdf_path = download_pdf(link, folder_date)
    time.sleep(1)  # Rate limit between downloads
    return pdf_path


def main():
    dry_run = '--dry-run' in sys.argv
    backfill = '--backfill' in sys.argv

    print("=" * 60)
    print("Wednesday Folder Email Fetcher")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if backfill:
        print("Mode: BACKFILL (downloading all past emails)")
    print("=" * 60)

    # Connect to Gmail
    service = get_gmail_service()

    if backfill:
        # Backfill mode: get all Wednesday Folder emails since Sept 2025
        after_date = '2025/09/01'
        msgs = find_wednesday_folder_emails(service, after_date=after_date, max_results=200)
        if not msgs:
            print("\nNo emails found.")
            return

        downloaded = []
        skipped = []
        failed = []
        for msg in reversed(msgs):  # Process oldest first
            pdf_path = process_single_email(msg, service, dry_run)
            folder_date = get_folder_date_from_email(msg)
            if pdf_path:
                downloaded.append(folder_date)
            elif (PDF_DIR / f"{folder_date}_wednesday_folder.pdf").exists():
                skipped.append(folder_date)
            else:
                failed.append(folder_date)

        print(f"\n{'=' * 50}")
        print(f"BACKFILL COMPLETE")
        print(f"  Downloaded: {len(downloaded)}")
        print(f"  Skipped (already had): {len(skipped)}")
        print(f"  Failed: {len(failed)}")
        if downloaded:
            print(f"  New PDFs: {', '.join(downloaded)}")
        if failed:
            print(f"  Failed dates: {', '.join(failed)}")

    else:
        # Normal mode: get latest email only
        state = load_state()
        if state["last_processed_date"]:
            print(f"Last processed: {state['last_processed_date']}")

        after_date = None
        if state["last_processed_date"]:
            after = datetime.strptime(state["last_processed_date"], '%Y-%m-%d') - timedelta(days=1)
            after_date = after.strftime('%Y/%m/%d')

        msgs = find_wednesday_folder_emails(service, after_date, max_results=1)
        if not msgs:
            print("\nNo new Wednesday Folder emails to process.")
            return

        msg = msgs[0]
        msg_id = msg['id']
        if msg_id in state.get("processed_ids", []):
            print("\nThis email was already processed. Nothing new.")
            return

        pdf_path = process_single_email(msg, service, dry_run)
        if not pdf_path:
            return

        # Update state
        folder_date = get_folder_date_from_email(msg)
        state["last_processed_date"] = folder_date
        if "processed_ids" not in state:
            state["processed_ids"] = []
        state["processed_ids"].append(msg_id)
        state["processed_ids"] = state["processed_ids"][-20:]
        save_state(state)

        print(f"\nPDF downloaded and saved successfully!")
        print(f"  python process_pdf.py \"{pdf_path}\" --date {folder_date}")


if __name__ == "__main__":
    main()
