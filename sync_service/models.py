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
    summaries = relationship("Summary", back_populates="video")

class VideoFolder(Base):
    __tablename__ = "video_folders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_name = Column(String(255))
    video_id = Column(String(50), ForeignKey("videos.video_id"))
    last_modified = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="folders")

class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(50), ForeignKey("videos.video_id"))
    summary_type = Column(String(50))  # e.g. "openai" or "ollama"
    model_name = Column(String(50))    # e.g. "gpt-4" or "llama3.2"
    summary_text = Column(Text)
    tokens_count = Column(Integer, default=0)
    file_path = Column(String(512))    # local path
    file_mtime = Column(DateTime)      # last modification time from file system
    date_generated = Column(DateTime)  # optional, e.g. from summary's metadata

    video = relationship("Video", back_populates="summaries")

class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime)
    status = Column(String(50), default="in_progress") # in_progress, completed, failed
    message = Column(Text)
