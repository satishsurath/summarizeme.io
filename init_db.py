#!/usr/bin/env python3
"""
init_db.py

One-time script to initialize the database using SQLAlchemy models.
"""
import os
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# If you keep the models in a separate module (e.g. sync_service/models.py),
# update the import path accordingly:
from db.models import Base, Video, VideoFolder, SummariesV2, User

# If using dotenv to load .env variables:
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # if python-dotenv not installed, just ensure DATABASE_URL is set externally.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Read DB connection from environment
    DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
    logger.info(f"Using DB_URL={DB_URL}")

    # Create engine & session
    engine = create_engine(DB_URL, echo=True)
    SessionLocal = sessionmaker(bind=engine)

    # Create all tables that do not exist
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully (tables created if not existing).")

if __name__ == "__main__":
    main()
