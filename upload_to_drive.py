"""
Upload SOCDS newsletter images to Google Drive.
Creates: SOCDS Images / week_NN_YYYY-MM-DD / image files
Uses a separate OAuth token (drive_token.json) so Gmail token is unaffected.
"""
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCRIPT_DIR = Path(__file__).parent.resolve()
CREDS_DIR = SCRIPT_DIR / "credentials"
CLIENT_SECRET = list(CREDS_DIR.glob("client_secret_*.json"))[0]
DRIVE_TOKEN = CREDS_DIR / "drive_token.json"
IMAGE_DIR = SCRIPT_DIR / "socds" / "images"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
ROOT_FOLDER_NAME = "SOCDS Images"


def get_drive_service():
    creds = None
    if DRIVE_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(DRIVE_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(DRIVE_TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def find_or_create_folder(service, name, parent_id=None):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = service.files().list(q=q, fields="files(id,name)", spaces="drive").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_images(service):
    root_id = find_or_create_folder(service, ROOT_FOLDER_NAME)
    print(f"Root folder: {ROOT_FOLDER_NAME} ({root_id})")

    total = 0
    for week_dir in sorted(IMAGE_DIR.iterdir()):
        if not week_dir.is_dir() or week_dir.name == "all_images":
            continue

        imgs = sorted([f for f in week_dir.iterdir() if f.is_file()])
        if not imgs:
            continue

        week_folder_id = find_or_create_folder(service, week_dir.name, root_id)

        # Check existing files in this Drive folder to skip duplicates
        existing = set()
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{week_folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(name)",
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                existing.add(f["name"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        uploaded = 0
        for img in imgs:
            if img.name in existing:
                continue
            ext = img.suffix.lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            media = MediaFileUpload(str(img), mimetype=mime)
            service.files().create(
                body={"name": img.name, "parents": [week_folder_id]},
                media_body=media,
                fields="id",
            ).execute()
            uploaded += 1
            total += 1

        skipped = len(imgs) - uploaded
        skip_msg = f" ({skipped} already existed)" if skipped else ""
        print(f"  {week_dir.name}: {uploaded} uploaded{skip_msg}")

    print(f"\nDone! {total} images uploaded to Google Drive")


if __name__ == "__main__":
    service = get_drive_service()
    upload_images(service)
