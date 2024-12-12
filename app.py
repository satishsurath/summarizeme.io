import os
import re
import logging
import subprocess
import json
from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', template_folder='templates')

# Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["10 per minute"]
)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/history', methods=['GET'])
def history_page():
    return render_template('history.html')

@app.route('/api/transcript', methods=['POST'])
@limiter.limit("10 per minute")
def get_transcript():
    data = request.get_json()
    if not data or 'youtube_url' not in data:
        return jsonify({"status": "error", "message": "youtube_url required"}), 400

    youtube_url = data['youtube_url']
    if not is_valid_youtube_url(youtube_url):
        return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({"status": "error", "message": "Could not extract video ID"}), 400

    # Get video metadata using yt-dlp (title, upload date)
    try:
        metadata = get_video_metadata(youtube_url)
        title = metadata.get("title", "Unknown Title")
        upload_date = metadata.get("upload_date", "Unknown Date")
    except Exception as e:
        logger.error(f"Error getting metadata: {e}")
        return jsonify({"status": "error", "message": "Could not retrieve video metadata."}), 500

    # Fetch transcript using YouTubeTranscriptApi
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript_data = None
        try:
            transcript_data = transcript_list.find_transcript(['en']).fetch()
        except:
            # If no English transcript found, pick the first available
            for t in transcript_list:
                transcript_data = t.fetch()
                if transcript_data:
                    break

        if not transcript_data:
            return jsonify({"status": "error", "message": "No transcript available."}), 404

        structured_transcript = [
            {
                "text": item["text"],
                "start": item["start"],
                "duration": item.get("duration", 0)
            } for item in transcript_data
        ]

        return jsonify({
            "status": "success",
            "video_id": video_id,
            "title": title,
            "upload_date": upload_date,
            "transcript": structured_transcript
        })
    except Exception as e:
        logger.error(f"Error retrieving transcript: {e}")
        return jsonify({"status": "error", "message": "Could not retrieve transcript."}), 500

@app.route('/api/analyze', methods=['POST'])
@limiter.limit("10 per minute")
def analyze_transcript():
    data = request.get_json()
    required_fields = ['transcript', 'video_id', 'title', 'upload_date', 'openai_api_key']
    if any(field not in data for field in required_fields):
        return jsonify({"status": "error", "message": "Missing required fields (transcript, video_id, title, upload_date, openai_api_key)"}), 400

    transcript = data['transcript']
    title = data['title']
    upload_date = data['upload_date']
    openai_api_key = data['openai_api_key']

    # Set the provided key for this request
    openai.api_key = openai_api_key

    analysis_type = data.get('analysis_type', 'detailed_summary')
    transcript_text = "\n".join([t['text'] for t in transcript])
    prompt = generate_prompt(title, upload_date, transcript_text, analysis_type)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # Using GPT-4 model
            messages=[{"role": "system", "content": "You are a helpful assistant, skilled in summarizing and structuring video content."},
                      {"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        return jsonify({"status": "success", "analysis_markdown": content})
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return jsonify({"status": "error", "message": "Could not analyze the transcript. Check your OpenAI key."}), 500

def is_valid_youtube_url(url):
    youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+'
    return re.match(youtube_regex, url) is not None

def extract_video_id(url):
    import urllib.parse as up
    u = up.urlparse(url)
    if 'youtube.com' in u.netloc:
        q = up.parse_qs(u.query)
        return q.get('v', [None])[0]
    elif 'youtu.be' in u.netloc:
        return u.path.strip('/')
    return None

def get_video_metadata(url):
    cmd = ["yt-dlp", "--dump-single-json", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"yt-dlp error: {result.stderr}")
        raise Exception("yt-dlp failed")
    data = json.loads(result.stdout)
    return data

def generate_prompt(title, upload_date, transcript_text, analysis_type):
    return (f"The following is a transcript of a YouTube video titled '{title}', uploaded on {upload_date}. "
            f"Please analyze and summarize this video transcript. Provide the following in your response:\n\n"
            f"1. A concise summary of the entire content.\n"
            f"2. Key topics or themes covered in the video.\n"
            f"3. Important takeaways or lessons.\n"
            f"4. Any notable timestamps or sections worth revisiting.\n\n"
            f"Format the output in well-structured Markdown, including headings, bullet points, and emphasis where appropriate.\n\n"
            f"Here is the transcript:\n\n{transcript_text}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
