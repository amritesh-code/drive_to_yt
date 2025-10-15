import io
import os
import json
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials

id_folder = "1Ud9kASJFMGzFi308jiFqJ5AS6oNZUwnQ"
privacy_tag = "unlisted"
file_check = "uploaded.json"
oAuth = "token.json"

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


def list_videos_in_folder(folder_id):
    query = f"'{folder_id}' in parents and (mimeType contains 'video/' or mimeType='application/octet-stream') and trashed=false"
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


def upload_to_youtube(filename, title):

    media = MediaFileUpload(filename, chunksize=-1, resumable=True)
    body = {
        "snippet": {
            "title": title,
            "description": "Auto-uploaded via Drive to YouTube script.",
            "tags": [],
            "categoryId": "22",
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


def main():
    tracked = load_tracked()
    files = list_videos_in_folder(id_folder)

    if not files:
        print("No video files found in folder.")
        return

    for f in files:
        fid = f["id"]
        name = f.get("name", f"{fid}.mp4")

        if fid in tracked:
            print(f"Skipping already uploaded: {name}")
            continue

        safe_filename = safe_name(name)
        tmp_path = os.path.join(os.getcwd(), safe_filename)

        print(f"Processing: {name}")
        try:
            download_file(fid, tmp_path)
            vid_id = upload_to_youtube(tmp_path, name)
            print(f"Uploaded video id: {vid_id}")

            tracked[fid] = {
                "name": name,
                "youtube_id": vid_id,
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_tracked(tracked)

        except Exception as e:
            print(f"Error processing {name}: {str(e)}")

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    main()