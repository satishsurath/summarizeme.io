Below is a revised README with improved formatting, including instructions to initialize the database and create vectorizers via your one-time scripts (init_db.py and the vectorizer script). Adapt as needed!

# summarizeme.io – YouTube Transcript Summaries & Chat

summarizeme.io is a Python Flask application that downloads transcripts from a YouTube channel (or a single video within a channel) and provides multiple ways to summarize and chat with the content:

- Summaries
- Uses Ollama (LLaMA-based local text generation).
- Summaries are stored as SummariesV2 in a Postgres database for each video.
- Chat
- Allows you to query either an entire channel or a single video using vector-embedded data.
- Employs Ollama for embeddings (via nomic-embed-text) and generation.

This provides a convenient way to explore long-form YouTube content. You can rename or delete channels, filter videos, and handle everything via a user-friendly web interface.

## Key Updates in This Version

1.	Database Integration
	- Moved from file-based metadata to Postgres for videos, summaries, and channel-folder associations (via SQLAlchemy).
	- Video transcripts, summarizations, and channel info can now be queried, renamed, or deleted using REST endpoints.
2.	New Summaries (v2)
	- Four different summary fields per video: concise_summary, key_topics, important_takeaways, and comprehensive_notes.
	- Built with chunking logic so each video’s transcript is broken into manageable sections for LLM summarization.
3.	Channel & Video Chat
	- Ability to chat across an entire channel (aggregating relevant chunks from multiple videos).
	- Ability to chat with a single video and retrieve context from selected summary fields (or from the raw transcript embedding).
	- Uses vector embeddings with Ollama (nomic-embed-text) and a Postgres-based vector store (via PGVector or PGAI).
4.	Channel Management
	- Rename a channel folder from the database.
	- Delete a channel folder (and optionally remove all videos that are no longer referenced by any folder).
5.	Ollama Remote Integration
	- Support for a remote Ollama instance (via a configurable host in .env).
	- New endpoint to list available Ollama models: /api/ollama/models.

## Features Overview

1.	Channel-Wide Transcript Download
	Provide a channel URL (or a single video URL from that channel), and the application downloads transcripts for each video.
	- No channel? No problem—just supply any video from a channel, and it will infer the channel ID.
2.	Summarization (v2)
	- Breaks large transcripts into ~4,000-word chunks for safe LLM processing.
	- Generates four specialized summaries:
		1.	Concise Summary
		2.	Key Topics
		3.	Important Takeaways
		4.	Comprehensive Notes
	- Stores each summary in the SummariesV2 table for future retrieval or chat usage.
3.	Database & File Storage
	- Postgres for storing video metadata, transcripts (text), and summary objects.
	- Optionally, you can still keep raw transcript files under data/ if desired.
	- Minimal or no reliance on an external queue — background threads are used for demonstration.
4.	Chat Across a Channel
	- Combine chunk embeddings from multiple videos for more robust Q&A.
	- Embeddings are stored in Postgres views/tables, so you can query them easily.
5.	Chat With a Single Video
	- Focus Q&A on just one video’s transcript or summary fields.
	- Embedding-based retrieval to supply context to Ollama’s local LLM.
6.	Channel Rename / Delete
	- Rename: The /api/channels/rename route changes the folder_name across all relevant videos.
	- Delete: The /api/channels/delete route removes the specified folder and any unreferenced videos.
7.	Error Handling & Progress Tracking
	- Graceful fallback if a single video fails to download or summarize.
	- Front-end polling endpoints to get progress updates (e.g. /api/channel/status/<task_id>).

## Folder & Database Structure

### Directory Layout
```
my_youtube_transcript_summarizer/
├─ app.py               # Main Flask app (with routes, chat endpoints)
├─ youtube_utils.py     # Functions for downloading YouTube transcripts
├─ summarizer_v2.py     # Chunking, prompting, generation logic
├─ openai_summarizer.py # (Older summarizer approach, optional)
├─ ollama_summarizer.py # (Older summarizer approach, optional)
├─ requirements.txt
├─ .env.example         # Example environment file
├─ README.md
├─ data/
│  └─ channels/
│     └─ <channel-id>/
│        ├─ transcripts/
│        │  └─ *.json
│        ├─ summaries_openai/
│        │  └─ *.md
│        └─ summaries_ollama/
│           └─ *.md
├─ templates/
│  ├─ layout.html
│  ├─ index.html
│  ├─ status.html
│  ├─ videos.html
│  ├─ channel_chat.html   # Chat interface for entire channel
│  ├─ video_chat.html     # Chat interface for single video
│  ├─ summary_v2.html     # View SummariesV2 details
│  └─ summary_view.html   # (Legacy single summary view)
└─ static/
   ├─ css/
   │  └─ styles.css
   └─ js/
      ├─ index.js
      ├─ status.js
      └─ videos.js
```


### Database Schema (Simplified)
```
	- videos
	- video_id (primary key, typically the YouTube video ID)
	- title, transcript_no_ts, upload_date, etc.
	- video_folders
	- folder_name (i.e., channel name or ID)
	- video_id (FK to videos)
	- last_modified
	- summaries_v2
	- id (primary key)
	- video_id (FK to videos)
	- model_name
	- concise_summary, key_topics, important_takeaways, comprehensive_notes (text fields)
	- date_generated
	- Vector Embedding Tables/Views (with PGVector or PGAI)
	- e.g. videos_embedding, summaries_v2_concise_summary_embedding, etc.
	- These store embeddings for chunked text, used for chat retrieval.
```

## Requirements

1.	Python 3.10+
2.	Virtualenv or pipenv (recommended)
3.	PostgreSQL 14+ (for storing transcripts, summaries, and embeddings)
4.	Ollama (LLaMA-based local text generation + embedding)
- Must be installed locally or running on a remote machine.
- The .env file must point to the correct host/URL for your Ollama instance.
5.	(Optional) If you still plan to use OpenAI for summarization, you’ll need an OpenAI API Key.

## Setup Instructions

1. Clone the repository
```
git clone <this-repo-url>
cd my_youtube_transcript_summarizer
```

2. Set up a virtual environment

Mac / Linux:
```
python3 -m venv venv
source venv/bin/activate
```
Windows:
```
python -m venv venv
.\venv\Scripts\activate
```
3. Install dependencies
```
pip install -r requirements.txt
```
4. Configure .env

Copy the provided example:
```
cp .env.example .env
```
Then edit .env to set:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
REMOTE_OLLAMA_HOST=localhost         # or your server IP
```
Make sure you have a running Postgres instance that matches the DATABASE_URL.

5. Initialize the Database

Run the init_db.py script (found in your repository) to create tables:
```
python init_db.py
```
This script:
	- Loads environment variables to locate your database (DATABASE_URL).
	- Creates all tables (videos, video_folders, summaries_v2, etc.) if they do not already exist.

6. Create Vectorizers

If you plan to chat with embedded transcripts and summaries, you’ll need the vectorizers created. Run init_vectorizers.py:
```
python init_vectorizers.py
```
This script:
	1.	Creates vectorizers for videos.transcript_no_ts.
	2.	Creates vectorizers for each SummariesV2 field (concise_summary, key_topics, important_takeaways, comprehensive_notes).
	3.	Registers them in the PGVector or PGAI extension so that embeddings can be generated on demand and stored in specialized tables/views.

Note: Ensure you have PGVector or the PGAI extension installed in your Postgres.

7. Run the App

Mac / Linux:
```
source venv/bin/activate
flask run
```
Windows:
```
.\venv\Scripts\activate
flask run
```
By default, the app runs at: http://127.0.0.1:5000.

## Usage

1. Downloading Transcripts
	1.	Open your browser to http://127.0.0.1:5000.
	2.	Enter a YouTube channel URL or video URL from that channel and click “Start Download.”
	3.	Check the Status page (/status) to see progress.
	4.	Once completed, you can list videos under the videos page (/videos/<channel-name>).

2. Summarizing Videos (SummariesV2)
	1.	From the Videos page for a channel, select videos to summarize (or set up a button that calls /api/summarize_v2).
	2.	The system chunkifies transcripts and produces four types of summaries:
	1.	Concise Summary
	2.	Key Topics
	3.	Important Takeaways
	4.	Comprehensive Notes
	3.	Progress updates are available at /api/summarize_v2/status/<task_id>.

3. Chatting With a Channel (/chat-channel/<channel_name>)
	1.	Navigate to <http://127.0.0.1:5000/chat-channel/<channel_name>>.
	2.	Type your query in the prompt. The system:
	1.	Embeds your query via Ollama (nomic-embed-text).
	2.	Retrieves the top relevant chunks from the summary or transcript embeddings for all videos in that channel.
	3.	Generates a final answer with your chosen LLM model (e.g., phi4:latest).

4. Chatting With a Single Video (/chat-video/<video_id>)
	1.	Navigate to <http://127.0.0.1:5000/chat-video/<video_id>>.
	2.	Enter your query, and the system will embed that query and retrieve the top chunks (from that single video’s transcript or chosen summary field).

5. Channel Management

- Rename Channel:
Send a POST request to /api/channels/rename with JSON:
```
{
  "old_name": "OldChannelName",
  "new_name": "NewChannelName"
}
```

- Delete Channel:
Send a POST request to /api/channels/delete with JSON:
```
{
  "name": "ChannelNameToDelete"
}
```
This removes the channel folder references; any videos no longer referenced by any folder are also deleted.

6. Checking Ollama Models

A GET request to /api/ollama/models returns the list of available models from your remote Ollama instance.

## Environment Variables

| Variable              | Description                                                    | Example                                 |
|-----------------------|----------------------------------------------------------------|-----------------------------------------|
| OPENAI_API_KEY        | Your OpenAI API Key (only if using ChatGPT/OpenAI)             | sk-abc123...                            |
| DATABASE_URL          | Postgres connection URL                                        | postgresql://user:pass@localhost:5432/mydb |
| REMOTE_OLLAMA_HOST    | Hostname/IP for your remote Ollama service (default port 11434) | localhost or remote.server.com         |


## Troubleshooting / Tips
1.	Ensure Ollama Is Running
	- By default, Ollama listens on port 11434. If running remotely, confirm your firewall allows incoming requests or use SSH tunneling.
2.	Check DB Connectivity
	- Make sure DATABASE_URL is correct and the tables exist.
	- If you run into table-not-found errors, verify that init_db.py was executed successfully.
3.	Embedding Performance
	- Large transcripts can be slow to embed. If you have memory constraints, consider adjusting chunk sizes or concurrency.
4.	Long Summaries
	- Summaries might cut off if the LLM hits a token limit. In that case, reduce chunk size or model context length.

## License

This project is licensed under the MIT License — see the LICENSE file for details.

## Contributing

Pull requests and discussions are welcome! Feel free to open an issue for feature requests or bug reports.