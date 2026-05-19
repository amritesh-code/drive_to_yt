import io
import os
import json
import time
import zipfile
import shutil
import glob
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials

from sheet_logger import append_video_to_sheet, build_youtube_video_url

id_folder = os.getenv("DRIVE_FOLDER_ID", "1ALmBGywBExPRIC7TGWNIXtbMasNGSWZE")
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


def download_file(file_id, destination_path):
    request = drive_service.files().get_media(fileId=file_id)
    with io.FileIO(destination_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
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
    media = MediaFileUpload(filename, chunksize=-1, resumable=True)
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
        status, response = request.next_chunk()
        if status:
            print(f"Upload {int(status.progress() * 100)}%")
    return response.get("id")


def safe_name(name):
    return "".join(c for c in name if c.isalnum() or c in " .-_()").strip()


def is_dry_run():
    return os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}


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

        if fid in tracked:
            print(f"Skipping already uploaded: {name}")
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
            title = os.path.splitext(name)[0]
            
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
            print(f"Error processing {name}: {str(e)}")

        finally:
            cleanup_temp([zip_path, extract_dir])


if __name__ == "__main__":
    main()
