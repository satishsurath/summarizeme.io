#run_vectorizers.py

import os
import psycopg2
from dotenv import load_dotenv



def main():

    # 1) Load your DB connection info from environment:
    #Read the env file and load the values
    load_dotenv()
    ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
    DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
    print(f"DB_URL: {DB_URL}")

    # Build a full URL for Ollama, typically port 11434
    OLLAMA_URL = f"http://{ollama_host}:11434"

    # Connect to Postgres
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:

        # 2) Ensure pgai extension installed
        print("[INFO] Ensuring pgai extension is installed...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS ai CASCADE;")
        conn.commit()

        # 1) Create vectorizer for transcript (videos.transcript_no_ts).
        #    This might already exist, but we’ll show it for completeness.
        transcript_sql = f"""
        SELECT ai.create_vectorizer(
            'public.videos'::regclass,
            embedding => ai.embedding_ollama(
                'nomic-embed-text',
                768,
                base_url => '{OLLAMA_URL}'
            ),
            chunking => ai.chunking_recursive_character_text_splitter(
                'transcript_no_ts',
                1000,
                200,
                separators => array[E'\\n\\n', E'\\n', '.', '?', '!']
            ),
            formatting => ai.formatting_python_template(
                'Video Title: $title\\nTranscript chunk:\\n$chunk'
            ),
            indexing => ai.indexing_default()
        );
        """

        # 2) Create vectorizers for each summaries_v2 column.
        #    Because 'summaries_v2' has a PK (id), this will succeed.
        #    We can reference $video_title and $video_id in the formatting template.

        # Common chunking config for markdown headings
        # chunk_size=2000, chunk_overlap=200
        # first splitting on headings, then fallback to line breaks + punctuation
        # is_separator_regex => true because we’re using ^# anchors in the array.


        # Vectorizer for concise_summary
        concise_summary_sql = f"""
        SELECT ai.create_vectorizer(
            'public.summaries_v2'::regclass,
            destination => 'summaries_v2_concise_summary_embedding',  -- <--- UNIQUE DESTINATION
            embedding => ai.embedding_ollama(
                'nomic-embed-text',
                768,
                base_url => '{OLLAMA_URL}'
            ),
            chunking => ai.chunking_recursive_character_text_splitter(
                'concise_summary',
                2000,
                200,
                separators => array[
                    E'^# ',
                    E'^## ',
                    E'^### ',
                    E'^#### ',
                    E'^##### ',
                    E'\\n\\n',
                    E'\\n',
                    '.',
                    '?',
                    '!'
                ],
                is_separator_regex => true
            ),
            formatting => ai.formatting_python_template(
                'Video ID: $video_id\\nVideo Title: $video_title\\nConcise Summary chunk:\\n$chunk'
            ),
            indexing => ai.indexing_default()
        );
        """

        # Vectorizer for key_topics
        key_topics_sql = f"""
        SELECT ai.create_vectorizer(
            'public.summaries_v2'::regclass,
            destination => 'summaries_v2_key_topics_embedding',  -- <--- UNIQUE DESTINATION
            embedding => ai.embedding_ollama(
                'nomic-embed-text',
                768,
                base_url => '{OLLAMA_URL}'
            ),
            chunking => ai.chunking_recursive_character_text_splitter(
                'key_topics',
                2000,
                200,
                separators => array[
                    E'^# ',
                    E'^## ',
                    E'^### ',
                    E'^#### ',
                    E'^##### ',
                    E'\\n\\n',
                    E'\\n',
                    '.',
                    '?',
                    '!'
                ],
                is_separator_regex => true
            ),
            formatting => ai.formatting_python_template(
                'Video ID: $video_id\\nVideo Title: $video_title\\nKey Topics chunk:\\n$chunk'
            ),
            indexing => ai.indexing_default()
        );
        """

        # Vectorizer for important_takeaways
        important_takeaways_sql = f"""
        SELECT ai.create_vectorizer(
            'public.summaries_v2'::regclass,
            destination => 'summaries_v2_important_takeaways_embedding', -- <--- UNIQUE DESTINATION
            embedding => ai.embedding_ollama(
                'nomic-embed-text',
                768,
                base_url => '{OLLAMA_URL}'
            ),
            chunking => ai.chunking_recursive_character_text_splitter(
                'important_takeaways',
                2000,
                200,
                separators => array[
                    E'^# ',
                    E'^## ',
                    E'^### ',
                    E'^#### ',
                    E'^##### ',
                    E'\\n\\n',
                    E'\\n',
                    '.',
                    '?',
                    '!'
                ],
                is_separator_regex => true
            ),
            formatting => ai.formatting_python_template(
                'Video ID: $video_id\\nVideo Title: $video_title\\nImportant Takeaways chunk:\\n$chunk'
            ),
            indexing => ai.indexing_default()
        );
        """

        # Vectorizer for comprehensive_notes
        comprehensive_notes_sql = f"""
        SELECT ai.create_vectorizer(
            'public.summaries_v2'::regclass,
            destination => 'summaries_v2_comprehensive_notes_embedding', -- <--- UNIQUE DESTINATION
            embedding => ai.embedding_ollama(
                'nomic-embed-text',
                768,
                base_url => '{OLLAMA_URL}'
            ),
            chunking => ai.chunking_recursive_character_text_splitter(
                'comprehensive_notes',
                2000,
                200,
                separators => array[
                    E'^# ',
                    E'^## ',
                    E'^### ',
                    E'^#### ',
                    E'^##### ',
                    E'\\n\\n',
                    E'\\n',
                    '.',
                    '?',
                    '!'
                ],
                is_separator_regex => true
            ),
            formatting => ai.formatting_python_template(
                'Video ID: $video_id\\nVideo Title: $video_title\\nComprehensive Notes chunk:\\n$chunk'
            ),
            indexing => ai.indexing_default()
        );
        """

        print("[INFO] Creating transcript vectorizer for videos.transcript_no_ts...")
        cur.execute(transcript_sql)

        print("[INFO] Creating concise_summary vectorizer...")
        cur.execute(concise_summary_sql)

        print("[INFO] Creating key_topics vectorizer...")
        cur.execute(key_topics_sql)

        print("[INFO] Creating important_takeaways vectorizer...")
        cur.execute(important_takeaways_sql)

        print("[INFO] Creating comprehensive_notes vectorizer...")
        cur.execute(comprehensive_notes_sql)

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Unable to create vectorizers: {e}")
    finally:
        cur.close()
        conn.close()

    print("[SUCCESS] All vectorizers created successfully!")

if __name__ == "__main__":
    main()