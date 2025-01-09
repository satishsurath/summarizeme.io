import os
import json
import subprocess
import logging
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from pytube import YouTube

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR is None:
    DATA_DIR = "data/channels"  # Base directory for channel data


def download_channel_transcripts(channel_url, status_dict):
    """
    1. Determine channel_id.
    2. List all video_ids from the channel.
    3. For each video, download transcript to local json file.
    4. Update status_dict to reflect progress (including errors).
    """
    channel_id, videos = get_channel_and_videos(channel_url)
    channel_path = os.path.join(DATA_DIR, channel_id)
    os.makedirs(os.path.join(channel_path, "transcripts"), exist_ok=True)
    os.makedirs(os.path.join(channel_path, "summaries_openai"), exist_ok=True)
    os.makedirs(os.path.join(channel_path, "summaries_ollama"), exist_ok=True)

    total_videos = len(videos)
    status_dict["total"] = total_videos

    logger.info(f"Starting to download transcripts for channel '{channel_id}' with {total_videos} videos.")

    processed_count = 0
    for video_meta in videos:
        video_id = video_meta["video_id"]
        transcript_file = os.path.join(channel_path, "transcripts", f"{video_id}.json")

        # If transcript is already downloaded, skip it
        if os.path.exists(transcript_file):
            processed_count += 1
            status_dict["processed"] = processed_count
            logger.info(f"Transcript for video '{video_id}' already exists. Skipping download.")
            continue

        try:
            transcripts = get_transcript_for_video(video_id)
            # Save transcript + metadata to file
            with open(transcript_file, "w", encoding="utf-8") as f:
                video_meta["transcript"] = transcripts
                json.dump(video_meta, f, ensure_ascii=False, indent=2)
            logger.info(f"Successfully downloaded and saved transcript for video '{video_id}'.")
        except Exception as e:
            logger.error(f"Failed to get transcript for video '{video_id}': {e}")
            status_dict["errors"].append(f"Video {video_id}: {e}")

        processed_count += 1
        status_dict["processed"] = processed_count

    logger.info(f"Finished processing channel '{channel_id}'. "
                f"Processed {processed_count} out of {total_videos} videos.")

def get_channel_and_videos(channel_url):
    """
    Use yt-dlp to list all videos from the channel (or playlist).
    Returns:
      channel_id (str): a unique ID or playlist ID
      videos (list of dict): each dict has "video_id", "title", "upload_date"
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

    logger.info(f"Found {len(videos)} videos for channel/playlist '{channel_id}' using URL: {channel_url}")
    return channel_id, videos

def get_transcript_for_video(video_id):
    """
    Attempt to retrieve the transcript via youtube_transcript_api (preferring English).
    Fallback to pytube if not found.
    Returns a list of dicts: [{ "text":..., "start":..., "duration":... }, ...]
    Raises an Exception if no transcript is available.
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
            raise Exception("No English caption found even via pytube.")
        srt_captions = caption.generate_srt_captions()
        return parse_srt(srt_captions)

def parse_srt(srt_text):
    """
    Parse SRT text into a list of dicts: [{"text":..., "start":..., "duration":...}, ...].
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
    Convert SRT time string 'HH:MM:SS,mmm' to total seconds as float.
    """
    h, m, s_milli = t_str.split(':')
    s, ms = s_milli.split(',')
    return int(h)*3600 + int(m)*60 + float(s) + float(ms)/1000.0

def list_downloaded_videos(channel_id):
    """
    Return a list of dicts describing the videos for the given channel,
    reading from local JSON files in the channel's transcripts folder.
    """
    channel_path = os.path.join(DATA_DIR, channel_id, "transcripts")
    if not os.path.exists(channel_path):
        return []

    files = os.listdir(channel_path)
    videos = []
    for f in files:
        if f.endswith(".json"):
            with open(os.path.join(channel_path, f), "r", encoding="utf-8") as jf:
                data = json.load(jf)
                videos.append({
                    "video_id": data.get("video_id"),
                    "title": data.get("title", "Untitled"),
                    "upload_date": data.get("upload_date", "UnknownDate")
                })
    return videos