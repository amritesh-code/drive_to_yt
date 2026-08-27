from __future__ import annotations

import os
from typing import Any, Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


default_spreadsheet_id = "1arGs7WTgCAfxPqWEiqHwEQQituhAxkY8rSu3QsNhcyM"
default_token_file = "token.json"


def build_youtube_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def get_sheets_service(token_file: Optional[str] = None) -> Any:
    creds = Credentials.from_authorized_user_file(
        token_file or os.getenv("GOOGLE_TOKEN_FILE", default_token_file), scopes=None
    )
    return build("sheets", "v4", credentials=creds)


def get_first_sheet_title(service: Any, spreadsheet_id: str) -> str:
    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()
    sheets = response.get("sheets", [])
    if not sheets:
        raise ValueError("Spreadsheet has no tabs available for logging.")
    return sheets[0]["properties"]["title"]


def append_video_to_sheet(
    video_title: str,
    video_url: str,
    spreadsheet_id: Optional[str] = None,
    token_file: Optional[str] = None,
) -> None:
    target_spreadsheet_id = spreadsheet_id or os.getenv(
        "GOOGLE_SHEET_ID", default_spreadsheet_id
    )
    service = get_sheets_service(token_file=token_file)
    sheet_title = get_first_sheet_title(service, target_spreadsheet_id)
    body = {"values": [[video_title, video_url]]}

    service.spreadsheets().values().append(
        spreadsheetId=target_spreadsheet_id,
        range=f"{sheet_title}!A:B",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()