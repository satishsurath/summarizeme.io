import os
import json
import openai

openai.api_key = os.getenv("OPENAI_API_KEY", "")

DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR is None:
    DATA_DIR = "data/channels"  # Base directory for channel data

def summarize_transcript_openai(channel_id: str, video_id: str):
    """
    Summarize a transcript using OpenAI ChatGPT 4o model.
    Output is saved in data/channels/<channel_id>/summaries_openai/<video_id>.md
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

    # 3. Create prompt
    prompt = f"""
You are a helpful assistant. 
This is a transcript from a YouTube video titled "{title}", uploaded on {upload_date}.

Please provide a markdown summary with the following sections:
1. A concise summary of the entire content
2. Key topics or themes covered
3. Important takeaways or lessons
4. Any notable timestamps or sections worth revisiting
5. Comprehensive notes covering the entire transcript in an easy-to-read manner

Here is the transcript:

{transcript_text}
"""

    # 4. Call OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16384,
        temperature=0.7
    )

    summary_markdown = response.choices[0].message.content.strip()
    print(summary_markdown)

    # 5. Save to file
    summary_folder = os.path.join(DATA_DIR, channel_id, "summaries_openai")
    os.makedirs(summary_folder, exist_ok=True)
    summary_path = os.path.join(summary_folder, f"{video_id}.md")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_markdown)