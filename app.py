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

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Read the env file
load_dotenv()
ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
print(f"ollama_host: {ollama_host}")

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
    return render_template('index.html')


@app.route('/status')
def status_page():
    """
    Basic page to show status progress.
    """
    return render_template('status.html')


@app.route('/videos/<channel_id>')
def videos_page(channel_id):
    """
    Paginated video list for a specific channel.
    The user can sort, filter, and initiate summarization from here.
    """
    return render_template('videos.html', channel_id=channel_id)


@app.route('/api/channel/start', methods=['POST'])
def api_channel_start():
    """
    Start downloading transcripts for the entire channel.
    Expects JSON: { "channel_url": "https://www.youtube.com/..." }
    """
    data = request.get_json()
    if not data or 'channel_url' not in data:
        return jsonify({"status": "error", "message": "No channel_url provided"}), 400

    channel_url = data['channel_url']
    # Generate a unique task ID for tracking 
    task_id = f"dl_{len(download_statuses)+1}"

    download_statuses[task_id] = {
        "status": "in_progress",
        "processed": 0,
        "total": 0,
        "errors": []
    }

    def run_download():
        try:
            download_channel_transcripts(channel_url, download_statuses[task_id])
            download_statuses[task_id]["status"] = "completed"
        except Exception as e:
            logger.error(f"Error in channel download: {e}")
            download_statuses[task_id]["status"] = "failed"
            download_statuses[task_id]["errors"].append(str(e))

    # Background thread for the download
    thread = threading.Thread(target=run_download)
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
                else:
                    summarize_transcript_ollama(channel_id, vid)
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


@app.route('/api/channels', methods=['GET'])
def api_list_channels():
    """
    Lists the already downloaded channels by checking subdirectories in data/channels/.
    Returns JSON array of channel_ids.
    """
    if not os.path.exists(DATA_DIR):
        return jsonify([])

    all_dirs = [
        d for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, d)) and not d.startswith(".")
    ]
    return jsonify(all_dirs)

@app.route('/api/channels/rename', methods=['POST'])
def api_rename_channel():
    """
    Renames a channel folder on disk. Expects JSON:
    { "old_name": "...", "new_name": "..." }
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_name or not new_name:
        return jsonify({"status": "error", "message": "old_name and new_name are required"}), 400

    old_dir = os.path.join(DATA_DIR, old_name)
    if not os.path.exists(old_dir):
        return jsonify({"status": "error", "message": "Old channel directory not found"}), 404

    # Sanitize new_name for Ubuntu (example: only allow alphanumeric, underscores, hyphens, spaces).
    safe_new_name = re.sub(r"[^a-zA-Z0-9_\-\s]", "", new_name)
    if not safe_new_name:
        return jsonify({"status": "error", "message": "Invalid characters in new_name"}), 400

    new_dir = os.path.join(DATA_DIR, safe_new_name)

    # Check if new_name already exists
    if os.path.exists(new_dir):
        return jsonify({"status": "error", "message": "A channel with the new name already exists"}), 400

    try:
        os.rename(old_dir, new_dir)
    except Exception as e:
        logger.error(f"Error renaming channel: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ok", "old_name": old_name, "new_name": safe_new_name})

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


if __name__ == '__main__':
    # For local dev
    app.run(debug=True, host='0.0.0.0', port=5000)