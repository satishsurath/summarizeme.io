#!/usr/bin/env python3
"""
fix_dates.py

Traverse all transcript JSON files under data/channels/
and retroactively fix 'upload_date' == "UnknownDate" by
retrieving from yt-dlp or pytube.

Usage:
  python fix_dates.py [--base-dir data/channels]

Note:
  - This script attempts to fix each JSON in place.
  - You can choose either approach for retrieving the date: 
    1) yt-dlp
    2) pytube 
  - If both fail, we leave "UnknownDate" untouched, 
    and optionally log an error.
"""

import os
import json
#import argparse
import subprocess
from pytube import YouTube
from datetime import datetime


base_dir = os.getenv("DATA_DIR")
if base_dir is None:
    base_dir = "data/channels"  # Base directory for channel data

def get_upload_date_yt_dlp(video_id: str) -> str:
    """
    Attempt to get the upload date string (YYYYMMDD) from yt-dlp.
    If successful, return 'YYYY-MM-DD'. Otherwise return None.
    """
    cmd = ["yt-dlp", "--dump-single-json", f"https://www.youtube.com/watch?v={video_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        info = json.loads(result.stdout)
        raw_date = info.get("upload_date")  # e.g. "20200131"
        if raw_date:
            # Reformat to "YYYY-MM-DD"
            return f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    except Exception:
        pass
    return None

def get_upload_date_pytube(video_id: str) -> str:
    """
    Attempt to get the upload date from pytube.
    If successful, return 'YYYY-MM-DD'. Otherwise return None.
    """
    try:
        yt_obj = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        if yt_obj.publish_date:
            dt = yt_obj.publish_date  # datetime object
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def fix_upload_dates():
    """
    Traverse all channels under base_dir and fix UnknownDate by
    trying yt-dlp, then pytube. If found, rewrite the JSON file.
    """
    # Example: data/channels/<channel_id>/transcripts/<video_id>.json
    # Loop over each channel directory
    if not os.path.exists(base_dir):
        print(f"Base directory '{base_dir}' does not exist.")
        return

    channels = [
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d)) and not d.startswith(".")
    ]
    print(f"Found {len(channels)} channel directories.")

    for channel_id in channels:
        transcripts_path = os.path.join(base_dir, channel_id, "transcripts")
        if not os.path.exists(transcripts_path):
            continue

        files = os.listdir(transcripts_path)
        json_files = [f for f in files if f.endswith(".json")]
        print(f"Channel '{channel_id}' has {len(json_files)} transcript JSON files.")

        for jf in json_files:
            full_path = os.path.join(transcripts_path, jf)
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            vid_id = data.get("video_id")
            old_date = data.get("upload_date", "UnknownDate")

            if old_date == "UnknownDate" and vid_id:
                print(f"  --> Fixing {vid_id} in channel '{channel_id}'")
                # Attempt yt-dlp
                new_date = get_upload_date_yt_dlp(vid_id)

                # Fallback to pytube if yt-dlp didn't work
                if not new_date:
                    new_date = get_upload_date_pytube(vid_id)

                if new_date:
                    data["upload_date"] = new_date
                    # Write back to file
                    with open(full_path, "w", encoding="utf-8") as fw:
                        json.dump(data, fw, ensure_ascii=False, indent=2)
                    print(f"     Updated date -> {new_date}")
                else:
                    print("     Could not find a valid upload date.")


if __name__ == "__main__":
    #parser = argparse.ArgumentParser(description="Retroactively fix JSON files with UnknownDate.")
    # parser.add_argument("--base-dir", default="data/channels", help="Base directory of channels.")
    #args = parser.parse_args()
    fix_upload_dates()