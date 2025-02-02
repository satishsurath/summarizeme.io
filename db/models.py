# sync_service/models.py
import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

Base = declarative_base()

class Video(Base):
    __tablename__ = "videos"
    # We use the YT video_id as a unique string primary key for easy referencing
    video_id = Column(String(50), primary_key=True)
    # Newly added columns:
    title = Column(String(512))              # e.g. video title
    upload_date = Column(String(32))         # e.g. "2023-12-01" or "UnknownDate"    
    transcript_with_ts = Column(Text)
    transcript_no_ts = Column(Text)
    tokens_with_ts = Column(Integer, default=0)
    tokens_no_ts = Column(Integer, default=0)
    last_modified = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship to summaries and folder associations
    folders = relationship("VideoFolder", back_populates="video")
    # The new V2 Summaries relationship:
    summaries_v2 = relationship("SummariesV2", back_populates="video")

class VideoFolder(Base):
    __tablename__ = "video_folders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_name = Column(String(255))  # This is the human‐readable (renamable) name
    original_playlist_id = Column(String(255))  # NEW: stores the immutable YouTube playlist id
    video_id = Column(String(50), ForeignKey("videos.video_id"))
    last_modified = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="folders")



# The NEW Summaries v2 table (without the old columns),
# and with the new fields: concise_summary, key_topics, etc.
class SummariesV2(Base):
    __tablename__ = "summaries_v2"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(50), ForeignKey("videos.video_id"))
    video_title = Column(String(512))
    model_name = Column(String(50))      # e.g. "phi4"
    date_generated = Column(DateTime, default=datetime.datetime.utcnow)
    concise_summary = Column(Text)            # new
    key_topics = Column(Text)                 # new
    important_takeaways = Column(Text)        # new
    comprehensive_notes = Column(Text)        # new

    video = relationship("Video", back_populates="summaries_v2")    

class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime)
    status = Column(String(50), default="in_progress") # in_progress, completed, failed
    message = Column(Text)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), default="reader")  # e.g. possible roles: "admin", "member", "reader"