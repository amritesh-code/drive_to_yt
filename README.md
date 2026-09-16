# Drive to YouTube Uploader

## Overview

This automation uploads videos from a designated Google Drive folder directly to a connected YouTube channel using Google APIs.
Each archive is downloaded, the largest video inside it is extracted and uploaded with a title derived from the archive filename, then the title and watch URL are appended to a Google Sheet.
The system can run manually or on a schedule through GitHub Actions.

## Features

* Scans a specific Google Drive folder for new `.zip` / `.rar` archives.
* Extracts each archive and uploads the largest video found inside.
* Titles come from the archive filename, trimmed to YouTube's 100-character
  limit (the full name goes in the description when it has to be trimmed).
* Skips previously uploaded files, matching on Drive file ID then on title.
* Logs each upload to a Google Sheet.
* Stops cleanly when the daily YouTube upload quota is hit and resumes next run.
* Uses OAuth2 credentials stored securely in repository secrets.
* Can be triggered manually or on a recurring schedule via GitHub Actions.

## File Structure

```
drive_to_youtube/
│
├── main.py                 # Core upload pipeline
├── sheet_logger.py         # Google Sheets logging helper
├── authorize.py            # Google OAuth authorization
├── uploaded.json           # Record of what has already been uploaded
├── requirements.txt        # Dependencies
├── .github/
│   └── workflows/
│       └── upload.yml      # GitHub Actions automation
└── README.md               # Documentation
```

## Setup

### 1. Google Cloud Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable:
   * YouTube Data API v3
   * Google Drive API
3. Enable the Google Sheets API.
4. Create **OAuth 2.0 Client ID (Desktop)** credentials.
5. Download the JSON file and store it as `client_secret.json`.

### 2. Configuration

Everything is read from environment variables, each with a default in `main.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DRIVE_FOLDER_ID` | hardcoded folder | Drive folder to scan |
| `GOOGLE_SHEET_ID` | hardcoded sheet | Spreadsheet to log into |
| `GOOGLE_TOKEN_FILE` | `token.json` | OAuth token path |
| `YOUTUBE_PRIVACY` | `unlisted` | `public`, `private` or `unlisted` |
| `TEMP_EXTRACT_DIR` | `temp_extract` | Scratch directory for extraction |
| `UNRAR_TOOL` | auto-detect | Explicit path to `unrar`/`unar` (handy on Windows) |
| `DRY_RUN` | unset | Set to `1` to list what would be uploaded without uploading |


## Repository Secrets (for GitHub Actions)

| Secret Name             | Description                       |
| ----------------------- | --------------------------------- |
| `CLIENT_SECRET_JSON`    | Contents of `client_secret.json`  |
| `TOKEN_JSON`            | Contents of `token.json`          |
| `DRIVE_FOLDER_ID`       | ID of the Drive folder to monitor |
| `YOUTUBE_CLIENT_ID`     | OAuth client ID                   |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret               |

## How to run

### Run locally

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1; python -m pip install --upgrade pip; pip install -r requirements.txt
```

2. Place `client_secret.json` in the project root and run the OAuth flow once:

```powershell
python authorize.py
```

3. Run the uploader:

```powershell
python main.py
```

### Run via GitHub Actions

1. Add the required repository secrets (`CLIENT_SECRET_JSON`, `TOKEN_JSON`, `DRIVE_FOLDER_ID`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`).
2. Trigger the workflow manually from the Actions tab or wait for the scheduled run.

## How It Works

1. Authenticates with Google APIs using the stored credentials.
2. Lists every `.zip` / `.rar` archive in the configured Drive folder.
3. Downloads and extracts each one, picking the largest video file inside.
4. Uploads it to YouTube with the title derived from the archive filename.
5. Records the result in `uploaded.json` and appends a row to the Google Sheet.
6. Removes the downloaded archive and extracted files.

## Output

Each uploaded video appears in your YouTube Studio under the configured channel.
Every run ends with a summary of how many files were uploaded, skipped and
failed, listing each failure by name and reason.

## Notes

* For first time authorization, run `authorize.py` locally once to generate a valid `token.json`.
* Extracting `.rar` archives needs `unrar`, `unar`, `bsdtar` or `7z` on PATH.
  The GitHub Actions workflow installs `unar` for this.
* Keep both `client_secret.json` and `token.json` in repository secrets only.

---


