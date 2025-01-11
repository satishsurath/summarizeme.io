# sync_service/sync_service.py
import os
import sys
import json
import datetime
import logging
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, Video, VideoFolder, Summary, SyncJob

# Optional: for counting tokens (assuming tiktoken usage):
# pip install tiktoken
# if you prefer a simpler approach, do a naive word count or char count instead
try:
    import tiktoken
    tokenizer = tiktoken.get_encoding("cl100k_base")  # e.g. for gpt-3.5
except ImportError:
    tokenizer = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "data/channels")
DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")

def count_tokens(text):
    """
    Count approximate tokens in text. If tiktoken is unavailable, fallback to word count.
    """
    if not text:
        return 0
    if tokenizer:
        return len(tokenizer.encode(text))
    else:
        # fallback: word count as a rough approximation
        return len(text.split())

def strip_timestamps_from_transcript(transcript_entries):
    """
    transcript_entries is a list of { 'text': str, 'start': float, 'duration': float }
    Return a single string with just the text lines concatenated.
    """
    lines = [entry["text"] for entry in transcript_entries]
    return "\n".join(lines)

def run_sync():
    engine = create_engine(DB_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # Create tables if not existing
    Base.metadata.create_all(bind=engine)

    # Create a sync job record
    sync_job = SyncJob(status="in_progress", message="Sync started.")
    session.add(sync_job)
    session.commit()

    try:
        if not os.path.exists(DATA_DIR):
            logger.warning(f"DATA_DIR '{DATA_DIR}' does not exist. Nothing to sync.")
            sync_job.status = "failed"
            sync_job.message = f"DATA_DIR not found."
            sync_job.end_time = datetime.datetime.utcnow()
            session.commit()
            return

        # 1) For each folder => channel/playlist
        for folder_name in os.listdir(DATA_DIR):
            folder_path = os.path.join(DATA_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue  # skip files

            # transcripts dir
            transcripts_dir = os.path.join(folder_path, "transcripts")
            if os.path.exists(transcripts_dir):
                # For each .json transcript
                for fname in os.listdir(transcripts_dir):
                    if not fname.endswith(".json"):
                        continue
                    fullpath = os.path.join(transcripts_dir, fname)
                    stat = os.stat(fullpath)
                    # read the transcript JSON
                    try:
                        with open(fullpath, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                    except Exception as e:
                        logger.error(f"Failed to read transcript: {fullpath}, error={e}")
                        continue
                    
                    video_id = data.get("video_id")
                    title = data.get("title", "Untitled")
                    upload_date = data.get("upload_date", "UnknownDate")
                    if not video_id:
                        logger.warning(f"No video_id in {fullpath}, skipping.")
                        continue
                    
                    # Upsert in Videos
                    video_obj = session.query(Video).filter_by(video_id=video_id).first()
                    # Build text with timestamps
                    transcript_entries = data.get("transcript", [])
                    
                    with_ts_list = []
                    for entry in transcript_entries:
                        # e.g. "[10.0-4.0s] text"
                        start = entry.get("start", 0)
                        dur = entry.get("duration", 0)
                        text = entry.get("text", "")
                        line = f"[{start:.2f}s-{dur:.2f}s] {text}"
                        with_ts_list.append(line)
                    transcript_with_ts = "\n".join(with_ts_list)
                    transcript_no_ts = strip_timestamps_from_transcript(transcript_entries)

                    tokens_with_ts = count_tokens(transcript_with_ts)
                    tokens_no_ts = count_tokens(transcript_no_ts)

                    now = datetime.datetime.utcnow()

                    if not video_obj:
                        # create new
                        video_obj = Video(
                            video_id=video_id,
                            title=title,
                            upload_date=upload_date,
                            transcript_with_ts=transcript_with_ts,
                            transcript_no_ts=transcript_no_ts,
                            tokens_with_ts=tokens_with_ts,
                            tokens_no_ts=tokens_no_ts,
                            last_modified=now
                        )
                        session.add(video_obj)
                        logger.info(f"Inserted new video {video_id}.")
                    else:
                        # If we want to see if the file changed, check file mtime vs DB
                        # We assume transcript doesn't change once downloaded, 
                        # but let's do a quick check anyway:
                        # For demonstration, if transcript is empty or we want to refresh:
                        # or if the file's mtime is newer than video_obj.last_modified
                        # We'll skip rewriting if we assume transcripts never change.
                        pass

                    # Now link to folder
                    # We upsert folder_name => video
                    folder_assc = (
                        session.query(VideoFolder)
                        .filter_by(folder_name=folder_name, video_id=video_id)
                        .first()
                    )
                    if not folder_assc:
                        folder_assc = VideoFolder(
                            folder_name=folder_name,
                            video_id=video_id,
                            last_modified=now
                        )
                        session.add(folder_assc)
                        logger.info(f"Linked video {video_id} to folder {folder_name}.")
                    
                    # commit after each new video / folder association
                    session.commit()

            # 2) Summaries check
            # we might have "summaries_openai" and "summaries_ollama"
            for method in ["openai", "ollama"]:
                summary_dir = os.path.join(folder_path, f"summaries_{method}")
                if not os.path.exists(summary_dir):
                    continue
                for sf in os.listdir(summary_dir):
                    if not sf.endswith(".md"):
                        continue
                    summary_path = os.path.join(summary_dir, sf)
                    stat = os.stat(summary_path)
                    video_id = sf.replace(".md", "")
                    
                    # read the file
                    try:
                        with open(summary_path, "r", encoding="utf-8") as smd:
                            summary_text = smd.read()
                    except Exception as e:
                        logger.error(f"Failed to read summary: {summary_path}, error={e}")
                        continue

                    # Upsert into Summaries
                    summary_obj = (
                        session.query(Summary)
                        .filter_by(video_id=video_id, summary_type=method, file_path=summary_path)
                        .first()
                    )
                    now = datetime.datetime.utcnow()
                    tok_count = count_tokens(summary_text)

                    if not summary_obj:
                        summary_obj = Summary(
                            video_id=video_id,
                            summary_type=method, 
                            #if openai, model_name="gpt-4", if ollama, model_name="llama3.2"
                            model_name="gpt-4o" if method == "openai" else "llama3.2",
                            #model_name=method,  # or parse from file name if needed
                            summary_text=summary_text,
                            tokens_count=tok_count,
                            file_path=summary_path,
                            file_mtime=datetime.datetime.utcfromtimestamp(stat.st_mtime),
                            date_generated=now,
                        )
                        session.add(summary_obj)
                        logger.info(f"Inserted new summary for video={video_id}, type={method}.")
                    else:
                        # Check if file_mtime changed
                        file_mtime_dt = datetime.datetime.utcfromtimestamp(stat.st_mtime)
                        if file_mtime_dt > (summary_obj.file_mtime or datetime.datetime.min):
                            summary_obj.summary_text = summary_text
                            summary_obj.tokens_count = tok_count
                            summary_obj.file_mtime = file_mtime_dt
                            # If you store a real model name from the file or metadata, update it
                            session.commit()
                            logger.info(f"Updated summary for video={video_id}, type={method} due to changed file.")
                    
                    session.commit()
        
        sync_job.status = "completed"
        sync_job.message = "Sync completed successfully."
        sync_job.end_time = datetime.datetime.utcnow()
        session.commit()

    except Exception as e:
        logger.error(f"Sync service encountered an error: {e}")
        sync_job.status = "failed"
        sync_job.message = f"Error: {e}"
        sync_job.end_time = datetime.datetime.utcnow()
        session.commit()
        session.close()
        sys.exit(1)

    session.close()

if __name__ == "__main__":
    run_sync()
