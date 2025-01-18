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

from sync_service.models import Base, Video, VideoFolder

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

def download_channel_transcripts(channel_url, status_dict):
    """
    - Use yt-dlp to get channel_id and list of videos
    - For each video:
      - fetch transcript
      - build transcript_with_ts and transcript_no_ts
      - upsert into 'videos' (with the transcripts)
      - ensure a row in 'video_folders(folder_name=channel_id, video_id=...)'
    - Update status_dict for progress
    """
    Base.metadata.create_all(engine)  # or handle migrations as needed

    channel_id, videos = get_channel_and_videos(channel_url)
    total_videos = len(videos)
    status_dict["total"] = total_videos
    status_dict["processed"] = 0
    if "errors" not in status_dict:
        status_dict["errors"] = []

    # Optionally fix unknown upload_date by re-checking each video:
    # for v in videos:
    #     if v["upload_date"] == "UnknownDate":
    #         real_date = get_upload_date_for_video(v["video_id"])
    #         if real_date:
    #             v["upload_date"] = real_date

    session = SessionLocal()
    try:
        processed_count = 0
        for video_meta in videos:
            video_id = video_meta["video_id"]
            title = video_meta["title"]
            upload_date = video_meta["upload_date"]

            try:
                transcripts = get_transcript_for_video(video_id)
            except Exception as e:
                msg = f"Failed to get transcript for {video_id}: {e}"
                logger.error(msg)
                status_dict["errors"].append(msg)
                processed_count += 1
                status_dict["processed"] = processed_count
                continue

            # Convert transcript list of dicts => 2 text strings
            transcript_with_ts, transcript_no_ts = build_transcript_variants(transcripts)

            # Upsert video
            video_obj = session.query(Video).filter_by(video_id=video_id).first()
            if not video_obj:
                video_obj = Video(
                    video_id=video_id,
                    title=title,
                    upload_date=upload_date,
                    transcript_with_ts=transcript_with_ts,
                    transcript_no_ts=transcript_no_ts
                )
                session.add(video_obj)
            else:
                # update if needed
                video_obj.title = title
                video_obj.upload_date = upload_date
                video_obj.transcript_with_ts = transcript_with_ts
                video_obj.transcript_no_ts = transcript_no_ts

            session.commit()

            # Ensure folder row for (channel_id, video_id)
            folder_association = (
                session.query(VideoFolder)
                .filter_by(folder_name=channel_id, video_id=video_id)
                .first()
            )
            if not folder_association:
                folder_association = VideoFolder(
                    folder_name=channel_id,
                    video_id=video_id,
                    last_modified=datetime.utcnow()
                )
                session.add(folder_association)
                session.commit()

            processed_count += 1
            status_dict["processed"] = processed_count

    except Exception as e:
        logger.error(f"Database error: {e}")
        status_dict["errors"].append(str(e))
    finally:
        session.close()


def get_channel_and_videos(channel_url):
    """
    Use yt-dlp to list all videos from the channel (or playlist).
    Returns:
      channel_id (str) 
      videos (list of dict) => each has "video_id", "title", "upload_date"
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
    Optionally use "yt-dlp --dump-single-json" or pytube to get 'YYYY-MM-DD'.
    """
    cmd = ["yt-dlp", "--dump-single-json", f"https://www.youtube.com/watch?v={video_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            info = json.loads(result.stdout)
            raw_date = info.get("upload_date")
            if raw_date and len(raw_date) == 8:
                return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        except json.JSONDecodeError:
            pass

    # fallback
    try:
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        if yt.publish_date:
            return yt.publish_date.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def get_transcript_for_video(video_id):
    """
    Return a list of dicts: [{ "text":..., "start":..., "duration":... }, ...].
    """
    try:
        transcripts = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        return transcripts
    except NoTranscriptFound:
        logger.info(f"No transcript found via youtube_transcript_api for '{video_id}', trying pytube.")
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
    Convert SRT to a list of dicts: 
        [ {"text":..., "start":..., "duration":...}, ... ].
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
            while i < len(lines) and lines[i].strip() != '':
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
    Parse 'HH:MM:SS,mmm' => total seconds float
    e.g. "00:01:23,456" -> 83.456
    """
    h, m, s_milli = t_str.split(':')
    s, ms = s_milli.split(',')
    return int(h)*3600 + int(m)*60 + float(s) + float(ms)/1000.0

def build_transcript_variants(transcript_entries):
    """
    Given a list of { "text", "start", "duration" }, build:
      1) transcript_with_ts  => lines like "[0.00s - 2.30s] Some text"
      2) transcript_no_ts    => lines of just text
    Return (with_ts, no_ts).
    """
    lines_with_ts = []
    lines_no_ts = []
    for entry in transcript_entries:
        start = entry["start"]
        dur = entry["duration"]
        text = entry["text"]
        # E.g. "[12.34s - 3.21s] Transcript line"
        line_with = f"[{start:.2f}s - {dur:.2f}s] {text}"
        lines_with_ts.append(line_with)
        lines_no_ts.append(text)

    transcript_with_ts = "\n".join(lines_with_ts)
    transcript_no_ts = "\n".join(lines_no_ts)
    return transcript_with_ts, transcript_no_ts


def list_downloaded_videos(channel_id):
    """
    Return a list of dicts describing the videos for the given channel,
    querying the 'video_folders' and 'videos' tables from the DB.
    Each dict includes { "video_id", "title", "upload_date" }.
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