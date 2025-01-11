# sync_service/embedding_sync.py

import os
import psycopg2
import logging

logger = logging.getLogger(__name__)

def run_embedding_sync():
    """
    One-time function to create or update a pgai vectorizer 
    for your transcripts or 'videos' table using Ollama as the embedding source.
    
    This assumes you have installed pgai, pgvector, etc., 
    and that you have a table to embed, e.g. `public.videos` or `public.transcripts`.
    """

    # Read environment or .env
    DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
    REMOTE_OLLAMA_HOST = os.getenv("REMOTE_OLLAMA_HOST", "ollama-remote-hostname")

    # Build a full URL for Ollama, typically port 11434
    OLLAMA_URL = f"http://{REMOTE_OLLAMA_HOST}:11434"

    logger.info(f"Starting embedding sync with Ollama at {OLLAMA_URL}...")

    # Connect to DB
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:
        # Example: create vectorizer for a table named `videos` with a `transcript_no_ts` column
        # If your table or column differs, change accordingly.

        # This only needs to be run once, so you might do some checks first:
        # e.g., SELECT * FROM pgai.vectorizers WHERE table_name='videos' ...
        # For simplicity, we'll just run it every time.
        sql = f"""
            -- install the pgai extension
            create extension if not exists ai cascade;
            SELECT ai.create_vectorizer(
                'public.videos'::regclass,
                embedding => ai.embedding_ollama(
                    'nomic-embed-text',
                    768,
                    base_url => '{OLLAMA_URL}'  -- The standard port 11434 is appended
                ),
                -- Adjust chunking for transcripts:
                chunking => ai.chunking_recursive_character_text_splitter(
                    'transcript_no_ts',
                    1000,
                    200,
                    separators => array[E'\n\n', E'\n', '.', '?', '!']
                ),
                -- You can tweak the formatting if you want to add more metadata
                formatting => ai.formatting_python_template(
                    'Video Title: $title\\nTranscript Chunk:\\n$chunk'
                )
            );
        """

        logger.info(f"Executing vectorizer creation:\n{sql}")
        cur.execute(sql)
        result = cur.fetchone()

        # result might be something like: 
        # {"status": "created"} or a JSON response. We can log it:
        logger.info(f"Vectorizer result: {result}")

        conn.commit()

    except Exception as e:
        logger.error(f"Error creating/updating vectorizer: {e}")
    finally:
        cur.close()
        conn.close()

    logger.info("Embedding sync (via pgai vectorizer) is completed.")
