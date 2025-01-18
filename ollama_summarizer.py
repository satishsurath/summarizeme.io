# ollama_summarizer.py
import os
import json
import ollama
from dotenv import load_dotenv

#Read the env file
load_dotenv()
ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
print(f"ollama_host: {ollama_host}")

client = ollama.Client(
  host='http://'+ ollama_host+':11434')



DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR is None:
    DATA_DIR = "data/channels"  # Base directory for channel data



def summarize_transcript_ollama(
    channel_id: str,
    video_id: str,
    model: str = "llama3.2"
):
    """
    Summarize a transcript using a locally running Ollama instance and the specified model.
    Output is saved in data/channels/<channel_id>/summaries_ollama/<video_id>.md
    """

    # 1. Locate transcript file
    transcript_file = os.path.join(DATA_DIR, channel_id, "transcripts", f"{video_id}.json")
    if not os.path.exists(transcript_file):
        raise FileNotFoundError(f"Transcript file not found for video {video_id}")

    # 2. Read transcript
    with open(transcript_file, "r", encoding="utf-8") as f:
        video_data = json.load(f)
    transcript_entries = video_data.get("transcript", [])
    transcript_text = "\n".join([e["text"] for e in transcript_entries])
    title = video_data.get("title", "Untitled Video")
    upload_date = video_data.get("upload_date", "UnknownDate")

    # 3. Prepare prompt
    prompt = f"""
Please provide a markdown summary for this YouTube video titled "{title}", uploaded on {upload_date}.
Include:
1. Concise summary
2. Key topics
3. Important takeaways
5. Comprehensive notes

Transcript:
{transcript_text}
"""

    # 4. Ollama call
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )

    summary_text = response.get("message", {}).get("content", "").strip()

    # 5. Save to file
    summary_folder = os.path.join(DATA_DIR, channel_id, "summaries_ollama")
    os.makedirs(summary_folder, exist_ok=True)
    summary_path = os.path.join(summary_folder, f"{video_id}.md")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)