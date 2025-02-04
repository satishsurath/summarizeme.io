# youtube_utils.py
import os
import json
import logging
import subprocess
from datetime import datetime

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from pytube import YouTube

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Video, VideoFolder

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
#engine = create_engine(DB_URL)
engine = create_engine(
    DB_URL, 
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800)  # 30 minutes
SessionLocal = sessionmaker(bind=engine)

def download_channel_transcripts(channel_url, status_dict):
    """
    Download transcripts for all videos in a channel/playlist.

    Improved:
    - Skip downloading transcripts if they are already in the DB
    - Report skipped videos as processed in the status_dict
    """
    # Create tables if they don't exist (or use migrations in production)
    Base.metadata.create_all(engine)

    # Get the immutable channel/playlist id and video list from YouTube
    channel_id, videos = get_channel_and_videos(channel_url)
    total_videos = len(videos)
    status_dict["total"] = total_videos
    status_dict.setdefault("processed", 0)
    status_dict.setdefault("errors", [])
    # Optionally track how many videos were skipped or newly downloaded
    status_dict.setdefault("already_downloaded", 0)
    status_dict.setdefault("newly_downloaded", 0)

    session = SessionLocal()
    try:
        # Check if there is already a folder association for this playlist id.
        existing_folder = session.query(VideoFolder).filter_by(original_playlist_id=channel_id).first()

        if existing_folder:
            # Use the existing (human-friendly) folder name.
            human_playlist_name = existing_folder.folder_name
        else:
            # If no folder exists yet, use the playlist id as the name.
            human_playlist_name = channel_id

        processed_count = 0
        for video_meta in videos:
            video_id = video_meta["video_id"]
            title = video_meta["title"]
            upload_date = video_meta["upload_date"]

            # 1) Check if this video is already in DB with a transcript
            existing_video = (
                session.query(Video)
                .filter_by(video_id=video_id)
                .first()
            )
            if (existing_video
                and existing_video.transcript_no_ts
                and existing_video.transcript_no_ts.strip() != ""):
                # Already have a transcript => skip re-downloading
                logger.info(f"Skipping transcript download for {video_id} (already in DB).")
                status_dict["already_downloaded"] += 1

                # Ensure folder association
                ensure_folder_association(
                    session,
                    video_id,
                    channel_id,
                    human_playlist_name
                )
                
                processed_count += 1
                status_dict["processed"] = processed_count
                continue

            # Fix unknown upload date if possible
            if upload_date == "UnknownDate":
                real_date = get_upload_date_for_video(video_id)
                if real_date:
                    upload_date = real_date
                    video_meta["upload_date"] = real_date

            # 2) Download transcript only if missing
            try:
                transcripts = get_transcript_for_video(video_id)
            except Exception as e:
                msg = f"Failed to get transcript for {video_id}: {e}"
                logger.error(msg)
                status_dict["errors"].append(msg)
                processed_count += 1
                status_dict["processed"] = processed_count
                continue

            # 3) Build transcript variants
            transcript_with_ts, transcript_no_ts = build_transcript_variants(transcripts)

            # 4) Upsert the Video row
            if not existing_video:
                video_obj = Video(
                    video_id=video_id,
                    title=title,
                    upload_date=upload_date,
                    transcript_with_ts=transcript_with_ts,
                    transcript_no_ts=transcript_no_ts
                )
                session.add(video_obj)
                session.commit()
            else:
                existing_video.title = title
                existing_video.upload_date = upload_date
                existing_video.transcript_with_ts = transcript_with_ts
                existing_video.transcript_no_ts = transcript_no_ts
                session.commit()

            # 5) Ensure folder association
            ensure_folder_association(
                session,
                video_id,
                channel_id,
                human_playlist_name
            )

            # Mark one newly downloaded
            status_dict["newly_downloaded"] += 1

            processed_count += 1
            status_dict["processed"] = processed_count

    except Exception as e:
        logger.error(f"Database error: {e}")
        status_dict["errors"].append(str(e))
    finally:
        session.close()


def ensure_folder_association(session, video_id, channel_id, folder_name):
    """
    Helper to ensure there's a row in video_folders linking this 
    video_id to the channel/playlist (folder_name + original_playlist_id).
    """
    folder_assoc = session.query(VideoFolder).filter_by(
        original_playlist_id=channel_id,
        video_id=video_id
    ).first()
    if not folder_assoc:
        folder_assoc = VideoFolder(
            folder_name=folder_name,
            original_playlist_id=channel_id,
            video_id=video_id,
            last_modified=datetime.utcnow()
        )
        session.add(folder_assoc)
        session.commit()


def get_channel_and_videos(channel_url):
    """
    Use yt-dlp to list all videos from the channel or playlist (fast).
    Return:
      channel_id (str)
      videos (list of dict): { "video_id", "title", "upload_date" }
    """
    cmd = ["yt-dlp", "--flat-playlist", "--dump-single-json", channel_url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"yt-dlp failed: {result.stderr}")

    data = json.loads(result.stdout)
    channel_id = data.get("id", "unknown_channel_id")
    entries = data.get("entries", [])
    videos = []
    for entry in entries:
        vid_id = entry.get("id")
        vid_title = entry.get("title", "Untitled")
        upload_date = entry.get("upload_date", "UnknownDate")
        videos.append({
            "video_id": vid_id,
            "title": vid_title,
            "upload_date": upload_date
        })

    logger.info(f"Found {len(videos)} videos for '{channel_id}' using {channel_url}")
    return channel_id, videos


def get_upload_date_for_video(video_id):
    """
    Attempt to get a real upload date in 'YYYY-MM-DD' via:
      1) yt-dlp --dump-single-json https://www.youtube.com/watch?v=VIDEO_ID
      2) fallback to pytube
    Return date string or None.
    """
    # Try a single-video metadata query via yt-dlp
    cmd = ["yt-dlp", "--dump-single-json", f"https://www.youtube.com/watch?v={video_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            info = json.loads(result.stdout)
            raw_date = info.get("upload_date")  # "YYYYMMDD"
            if raw_date and len(raw_date) == 8:
                return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback to pytube
    try:
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        if yt.publish_date:
            return yt.publish_date.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None


def get_transcript_for_video(video_id):
    """
    Return a list of dicts => [ {"text":..., "start":..., "duration":...}, ...].
    Attempt youtube_transcript_api first, fallback to pytube SRT captions.
    Raise Exception if not found.
    """
    try:
        return YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
    except NoTranscriptFound:
        logger.info(f"No transcript via youtube_transcript_api for '{video_id}', trying pytube.")
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        caption = None
        for code, c in yt.captions.items():
            if 'en' in code.lower():
                caption = c
                break
        if caption is None:
            raise Exception("No English caption found via pytube.")
        srt_captions = caption.generate_srt_captions()
        return parse_srt(srt_captions)


def parse_srt(srt_text):
    """
    Convert raw SRT text => list of dicts:
        [ { "text":..., "start":..., "duration":... }, ... ]
    """
    lines = srt_text.split('\n')
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit():
            i += 1
            time_line = lines[i].strip()
            start_str, end_str = time_line.split('-->')
            start_sec = srt_time_to_seconds(start_str.strip())
            end_sec = srt_time_to_seconds(end_str.strip())

            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1

            caption_text = " ".join(text_lines)
            duration = end_sec - start_sec
            entries.append({
                "text": caption_text,
                "start": start_sec,
                "duration": duration
            })
        i += 1
    return entries


def srt_time_to_seconds(t_str):
    """
    Parse 'HH:MM:SS,mmm' => total seconds (float).
    e.g. "00:01:23,456" -> 83.456
    """
    h, m, s_milli = t_str.split(':')
    s, ms = s_milli.split(',')
    return int(h)*3600 + int(m)*60 + float(s) + float(ms)/1000.0


def build_transcript_variants(transcript_entries):
    """
    Given [ {"text", "start", "duration"}, ... ],
    build two text variants:
      1) transcript_with_ts => "[0.00s - 2.30s] Some text"
      2) transcript_no_ts   => "Some text"
    Return (with_ts, no_ts).
    """
    lines_with_ts = []
    lines_no_ts = []
    for entry in transcript_entries:
        start = entry["start"]
        dur = entry["duration"]
        text = entry["text"]
        line_with = f"[{start:.2f}s - {dur:.2f}s] {text}"
        lines_with_ts.append(line_with)
        lines_no_ts.append(text)

    transcript_with_ts = "\n".join(lines_with_ts)
    transcript_no_ts = "\n".join(lines_no_ts)
    return transcript_with_ts, transcript_no_ts


def list_downloaded_videos(channel_id):
    """
    Return list of dicts { "video_id", "title", "upload_date" }
    by querying the 'video_folders' + 'videos' tables in the DB.
    """
    session = SessionLocal()
    try:
        video_rows = (
            session.query(Video)
            .join(VideoFolder, Video.video_id == VideoFolder.video_id)
            .filter(VideoFolder.folder_name == channel_id)
            .all()
        )

        videos = []
        for v in video_rows:
            videos.append({
                "video_id": v.video_id,
                "title": v.title or "Untitled",
                "upload_date": v.upload_date or "UnknownDate"
            })
        return videos
    finally:
        session.close()