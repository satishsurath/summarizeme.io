# app.py
import os
import json
import threading
import logging
from flask import Flask, request, jsonify, render_template, abort
import markdown
import re # used for renaming the channel folder 
from dotenv import load_dotenv
import psycopg2

from datetime import datetime
from youtube_utils import download_channel_transcripts, list_downloaded_videos
from summarizer_v2 import chunk_transcript, build_prompts_for_chunk, ollama_generate_chunk

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text

# If you store your models and sync code in separate modules:
from db.models import Base, Video, VideoFolder, SummariesV2



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
summarize_v2_statuses = {}


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
            video_data.append({
                "video": vid
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


@app.route('/api/videos/<channel_name>', methods=['GET'])
def api_get_videos(channel_name):
    """
    List the videos for a given channel from the database,
    plus any SummariesV2 entries that exist for each video.
    Applies pagination, sorting, and a title filter.

    Query params:
      - page (int)
      - page_size (int)
      - sort_by (str) => "title" or "date"
      - filter (str) => partial match on title
    """
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 5))  # default 5 if not provided
    sort_by = request.args.get('sort_by', 'title')  # or 'date'
    filter_str = request.args.get('filter', '').strip().lower()

    session = SessionLocal()
    try:
        # 1) Query the videos for this channel
        query = (
            session.query(Video)
            .join(VideoFolder, Video.video_id == VideoFolder.video_id)
            .filter(VideoFolder.folder_name == channel_name)
        )
        
        # 2) Apply optional title filter
        if filter_str:
            # We do a simple case-insensitive "like" matching on Video.title
            query = query.filter(Video.title.ilike(f"%{filter_str}%"))

        # 3) Sorting
        if sort_by == 'title':
            query = query.order_by(Video.title.asc())
        elif sort_by == 'date':
            # If you want newest first, do desc. Or if you want oldest first, asc.
            query = query.order_by(Video.upload_date.desc())

        # 4) Pagination
        total = query.count()
        offset = (page - 1) * page_size
        video_rows = query.offset(offset).limit(page_size).all()

        # 5) Build the JSON response
        videos_list = []
        for vid in video_rows:
            # Retrieve all SummariesV2 for this video
            summaries_v2_data = []
            for s in vid.summaries_v2:
                summaries_v2_data.append({
                    "id": s.id,
                    "model_name": s.model_name,
                    "date_generated": s.date_generated.isoformat() if s.date_generated else None,
                    # If you want, you could include excerpts from s.concise_summary, etc.
                })

            videos_list.append({
                "video_id": vid.video_id,
                "title": vid.title or "Untitled",
                "upload_date": vid.upload_date or "UnknownDate",
                # Now we store the entire set of v2 summaries for the front-end to handle
                "summaries_v2": summaries_v2_data
            })

        return jsonify({
            "total": total,
            "page": page,
            "page_size": page_size,
            "videos": videos_list
        })

    finally:
        session.close()

#################################################
####### New routes for summarizing videos #######
#################################################

@app.route("/api/summarize_v2", methods=["POST"])
def api_summarize_v2():
    """
    Generate a "v2" summary for multiple videos (SummariesV2).
    - If the channel_id folder association doesn't exist, create it
    - If a SummariesV2 row (video_id, summary_type="ollama_v2", model_name=...) already exists, skip
    - Enhanced chunking by sentences, fallback to word-splitting
    - Enhanced prompt instructions
    """
    data = request.get_json() or {}
    channel_name = data.get("channel_name", "").strip()
    video_ids = data.get("video_ids", [])
    model_name = data.get("model", "phi4")

    if not channel_name or not video_ids:
        return jsonify({"status": "error", "message": "channel_id or video_ids missing"}), 400

    task_id = f"summ_v2_{len(summarize_v2_statuses)+1}"
    summarize_v2_statuses[task_id] = {
        "status": "in_progress",
        "processed": 0,
        "total": len(video_ids),
        "errors": []
    }

    def run_summarize_v2():
        session = SessionLocal()
        processed_count = 0
        try:
            for vid in video_ids:
                # 1) Ensure folder association
                existing_folder = session.query(VideoFolder).filter_by(
                    folder_name=channel_name, 
                    video_id=vid
                ).first()
                if not existing_folder:
                    folder_assoc = VideoFolder(
                        folder_name=channel_name,
                        video_id=vid,
                        last_modified=datetime.utcnow()
                    )
                    session.add(folder_assoc)
                    session.commit()

                # 2) Skip if SummariesV2 row exists
                existing_summary = (
                    session.query(SummariesV2)
                    .filter_by(
                        video_id=vid, 
                        model_name=model_name
                    )
                    .first()
                )
                if existing_summary:
                    logger.info(f"[SummariesV2] Skipping {vid}, summary already exists for model='{model_name}'.")
                    processed_count += 1
                    summarize_v2_statuses[task_id]["processed"] = processed_count
                    continue

                # 3) Fetch video
                video_obj = session.query(Video).filter_by(video_id=vid).first()
                if not video_obj:
                    msg = f"Video {vid} not found in DB."
                    logger.error(msg)
                    summarize_v2_statuses[task_id]["errors"].append(msg)
                    processed_count += 1
                    summarize_v2_statuses[task_id]["processed"] = processed_count
                    continue

                # 4) Get transcript
                transcript = video_obj.transcript_no_ts or ""
                tokens_no_ts = video_obj.tokens_no_ts or 0
                if tokens_no_ts <= 0:
                    # fallback: naive word count
                    tokens_no_ts = len(transcript.split())

                # 5) Enhanced chunking
                if tokens_no_ts <= 4000:
                    chunked_texts = [transcript]
                else:
                    chunked_texts = chunk_transcript(transcript, max_words_per_chunk=4000)

                # 6) Summaries accumulators
                all_concise = []
                all_topics = []
                all_takeaways = []
                all_comprehensive = []

                # 7) For each chunk, run the four prompts
                for chunk_str in chunked_texts:
                    prompts = build_prompts_for_chunk(chunk_str)

                    c_text = ollama_generate_chunk(model_name, prompts["concise"])
                    kt_text = ollama_generate_chunk(model_name, prompts["key_topics"])
                    tk_text = ollama_generate_chunk(model_name, prompts["takeaways"])
                    cp_text = ollama_generate_chunk(model_name, prompts["comprehensive"])

                    all_concise.append(c_text)
                    all_topics.append(kt_text)
                    all_takeaways.append(tk_text)
                    all_comprehensive.append(cp_text)

                # 8) Merge partial results
                final_concise = "\n".join(all_concise).strip()
                final_topics = "\n".join(all_topics).strip()
                final_takeaways = "\n".join(all_takeaways).strip()
                final_comprehensive = "\n".join(all_comprehensive).strip()

                # 9) Insert SummariesV2 row
                new_summary = SummariesV2(
                    video_id=vid,
                    video_title=video_obj.title,
                    model_name=model_name,
                    date_generated=datetime.utcnow(),
                    concise_summary=final_concise,
                    key_topics=final_topics,
                    important_takeaways=final_takeaways,
                    comprehensive_notes=final_comprehensive
                )
                session.add(new_summary)
                session.commit()

                logger.info(f"[SummariesV2] Inserted for video={vid}, model={model_name}")
                processed_count += 1
                summarize_v2_statuses[task_id]["processed"] = processed_count

            summarize_v2_statuses[task_id]["status"] = "completed"
        except Exception as e:
            logger.error(f"[SummariesV2] Error: {e}")
            summarize_v2_statuses[task_id]["status"] = "failed"
            summarize_v2_statuses[task_id]["errors"].append(str(e))
        finally:
            session.close()

    # spawn background thread
    thread = threading.Thread(target=run_summarize_v2, daemon=True)
    thread.start()

    return jsonify({"status": "initiated", "task_id": task_id})

@app.route("/api/summarize_v2/status/<task_id>", methods=["GET"])
def api_summarize_v2_status(task_id):
    """
    Returns progress for the SummariesV2 generation task.
    """
    status = summarize_v2_statuses.get(task_id)
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
        # Update only the folder_name field; original_playlist_id remains unchanged.
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

@app.route('/api/channels/refresh', methods=["POST"])
def api_refresh_channel():
    """
    Refresh the channel using the immutable original_playlist_id.
    Expects JSON: { "channel_name": "HumanFriendlyChannelName" }
    """
    data = request.get_json() or {}
    channel_name_input = data.get("channel_name", "").strip()
    if not channel_name_input:
        return jsonify({"status": "error", "message": "Channel name missing"}), 400

    session = SessionLocal()
    try:
        # Look up the channel by matching either the human-friendly name or the original_playlist_id.
        folder_obj = session.query(VideoFolder).filter(
            (VideoFolder.folder_name == channel_name_input) |
            (VideoFolder.original_playlist_id == channel_name_input)
        ).first()
        # debug statement
        print(f"folder_obj: {folder_obj}")
        if not folder_obj:
            # debug statement
            print(f"Channel not found")
            return jsonify({"status": "error", "message": "Channel not found"}), 404

        # Preserve the human-friendly name.
        human_playlist_name = folder_obj.folder_name
        # Use the immutable original playlist ID (fallback to the human-friendly name if needed).
        original_playlist_id = folder_obj.original_playlist_id or human_playlist_name

        # Build the YouTube playlist URL using the original playlist id.
        channel_url = f"https://www.youtube.com/playlist?list={original_playlist_id}"

        # Generate a task ID using the human-friendly name.
        task_id = f"refresh_{human_playlist_name}_{int(datetime.utcnow().timestamp())}"
        download_statuses[task_id] = {
            "status": "in_progress",
            "processed": 0,
            "total": 0,
            "errors": []
        }

        def run_refresh():
            try:
                # This function (download_channel_transcripts) uses the updated logic:
                # It checks for an existing folder association (using original_playlist_id)
                # so that videos that already exist are not re-added.
                download_channel_transcripts(channel_url, download_statuses[task_id])
                download_statuses[task_id]["status"] = "completed"
            except Exception as e:
                logger.error(f"Error in channel refresh: {e}")
                download_statuses[task_id]["status"] = "failed"
                download_statuses[task_id]["errors"].append(str(e))

        thread = threading.Thread(target=run_refresh, daemon=True)
        thread.start()

        return jsonify({"status": "initiated", "task_id": task_id})
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
            session.query(SummariesV2).filter_by(video_id=vid).delete()
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
    for task_id, stat in summarize_v2_statuses.items():
        all_tasks.append({
            "task_id": task_id,
            "type": "summarize",
            "status": stat["status"],
            "processed": stat["processed"],
            "total": stat["total"],
            "errors": stat["errors"]
        })

    return jsonify(all_tasks)


@app.route("/api/ollama/models", methods=["GET"])
def api_ollama_models():
    """
    Returns a JSON list of Ollama models from your remote instance.
    Example JSON: { "models": [ { "name": "phi4" }, { "name": "llama2" } ] }
    """
    # e.g., using the 'requests' library or your 'ollama' python client
    import requests

    ollama_host = os.getenv("REMOTE_OLLAMA_HOST", "localhost")
    url = f"http://{ollama_host}:11434/v1/models"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()  # likely { "models": [ { "name": "..." }, ... ] }
        return jsonify(data)
    except Exception as e:
        logger.error(f"Failed to list Ollama models: {e}")
        return jsonify({"models": []}), 500


@app.route("/summaries_v2/<int:summary_id>", methods=["GET"])
def view_summary_v2(summary_id):
    """
    Fetch SummariesV2 by ID, join its Video, 
    convert the 4 summary fields from MD to HTML, 
    and render a 'summary_v2.html' template.
    """
    session = SessionLocal()
    try:
        summary_obj = session.query(SummariesV2).get(summary_id)
        if not summary_obj:
            return f"SummariesV2 with ID {summary_id} not found.", 404
        
        video = summary_obj.video  # Because SummariesV2.video is the relationship

        # Convert each of the 4 fields from markdown => HTML
        concise_html = markdown.markdown(summary_obj.concise_summary or "")
        topics_html = markdown.markdown(summary_obj.key_topics or "")
        takeaways_html = markdown.markdown(summary_obj.important_takeaways or "")
        notes_html = markdown.markdown(summary_obj.comprehensive_notes or "")

        return render_template(
            "summary_v2.html",
            summary=summary_obj,    # We might still pass the raw text data for reference
            video=video,
            concise_html=concise_html,
            topics_html=topics_html,
            takeaways_html=takeaways_html,
            notes_html=notes_html
        )
    finally:
        session.close()


@app.route("/transcript/<video_id>")
def view_transcript_v2(video_id):
    """
    Fetch Video Transcript by ID, 
    and render a 'summary_v2.html' template.
    """
    session = SessionLocal()
    try:
        video_obj = session.query(Video).get(video_id)
        if not video_obj:
            return f"Video with ID {video_id} not found.", 404
        
        video = video_obj  # Because SummariesV2.video is the relationship

        return render_template(
            "transcript_v2.html",
            video=video
        )
    finally:
        session.close()


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
            video_data.append({
                "video": vid
            })        
    finally:
        session.close()

    # We'll pass `videos` to the template so we can display them
    return render_template("channel_chat.html", channel_name=channel_name, video_data=video_data)

@app.route("/api/chat-channel/<channel_name>", methods=["POST"])
def api_chat_channel(channel_name):
    """
    AJAX endpoint to handle chat queries for a given channel.
    Uses a 'data_type' param to select which embeddings to query,
    and 'model_name' to dynamically pick which Ollama model to use.
    """
    data = request.json or {}
    user_query = data.get("query", "").strip()
    data_type = data.get("data_type", "comprehensive_notes")
    model_name = data.get("model_name", "phi4:latest")  # default fallback

    # temporary work around - if model_name = "deepseek-r1:32b" change it to "gemma2:27b"
    if model_name == "deepseek-r1:32b":
        model_name = "gemma2:27b"

    if not user_query:
        return jsonify({"answer": "No query provided."}), 400

    logger.info(f"Chat-channel query for channel={channel_name}, "
                f"user_query='{user_query}', data_type='{data_type}', model='{model_name}'")

    # 1) Map data_type to the relevant embeddings view
    EMBEDDINGS_VIEW_MAP = {
        "comprehensive_notes": "public.summaries_v2_comprehensive_notes_embedding",
        "concise_summary":     "public.summaries_v2_concise_summary_embedding",
        "key_topics":          "public.summaries_v2_key_topics_embedding",
        "important_takeaways": "public.summaries_v2_important_takeaways_embedding",
        "transcript":          "public.videos_embedding"
    }
    selected_view = EMBEDDINGS_VIEW_MAP.get(data_type, EMBEDDINGS_VIEW_MAP["comprehensive_notes"])

    session = SessionLocal()
    try:
        # 2) Embed the user query with the chosen model
        sql_embed = text("""
            SELECT ai.ollama_embed(
                :model_name,
                :query_text,
                :ollama_url
            ) AS user_query_emb
        """)

        user_query_emb = session.execute(sql_embed, {
            "model_name": "nomic-embed-text:latest", 
            "query_text": user_query,
            "ollama_url": OLLAMA_URL
        }).scalar()

        if not user_query_emb:
            return jsonify({"answer": "Failed to get embedding for user query."}), 500

        # 3) Retrieve relevant chunks from the selected view
        sql_top_chunks = text(f"""
            SELECT 
                ev.chunk,
                ev.video_id,
                v.title AS video_title,
                1 - (ev.embedding <=> :q_emb) AS similarity
            FROM {selected_view} ev
            JOIN video_folders vf ON ev.video_id = vf.video_id
            JOIN videos v        ON ev.video_id = v.video_id
            WHERE vf.folder_name = :chan
            ORDER BY similarity DESC
            LIMIT 5
        """)

        chunk_rows = session.execute(sql_top_chunks, {
            "q_emb": user_query_emb,
            "chan": channel_name
        }).fetchall()

        if not chunk_rows:
            final_answer = "No relevant content found for this channel and data type."
            used_videos_html = ""
        else:
            context_pieces = []
            unique_videos = {}

            for row in chunk_rows:
                chunk_text = row[0]
                chunk_vid_id = row[1]
                chunk_vid_title = row[2]
                similarity = row[3]

                context_pieces.append(f"Chunk (similarity={similarity:.4f}): {chunk_text}")
                unique_videos[chunk_vid_id] = chunk_vid_title

            context_for_generation = "\n\n".join(context_pieces)

            # 4) Generate final answer (embedding is done; now we do text generation)
            sql_generate = text("""
                SELECT ai.ollama_generate(
                    :model_name,
                    :prompt,
                    :ollama_url
                ) AS answer
            """)

            prompt_str = f"""
Context:
{context_for_generation}

User Query:
{user_query}

Please provide a concise answer:
"""

            result_json = session.execute(sql_generate, {
                "model_name": model_name,
                "prompt": prompt_str,
                "ollama_url": OLLAMA_URL
            }).scalar()

            if not result_json:
                final_answer = "No answer was returned by the model."
            else:
                final_answer = result_json.get("response", "[No response in JSON]")

            # same logic to append the used_videos_html
            if unique_videos:
                used_videos_html = "<h4>Videos used in Context:</h4>\n<ul>\n"
                for vid_id, vid_title in unique_videos.items():
                    used_videos_html += f"""
<li>
    <a href="https://www.youtube.com/watch?v={vid_id}" target="_blank">
        <svg style="fill:#333; height:1em; width:1em;" version="1.1"
             xmlns="http://www.w3.org/2000/svg"
             xmlns:xlink="http://www.w3.org/1999/xlink"
             viewBox="0 0 48 48" xml:space="preserve">
            <use href="#icon-summarizeYouTube" xlink:href="#icon-summarizeYouTube"></use>
        </svg>
    </a>
    &nbsp;
    <a href="/chat-video/{vid_id}">
        <svg xmlns="http://www.w3.org/2000/svg" height="24px"
             viewBox="0 -960 960 960" width="24px">
            <path d="M240-400h320v-80H240v80Zm0-120h480v-80H240v80Zm0-120h480v-80H240v80ZM80-80v-720q0-33 23.5-56.5T160-880h640q33 0 56.5 23.5T880-800v480q0 33-23.5 56.5T800-240H240L80-80Zm126-240h594v-480H160v525l46-45Zm-46 0v-480 480Z"/>
        </svg>
    </a>
    {vid_title}
</li>
"""
                used_videos_html += "</ul>\n"
            else:
                used_videos_html = ""

    except Exception as e:
        logger.exception("Error during chat-channel flow:")
        return jsonify({"answer": f"Error: {str(e)}"}), 500
    finally:
        session.close()

    # Convert final_answer from markdown to HTML, then append the used_videos_html
    final_answer_html = markdown.markdown(final_answer)
    if used_videos_html:
        final_answer_html += used_videos_html

    return jsonify({"answer": final_answer_html})

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
    finally:
        session.close()

    # Pass this info to the template:
    return render_template(
        "video_chat.html",
        video_id=video_id,
        video_name=video_name,
        video_transcript=video_transcript,
        folder_list=folder_list
    )


@app.route("/api/chat-video/<video_id>", methods=["POST"])
def api_chat_video(video_id):
    """
    AJAX endpoint for chatting with a single video's content.
    """
    data = request.json or {}
    user_query = data.get("query", "")
    data_type = data.get("data_type", "comprehensive_notes")  # default fallback

    logger.info(f"Chat-video query for video_id={video_id}, user_query={user_query}, data_type={data_type}")

    # 1) Create a small lookup dict that maps data_type to the relevant embeddings store
    #    e.g. the "destination =>" string you used in create_vectorizer
    #    or your actual table/view names for each embedding.
    #    Example names are placeholders—adjust to match your actual vectorizer output.
    EMBEDDINGS_TABLE_MAP = {
        "comprehensive_notes": "public.summaries_v2_comprehensive_notes_embedding",
        "concise_summary":     "public.summaries_v2_concise_summary_embedding",
        "key_topics":          "public.summaries_v2_key_topics_embedding",
        "important_takeaways": "public.summaries_v2_important_takeaways_embedding",
        "transcript":          "public.videos_embedding"
    }

    # If the user chose something not in the map, default to comprehensive_notes
    selected_table = EMBEDDINGS_TABLE_MAP.get(data_type, EMBEDDINGS_TABLE_MAP["comprehensive_notes"])

    # 2) Connect to your DB
    conn = psycopg2.connect(DB_URL)  # or however you do this
    try:
        cur = conn.cursor()

        # 3) Embed the user_query
        #    We'll do something like:
        #    SELECT ai.ollama_embed('nomic-embed-text', user_query, base_url)
        embed_sql = """
            SELECT ai.ollama_embed('nomic-embed-text', %s, %s)
        """
        cur.execute(embed_sql, (user_query, OLLAMA_URL))
        user_query_embedding = cur.fetchone()[0]  # Store the embedding array

        # 4) SELECT relevant chunks from the chosen embeddings table
        #    If you need to filter by video_id, ensure you stored it as metadata.
        #    Example if your chunking stored 'video_id' in a column named 'video_id':
        #    SELECT chunk from selected_table WHERE video_id=%s ORDER BY (embedding <=> user_query_embedding) ASC
        #    or something similar. 
        #    Also note 1-(emb <=> query) is "similarity" if you want descending order. 
        #    Alternatively you can do embedding distance ascending order.
        select_chunks_sql = f"""
            SELECT chunk,
                   1 - (embedding <=> %s) AS similarity
              FROM {selected_table}
             WHERE video_id = %s
             ORDER BY similarity DESC
             LIMIT 5
        """
        cur.execute(select_chunks_sql, (user_query_embedding, video_id))
        rows = cur.fetchall()

        # 5) Concatenate the top relevant chunks
        context = "\n\n".join([f"Chunk: {r[0]}" for r in rows])

        # 6) Generate a final answer with ai.ollama_generate or ai.ollama_chat_complete.
        #    Simple example with ai.ollama_generate. 
        #    We wrap the context and user query into a single prompt.
        generate_sql = """
            SELECT ai.ollama_generate(
                'gemma2:27b',              -- or your model name
                %s,                        -- prompt
                %s                         -- base_url
            );
        """
        prompt_text = f"Query: {user_query}\nContext:\n{context}"
        cur.execute(generate_sql, (prompt_text, OLLAMA_URL))
        result_json = cur.fetchone()[0]  # e.g. { "response": "...", "done": True, ... }

        final_answer = result_json.get("response", "[No response in JSON]")

        cur.close()
    except Exception as e:
        logger.exception("Error while handling chat-video")
        final_answer = f"Error: {e}"
    finally:
        conn.close()

    # Convert final_answer from markdown to HTML
    final_answer_html = markdown.markdown(final_answer)

    return jsonify({"answer": final_answer_html})



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