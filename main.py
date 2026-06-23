import io
import os
import json
import time
import zipfile
import shutil
import glob
import ssl
import http.client
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials

from sheet_logger import append_video_to_sheet, build_youtube_video_url

id_folder = os.getenv("DRIVE_FOLDER_ID", "1G_wFFQW7N33-nGRJLUH8198NLwU8XYIx")
privacy_tag = os.getenv("YOUTUBE_PRIVACY", "unlisted")
file_check = "uploaded.json"
oAuth = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
temp_dir = os.getenv("TEMP_EXTRACT_DIR", "temp_extract")
spreadsheet_id = os.getenv(
    "GOOGLE_SHEET_ID", "1arGs7WTgCAfxPqWEiqHwEQQituhAxkY8rSu3QsNhcyM"
)

creds = Credentials.from_authorized_user_file(oAuth, scopes=None)
drive_service = build("drive", "v3", credentials=creds)
youtube_service = build("youtube", "v3", credentials=creds)


def load_tracked():
    if not os.path.exists(file_check):
        return {}
    try:
        with open(file_check, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_tracked(d):
    with open(file_check, "w") as f:
        json.dump(d, f, indent=2)


def list_zip_files_in_folder(folder_id):
    query = f"'{folder_id}' in parents and (mimeType='application/zip' or mimeType='application/x-zip-compressed' or name contains '.zip') and trashed=false"
    files, page_token = [], None
    while True:
        resp = (
            drive_service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


# Transient failures (dropped connections, 5xx) that are safe to retry.
RETRIABLE_EXCEPTIONS = (OSError, ssl.SSLError, http.client.HTTPException)
RETRIABLE_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 5


def next_chunk_with_retry(request, label):
    retry = 0
    while True:
        try:
            return request.next_chunk()
        except HttpError as e:
            if getattr(e, "resp", None) is None or e.resp.status not in RETRIABLE_STATUS:
                raise
        except RETRIABLE_EXCEPTIONS:
            pass
        retry += 1
        if retry > MAX_RETRIES:
            raise
        wait = min(2 ** retry, 60)
        print(f"{label}: transient error, retrying in {wait}s ({retry}/{MAX_RETRIES})")
        time.sleep(wait)


def download_file(file_id, destination_path):
    request = drive_service.files().get_media(fileId=file_id)
    with io.FileIO(destination_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = next_chunk_with_retry(downloader, "Download")
            if status:
                print(f"Download {int(status.progress() * 100)}%")


def extract_zip(zip_path, extract_to):
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    return extract_to


def find_video_in_extracted(extract_dir):
    video_patterns = [
        os.path.join(extract_dir, "**", "video*.mp4"),
        os.path.join(extract_dir, "**", "*.mp4"),
        os.path.join(extract_dir, "**", "*.mkv"),
        os.path.join(extract_dir, "**", "*.avi"),
        os.path.join(extract_dir, "**", "*.mov"),
    ]
    
    for pattern in video_patterns:
        videos = glob.glob(pattern, recursive=True)
        if videos:
            return max(videos, key=os.path.getsize)
    
    return None


def upload_to_youtube(filename, title):
    media = MediaFileUpload(filename, chunksize=50 * 1024 * 1024, resumable=True)
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "tags": [],
            "categoryId": "28",
        },
        "status": {"privacyStatus": privacy_tag},
    }

    request = youtube_service.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response = None
    while response is None:
        status, response = next_chunk_with_retry(request, "Upload")
        if status:
            print(f"Upload {int(status.progress() * 100)}%")
    return response.get("id")


def safe_name(name):
    return "".join(c for c in name if c.isalnum() or c in " .-_()").strip()


KNOWN_EXTENSIONS = (".zip", ".mp4", ".mkv", ".avi", ".mov")


def normalize_title(name):
    text = (name or "").strip()
    stripped = True
    while stripped:
        stripped = False
        lowered = text.lower()
        for ext in KNOWN_EXTENSIONS:
            if lowered.endswith(ext):
                text = text[: -len(ext)]
                stripped = True
                break
    return text.strip().lower()


def find_tracked_entry(tracked, file_id, title):
    if file_id in tracked:
        return file_id, tracked[file_id], "file id"

    normalized_title = normalize_title(title)
    for tracked_id, entry in tracked.items():
        entry_name = entry.get("title") or entry.get("name", "")
        if normalize_title(entry_name) == normalized_title:
            return tracked_id, entry, "title"

    return None, None, None


def is_dry_run():
    return os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}


# YouTube returns these reasons when the daily upload quota / limit is hit.
# When that happens there is no point trying the remaining videos today, so we
# stop cleanly (exit 0) and let the next scheduled run pick up where we left off.
QUOTA_REASONS = {
    "quotaexceeded",
    "dailylimitexceeded",
    "uploadlimitexceeded",
    "ratelimitexceeded",
    "userratelimitexceeded",
}


def is_quota_error(error):
    if not isinstance(error, HttpError):
        return False
    if getattr(error, "resp", None) is not None and error.resp.status == 403:
        text = (getattr(error, "content", b"") or b"").decode("utf-8", "ignore").lower()
        if any(reason in text for reason in QUOTA_REASONS):
            return True
    return False


def cleanup_temp(paths):
    for path in paths:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isfile(path):
                os.remove(path)
        except Exception as e:
            print(f"Warning: Could not remove {path}: {e}")


def main():
    tracked = load_tracked()
    files = list_zip_files_in_folder(id_folder)
    dry_run = is_dry_run()

    if not files:
        print("No zip files found in folder.")
        return

    for f in files:
        fid = f["id"]
        name = f.get("name", f"{fid}.zip")
        title = os.path.splitext(name)[0]

        tracked_id, tracked_entry, match_reason = find_tracked_entry(tracked, fid, title)
        if tracked_entry:
            print(
                f"Skipping already uploaded ({match_reason} match: {tracked_id}): {name}"
            )
            continue

        safe_filename = safe_name(name)
        zip_path = os.path.join(os.getcwd(), safe_filename)
        extract_dir = os.path.join(os.getcwd(), temp_dir, fid)

        print(f"Processing zip: {name}")
        try:
            print("Downloading zip file...")
            download_file(fid, zip_path)

            print("Extracting zip file...")
            extract_zip(zip_path, extract_dir)
            
            video_path = find_video_in_extracted(extract_dir)
            if not video_path:
                print(f"No video file found in zip: {name}")
                continue
            
            video_name = os.path.basename(video_path)
            
            print(f"Found video: {video_name}")
            if dry_run:
                print(f"Dry run: would upload to YouTube as: {title}")
                print("Dry run: would append title and video link to Google Sheets.")
                continue

            print(f"Uploading to YouTube as: {title}")
            
            vid_id = upload_to_youtube(video_path, title)
            print(f"Uploaded video id: {vid_id}")
            video_url = build_youtube_video_url(vid_id)

            tracked[fid] = {
                "name": name,
                "title": title,
                "video_file": video_name,
                "youtube_id": vid_id,
                "video_url": video_url,
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "sheet_logged": False,
            }
            save_tracked(tracked)

            try:
                append_video_to_sheet(title, video_url, spreadsheet_id=spreadsheet_id)
                tracked[fid]["sheet_logged"] = True
                save_tracked(tracked)
                print("Logged upload to Google Sheet.")
            except Exception as sheet_error:
                print(
                    "Warning: uploaded to YouTube but failed to log to Google Sheet: "
                    f"{sheet_error}"
                )

        except Exception as e:
            if is_quota_error(e):
                print(
                    "YouTube daily upload quota reached. Stopping for today; "
                    "remaining videos will be picked up on the next run."
                )
                break
            print(f"Error processing {name}: {str(e)}")

        finally:
            cleanup_temp([zip_path, extract_dir])


if __name__ == "__main__":
    main()
