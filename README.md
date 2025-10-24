# Drive to YouTube Uploader

## Overview

This automation uploads videos from a designated Google Drive folder directly to a connected YouTube channel using Google APIs.
Each video file is automatically detected, uploaded with metadata (title, description, and privacy setting), and optionally logged for tracking.
The system can run manually or on a schedule through GitHub Actions.

## Features

* Scans a specific Google Drive folder for new video files.
* Uploads each file to YouTube automatically.
* Supports metadata (title, description, tags, visibility).
* Skips previously uploaded files to prevent duplication.
* Uses OAuth2 credentials stored securely in repository secrets.
* Can be triggered manually or on a recurring schedule via GitHub Actions.

## File Structure

```
drive_to_youtube/
│
├── main.py                 # Core upload script
├── authorize.py            # Google OAuth authorization
├── requirements.txt        # Dependencies
├── .env                    # Environment variables (created at runtime)
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
3. Create **OAuth 2.0 Client ID (Desktop)** credentials.
4. Download the JSON file and store it as `client_secret.json`.


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
2. Lists all video files in the specified Drive folder.
3. Uploads each file to YouTube with metadata derived from filename or `.csv` mapping.
4. Marks successfully uploaded files to skip in subsequent runs.

## Output

Each uploaded video appears in your YouTube Studio under the configured channel.
Logs show which files were uploaded, skipped, or errored.

## Notes

* For first time authorization, run `main.py` locally once to generate a valid `token.json`.
* Keep both `client_secret.json` and `token.json` in repository secrets only.

---


