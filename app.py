# app.py
import os
import json
import threading
import logging
from flask import Flask, request, jsonify, render_template, abort
import markdown
import re # used for renaming the channel folder 
from dotenv import load_dotenv

from youtube_utils import download_channel_transcripts, list_downloaded_videos
from openai_summarizer import summarize_transcript_openai
from ollama_summarizer import summarize_transcript_ollama
from ollama_phi4_transcript_enhancer import transcript_enhancer_ollama

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text

# If you store your models and sync code in separate modules:
from sync_service.models import Base, Video, VideoFolder, Summary, SyncJob
from sync_service.sync import run_sync  # Contains the run_sync() function

# Import your new sync function
from sync_service.embedding_sync import run_embedding_sync



DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Read the env file
load_dotenv()
ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
print(f"ollama_host: {ollama_host}")
# Build a full URL for Ollama, typically port 11434
OLLAMA_URL = f"http://{ollama_host}:11434"

# In-memory storage for statuses (for demo). 
# For production, use a database or a caching layer (Redis).
download_statuses = {}
summarize_statuses = {}

DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR is None:
    DATA_DIR = "data/channels"  # Base directory for channel data
print(f"DATA_DIR: {DATA_DIR}")

@app.route('/')
def index():
    """
    Main page: form to enter a channel URL (or a video from that channel).
    Also lists already downloaded channels as links.
    """
    """
    Renders a page that shows channels/folders that have embedded data.
    We'll query the 'video_folders' table for all distinct folder_name.
    """
    session = SessionLocal()
    try:
        # SELECT DISTINCT folder_name FROM video_folders
        folder_rows = session.query(VideoFolder.folder_name).distinct().all()
        channel_list = [row.folder_name for row in folder_rows]
    finally:
        session.close()

    # Render a template that displays each channel as a link
    return render_template('index.html', channels=channel_list)


@app.route('/status')
def status_page():
    """
    Basic page to show status progress.
    """
    return render_template('status.html')


@app.route('/videos/<channel_name>')
def videos_page(channel_name):
    """
    Render a page to chat with the entire channel.
    Also show all videos that belong to this channel.
    """
    session = SessionLocal()
    try:
        # SELECT v.* 
        # FROM videos v
        # JOIN video_folders vf ON v.video_id = vf.video_id
        # WHERE vf.folder_name = :channel_name
        videos = (
            session.query(Video)
            .join(VideoFolder, Video.video_id == VideoFolder.video_id)
            .filter(VideoFolder.folder_name == channel_name)
            .all()
        )
        video_data = []
        for vid in videos:
            summaries_by_type = {}
            for s in vid.summaries:
                stype = s.summary_type.lower()  # "ollama", "openai", etc.
                if stype not in summaries_by_type:
                    summaries_by_type[stype] = []
                summaries_by_type[stype].append(s)

            video_data.append({
                "video": vid,
                "summaries_by_type": summaries_by_type
            })        
    finally:
        session.close()

    # We'll pass `videos` to the template so we can display them
    return render_template("videos.html", channel_name=channel_name, video_data=video_data)


@app.route('/api/channel/start', methods=['POST'])
def api_channel_start():
    """
    Start downloading transcripts for the entire channel.
    Expects JSON: { "channel_url": "https://www.youtube.com/..." }
    """
    data = request.get_json()
    if not data or 'channel_url' not in data:
        return jsonify({"status": "error", "message": "No channel_url provided"}), 400

    channel_url = data['channel_url'].strip()
    # Generate a unique task ID for tracking 
    task_id = f"dl_{len(download_statuses)+1}"

    # Initialize the task status in memory
    download_statuses[task_id] = {
        "status": "in_progress",
        "processed": 0,
        "total": 0,
        "errors": []
    }

    def run_download():
        try:
            # This function now ensures that for every video,
            # a row in video_folders(folder_name=<channel_id>, video_id=...) is inserted
            download_channel_transcripts(channel_url, download_statuses[task_id])
            download_statuses[task_id]["status"] = "completed"
        except Exception as e:
            logger.error(f"Error in channel download: {e}")
            download_statuses[task_id]["status"] = "failed"
            download_statuses[task_id]["errors"].append(str(e))

    # Run the download in a background thread so we don’t block the Flask request
    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()

    return jsonify({"status": "initiated", "task_id": task_id})

@app.route('/api/channel/status/<task_id>', methods=['GET'])
def api_channel_status(task_id):
    """
    Returns the status of an ongoing channel download process.
    """
    status = download_statuses.get(task_id)
    if not status:
        return jsonify({"status": "error", "message": "Invalid task ID"}), 404
    return jsonify(status)


@app.route('/api/videos/<channel_id>', methods=['GET'])
def api_get_videos(channel_id):
    """
    List the downloaded videos for a channel in a paginated fashion.
    Query params:
      - page (int)
      - page_size (int)
      - sort_by (str) => "title" or "date"
      - filter (str) => partial match on title
    """
    page = int(request.args.get('page', 1))
    page_size = 100
    sort_by = request.args.get('sort_by', 'title')  # or 'date'
    filter_str = request.args.get('filter', '')

    videos = list_downloaded_videos(channel_id)
    # For each video, check if openai/ollama summary exist
    for v in videos:
        vid = v["video_id"]
        openai_path = os.path.join(DATA_DIR, channel_id, "summaries_openai", f"{vid}.md")
        ollama_path = os.path.join(DATA_DIR, channel_id, "summaries_ollama", f"{vid}.md")
        v["openai_summary_exists"] = os.path.exists(openai_path)
        v["ollama_summary_exists"] = os.path.exists(ollama_path)

    # Apply filter
    if filter_str:
        filter_lower = filter_str.lower()
        videos = [v for v in videos if filter_lower in v['title'].lower()]

    # Sort
    if sort_by == 'title':
        videos.sort(key=lambda x: x['title'])
    elif sort_by == 'date':
        videos.sort(key=lambda x: x['upload_date'], reverse=True)

    total = len(videos)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated = videos[start_idx:end_idx]

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "videos": paginated
    })


@app.route('/api/summarize', methods=['POST'])
def api_summarize():
    """
    Summarize one or more videos' transcripts using either OpenAI or Ollama.
    Expects JSON:
    {
      "channel_id": "...",
      "video_ids": ["id1", "id2", ...],
      "method": "openai" or "ollama"
    }
    """
    data = request.get_json()
    if not all(k in data for k in ("channel_id", "video_ids", "method")):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    channel_id = data['channel_id']
    video_ids = data['video_ids']
    method = data['method']

    task_id = f"sum_{len(summarize_statuses)+1}"
    summarize_statuses[task_id] = {
        "status": "in_progress",
        "processed": 0,
        "total": len(video_ids),
        "errors": []
    }

    def run_summarize():
        try:
            for vid in video_ids:
                # Summarize each transcript
                if method == "openai":
                    summarize_transcript_openai(channel_id, vid)
                elif method == "ollama":
                    summarize_transcript_ollama(channel_id, vid)
                else:
                    transcript_enhancer_ollama(channel_id, vid)
                summarize_statuses[task_id]["processed"] += 1
            summarize_statuses[task_id]["status"] = "completed"
        except Exception as e:
            logger.error(f"Error in summarization: {e}")
            summarize_statuses[task_id]["status"] = "failed"
            summarize_statuses[task_id]["errors"].append(str(e))

    thread = threading.Thread(target=run_summarize)
    thread.start()

    return jsonify({"status": "initiated", "task_id": task_id})


@app.route('/api/summarize/status/<task_id>', methods=['GET'])
def api_summarize_status(task_id):
    """
    Returns summarization progress.
    """
    status = summarize_statuses.get(task_id)
    if not status:
        return jsonify({"status": "error", "message": "Invalid task ID"}), 404
    return jsonify(status)


@app.route("/api/channels", methods=["GET"])
def api_list_channels():
    session = SessionLocal()
    try:
        folders = (
            session.query(VideoFolder.folder_name)
            .distinct()
            .all()
        )
        # Convert to a simple list of folder names
        folder_list = [f.folder_name for f in folders]
    finally:
        session.close()

    return jsonify(folder_list)

@app.route('/api/channels/rename', methods=['POST'])
def api_rename_channel():
    """
    Renames a channel in the database (video_folders.folder_name).
    Expects JSON:
    { "old_name": "...", "new_name": "..." }
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_name or not new_name:
        return jsonify({
            "status": "error",
            "message": "old_name and new_name are required"
        }), 400

    # Example of sanitizing the new_name to allow only letters, digits, underscores, hyphens, spaces.
    safe_new_name = re.sub(r"[^a-zA-Z0-9_\-\s]", "", new_name)
    if not safe_new_name:
        return jsonify({"status": "error", "message": "Invalid characters in new_name"}), 400

    session = SessionLocal()
    try:
        # Check if old_name actually exists in the DB
        count_old = session.query(VideoFolder).filter_by(folder_name=old_name).count()
        if count_old == 0:
            return jsonify({
                "status": "error",
                "message": f"Channel '{old_name}' not found in database."
            }), 404

        # Optional: Check if new_name already exists (if you don't allow duplicates)
        count_new = session.query(VideoFolder).filter_by(folder_name=safe_new_name).count()
        if count_new > 0:
            return jsonify({
                "status": "error",
                "message": f"Channel '{safe_new_name}' already exists."
            }), 400

        # Perform the update (rename)
        session.query(VideoFolder).filter_by(folder_name=old_name).update({
            "folder_name": safe_new_name
        })
        session.commit()

        return jsonify({
            "status": "ok",
            "old_name": old_name,
            "new_name": safe_new_name
        })

    except Exception as e:
        logger.error(f"Error renaming channel in DB: {e}")
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@app.route('/api/channels/delete', methods=['POST'])
def api_delete_channel():
    """
    Deletes a channel (folder_name) from the database.
    Expects JSON:
    { "name": "channel_name_to_delete" }

    This will delete:
      - All VideoFolder rows matching that folder name
      - Any videos (and their summaries) no longer referenced by any other folder
    """
    session = SessionLocal()

    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"status": "error", "message": "No channel name provided"}), 400

    folder_name = data['name'].strip()
    if not folder_name:
        return jsonify({"status": "error", "message": "Channel name is empty."}), 400

    # 1) Find all VideoFolder rows for this folder_name
    folders_to_delete = session.query(VideoFolder).filter_by(folder_name=folder_name).all()

    if not folders_to_delete:
        return jsonify({"status": "error", "message": "Channel not found."}), 404

    # 2) Collect all video_ids from those folders
    video_ids = [f.video_id for f in folders_to_delete]

    # 3) Delete the VideoFolder rows
    for f in folders_to_delete:
        session.delete(f)

    session.flush()

    # 4) Check each unique video_id to see if it’s still referenced
    unique_video_ids = set(video_ids)
    for vid in unique_video_ids:
        usage_count = session.query(VideoFolder).filter_by(video_id=vid).count()
        if usage_count == 0:
            # If this video is no longer referenced, delete it and its summaries
            session.query(Summary).filter_by(video_id=vid).delete()
            session.query(Video).filter_by(video_id=vid).delete()

    session.commit()

    return jsonify({"status": "ok", "deleted_folder": folder_name})


@app.route('/api/all-tasks', methods=['GET'])
def api_all_tasks():
    """
    Return a list of all tasks (downloads and summaries) in a single JSON array.
    """
    all_tasks = []

    # For download tasks
    for task_id, stat in download_statuses.items():
        all_tasks.append({
            "task_id": task_id,
            "type": "download",
            "status": stat["status"],
            "processed": stat["processed"],
            "total": stat["total"],
            "errors": stat["errors"]
        })

    # For summarize tasks
    for task_id, stat in summarize_statuses.items():
        all_tasks.append({
            "task_id": task_id,
            "type": "summarize",
            "status": stat["status"],
            "processed": stat["processed"],
            "total": stat["total"],
            "errors": stat["errors"]
        })

    return jsonify(all_tasks)


@app.route('/api/sync-files', methods=['POST'])
def api_sync_files():
    """
    Trigger a file-to-DB sync. Spawns a background thread so we don't block.
    Returns immediate JSON indicating the sync has started.
    
    Example POST body: {}
    (You could allow optional parameters if needed)
    """
    # You could add logic to prevent multiple concurrent syncs, 
    # or accept "force" parameters, etc. For simplicity, we just spawn a new thread each time.

    def sync_thread():
        # Call your sync logic
        run_sync()  # This function updates the sync_jobs table with 'in_progress' -> 'completed' or 'failed'.

    thread = threading.Thread(target=sync_thread, daemon=True)
    thread.start()

    return jsonify({"status": "initiated"}), 202


# Example route to trigger embedding
@app.route("/api/embed-db", methods=["POST"])
def api_embed_db():
    """
    Trigger the pgai vectorizer creation or update in a background thread.
    """
    def embedding_thread():
        run_embedding_sync()

    thread = threading.Thread(target=embedding_thread, daemon=True)
    thread.start()

    return jsonify({"status": "initiated"}), 202

@app.route('/api/sync-jobs/current', methods=['GET'])
def api_sync_jobs_current():
    """
    Returns the most recent sync job from the 'sync_jobs' table
    or a message if none exist.
    """
    # For production, you might want a session manager function or a shared session.
    DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
    engine = create_engine(DB_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Grab the most recent job (assuming auto-increment 'id', descending)
    job = session.query(SyncJob).order_by(SyncJob.id.desc()).first()
    if not job:
        session.close()
        return jsonify({"status": "no_jobs", "message": "No sync jobs found."}), 200

    # Convert to JSON
    job_data = {
        "id": job.id,
        "start_time": job.start_time.isoformat() if job.start_time else None,
        "end_time": job.end_time.isoformat() if job.end_time else None,
        "status": job.status,
        "message": job.message,
    }
    session.close()
    return jsonify(job_data), 200



@app.route('/summaries/<channel_id>/<method>/<video_id>')
def view_summary(channel_id, method, video_id):
    """
    Displays the summary (if openai/ollama) + original transcript in summary.html.
    The transcript is shown in two collapsible sections:
      1) With timestamps
      2) Without timestamps
    If method='transcript', we skip the .md file loading.
    """
    # 1. Load the transcript JSON
    transcript_file = os.path.join(DATA_DIR, channel_id, "transcripts", f"{video_id}.json")
    if not os.path.exists(transcript_file):
        abort(404, f"Transcript file not found for video {video_id}")

    with open(transcript_file, "r", encoding="utf-8") as f:
        vid_data = json.load(f)
    # vid_data contains "title", "upload_date", "transcript" (list of items)

    # Build human-readable transcript variants
    transcripts = vid_data.get("transcript", [])
    transcript_text_with_timestamps = []
    transcript_text_no_timestamps = []

    for item in transcripts:
        start = item.get("start", 0)
        dur = item.get("duration", 0)
        text = item.get("text", "")
        # with timestamps
        line_with_ts = f"[{start:.2f}s - {dur:.2f}s] {text}"
        transcript_text_with_timestamps.append(line_with_ts)
        # without timestamps
        transcript_text_no_timestamps.append(text)

    # Join them
    transcript_with_ts_joined = "\n".join(transcript_text_with_timestamps)
    transcript_no_ts_joined = "\n".join(transcript_text_no_timestamps)

    # 2. If method is "openai" or "ollama", load the summary file
    summary_html = None
    if method in ("openai", "ollama"):
        summary_file = os.path.join(DATA_DIR, channel_id, f"summaries_{method}", f"{video_id}.md")
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as sf:
                md_text = sf.read()
            summary_html = markdown.markdown(md_text)
        else:
            summary_html = "<em>No summary found for this method.</em>"
    elif method == "transcript":
        # no summary needed
        summary_html = None
    else:
        abort(400, "Invalid method. Must be 'openai', 'ollama', or 'transcript'")

    return render_template(
        "summary.html",
        channel_id=channel_id,
        video_id=video_id,
        method=method,
        title=vid_data.get("title", "Untitled"),
        upload_date=vid_data.get("upload_date", "UnknownDate"),
        summary_html=summary_html,
        transcript_with_ts=transcript_with_ts_joined,
        transcript_no_ts=transcript_no_ts_joined
    )





#############################################################################
# Now define your new routes for embedded-channels, chat-channel, chat-video
#############################################################################


@app.route("/chat-channel/<channel_name>", methods=["GET"])
def chat_channel_page(channel_name):
    """
    Render a page to chat with the entire channel.
    Also show all videos that belong to this channel.
    """
    session = SessionLocal()
    try:
        # SELECT v.* 
        # FROM videos v
        # JOIN video_folders vf ON v.video_id = vf.video_id
        # WHERE vf.folder_name = :channel_name
        videos = (
            session.query(Video)
            .join(VideoFolder, Video.video_id == VideoFolder.video_id)
            .filter(VideoFolder.folder_name == channel_name)
            .all()
        )
        video_data = []
        for vid in videos:
            summaries_by_type = {}
            for s in vid.summaries:
                stype = s.summary_type.lower()  # "ollama", "openai", etc.
                if stype not in summaries_by_type:
                    summaries_by_type[stype] = []
                summaries_by_type[stype].append(s)

            video_data.append({
                "video": vid,
                "summaries_by_type": summaries_by_type
            })        
    finally:
        session.close()

    # We'll pass `videos` to the template so we can display them
    return render_template("channel_chat.html", channel_name=channel_name, video_data=video_data)

@app.route("/api/chat-channel/<channel_name>", methods=["POST"])
def api_chat_channel(channel_name):
    """
    AJAX endpoint to handle chat queries for a given channel.
    1) Embed the user query with Ollama.
    2) Do a top-K similarity search.
    3) Generate a final answer with Ollama.
    """
    data = request.json or {}
    user_query = data.get("query", "").strip()
    if not user_query:
        return jsonify({"answer": "No query provided."}), 400

    logger.info(f"Chat-channel query for channel={channel_name}, user_query='{user_query}'")

    session = SessionLocal()
    try:
        # 1) EMBED USER QUERY
        # Must match the function signature: ollama_embed(model text, input_text text, host text, ...)
        sql_embed = text("""
            SELECT ai.ollama_embed(
                'nomic-embed-text',
                :query_text,
            ) AS user_query_emb
        """)

        user_query_emb = session.execute(
            sql_embed,
            {
                "query_text": user_query,
                "ollama_url": OLLAMA_URL  # e.g. "http://192.168.50.4:11434"
            }
        ).scalar()

        if not user_query_emb:
            return jsonify({"answer": "Failed to get embedding for user query."}), 500

        # 2) TOP-K SIMILARITY SEARCH
        sql_top_chunks = text("""
            SELECT 
                ve.chunk,
                (ve.chunk_embedding <=> :q_emb) AS distance
            FROM videos_embedding ve
            JOIN video_folders vf ON ve.video_id = vf.video_id
            WHERE vf.folder_name = :chan
            ORDER BY ve.chunk_embedding <=> :q_emb
            LIMIT 3
        """)

        chunk_rows = session.execute(
            sql_top_chunks,
            {"q_emb": user_query_emb, "chan": channel_name}
        ).fetchall()

        context_pieces = []
        for row in chunk_rows:
            chunk_text = row[0]
            distance = row[1]
            context_pieces.append(f"Chunk (distance={distance:.4f}): {chunk_text}")

        context_for_generation = "\n\n".join(context_pieces)
        if not context_for_generation:
            context_for_generation = "No relevant chunks found."

        # 3) GENERATE THE FINAL ANSWER
        # Matching signature: ollama_generate(model text, prompt text, host text, ...)
        sql_generate = text("""
            SELECT ai.ollama_generate(
                'llama3.2',
                :prompt,
                :ollama_url
            ) AS answer
        """)

        prompt_str = f"""
Answer the user's query based on the context below.

Context:
{context_for_generation}

User Query:
{user_query}

Please provide a concise answer:
"""

        final_answer = session.execute(
            sql_generate,
            {
                "prompt": prompt_str,
                "ollama_url": OLLAMA_URL
            }
        ).scalar()

        if not final_answer:
            final_answer = "No answer was returned by the model."

    except Exception as e:
        logger.exception("Error during chat-channel flow:")
        return jsonify({"answer": f"Error: {str(e)}"}), 500
    finally:
        session.close()

    return jsonify({"answer": final_answer})
@app.route("/chat-video/<video_id>", methods=["GET"])
def chat_video_page(video_id):
    """
    Renders a page that allows chatting with a single video's content.
    We'll also fetch all the channels (folder_name) this video belongs to.
    And display its 'video_name' (which is the 'title' in your model).
    """
    session = SessionLocal()
    try:
        # Fetch the specific video
        video = session.query(Video).filter_by(video_id=video_id).first()

        if not video:
            return f"Video with id '{video_id}' not found.", 404

        video_name = video.title
        video_transcript = video.transcript_no_ts
        folder_list = [vf.folder_name for vf in video.folders]

        summaries_by_type = {}
        for s in video.summaries:
            stype = s.summary_type.lower()  # e.g. "openai", "ollama"
            if stype not in summaries_by_type:
                summaries_by_type[stype] = []
            summaries_by_type[stype].append(s)
            s.summary_text = markdown.markdown(s.summary_text)

    finally:
        session.close()

    # Pass this info to the template:
    return render_template(
        "video_chat.html",
        video_id=video_id,
        video_name=video_name,
        video_transcript=video_transcript,
        folder_list=folder_list,
        summaries_by_type=summaries_by_type
    )


@app.route("/api/chat-video/<video_id>", methods=["POST"])
def api_chat_video(video_id):
    """
    AJAX endpoint for chatting with a single video's content.
    """
    data = request.json or {}
    user_query = data.get("query", "")
    logger.info(f"Chat-video query for video_id={video_id}, user_query={user_query}")

    # -- PSEUDO CODE FOR VIDEO SIMILARITY SEARCH & GENERATION (mocked) --
    # user_query_emb = SELECT ollama_embed(...)
    # relevant_chunks = SELECT chunk FROM videos_embedding 
    #   WHERE video_id=:video_id 
    #   ORDER BY chunk_embedding <=> user_query_emb
    # final_answer = SELECT ollama_generate(...)
    # --------------------------------------------------------

    final_answer = f"Mock response about video_id='{video_id}', query='{user_query}'"
    return jsonify({"answer": final_answer})



@app.route("/view-summary/<int:summary_id>", methods=["GET"])
def view_summary_from_db(summary_id):
    """
    Fetches a summary by ID and displays it in a template.
    """
    session = SessionLocal()
    try:
        summary_obj = session.query(Summary).get(summary_id)
        if not summary_obj:
            return f"Summary with ID {summary_id} not found.", 404
        else:
            summary_obj.summary_text = markdown.markdown(summary_obj.summary_text)

        # We'll pass the entire object to the template
    finally:
        session.close()

    return render_template("summary_view.html", summary=summary_obj)


if __name__ == '__main__':
    # For local dev
    app.run(debug=True, host='0.0.0.0', port=5000)