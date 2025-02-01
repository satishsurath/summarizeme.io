# update_db.py
import os
import logging
from sqlalchemy import create_engine, text

#from db.models import Base, Video, VideoFolder, SummariesV2


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# If using dotenv to load .env variables:
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # if python-dotenv not installed, just ensure DATABASE_URL is set externally.

DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
logger.info(f"Using DB_URL={DB_URL}")

#DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
engine = create_engine(DB_URL)

with engine.connect() as conn:
    # Try to add the new column; if it already exists, an exception will be printed.
    try:
        conn.execute(text("ALTER TABLE video_folders ADD COLUMN original_playlist_id VARCHAR(255)"))
        print("Column original_playlist_id added.")
    except Exception as e:
        print("Column original_playlist_id may already exist:", e)

    # For existing rows where original_playlist_id is NULL, copy folder_name over.
    conn.execute(text("UPDATE video_folders SET original_playlist_id = folder_name WHERE original_playlist_id IS NULL"))
    print("Backfilled original_playlist_id for existing rows.")