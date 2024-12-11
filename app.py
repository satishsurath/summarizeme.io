import os
import re
import logging
from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pytube import YouTube
import openai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', template_folder='templates')

# Rate Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["10 per minute"]  # Adjust as needed
)

# Load OpenAI API Key from environment
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY not set. Please set the environment variable.")
openai.api_key = openai_api_key


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/api/transcript', methods=['POST'])
@limiter.limit("10 per minute")
def get_transcript():
    data = request.get_json()
    if not data or 'youtube_url' not in data:
        return jsonify({"status": "error", "message": "youtube_url required"}), 400

    youtube_url = data['youtube_url']
    if not is_valid_youtube_url(youtube_url):
        return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

    try:
        yt = YouTube(youtube_url)
    except Exception as e:
        logger.error(f"Error initializing YouTube object: {e}")
        return jsonify({"status": "error", "message": "Could not process the provided URL"}), 500

    # Attempt to get English captions (assuming 'en')
    caption = None
    for code, c in yt.captions.items():
        # Try a heuristic to match English captions
        if 'en' in code.lower():
            caption = c
            break

    if caption is None:
        return jsonify({"status": "error", "message": "No English transcript available."}), 404

    try:
        srt_captions = caption.generate_srt_captions()
        transcript_data = parse_srt_captions(srt_captions)
        return jsonify({
            "status": "success",
            "video_id": yt.video_id,
            "transcript": transcript_data
        })
    except Exception as e:
        logger.error(f"Error generating transcript: {e}")
        return jsonify({"status": "error", "message": "Could not retrieve transcript."}), 500


@app.route('/api/analyze', methods=['POST'])
@limiter.limit("10 per minute")
def analyze_transcript():
    data = request.get_json()
    if 'transcript' not in data or 'video_id' not in data:
        return jsonify({"status": "error", "message": "Missing transcript or video_id"}), 400

    transcript = data['transcript']
    analysis_type = data.get('analysis_type', 'detailed_summary')
    # Convert transcript array to a single text block
    transcript_text = "\n".join([t['text'] for t in transcript])

    # Depending on the analysis type, prompt ChatGPT differently
    prompt = generate_prompt(transcript_text, analysis_type)

    if not openai_api_key:
        return jsonify({"status": "error", "message": "OpenAI API key not set"}), 500

    try:
        # Call OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        # We can parse the content if structured; otherwise, return as is.
        insights = {"summary": content}  # For now, just return the text as summary.

        return jsonify({"status": "success", "insights": insights})
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return jsonify({"status": "error", "message": "Could not analyze the transcript."}), 500


def is_valid_youtube_url(url):
    # Simple validation (This can be more robust if needed)
    youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+'
    return re.match(youtube_regex, url) is not None


def parse_srt_captions(srt):
    # Parse SRT captions into a structured format: [{"text":..., "start":..., "duration":...}, ...]
    # SRT Format:
    # 1
    # 00:00:00,000 --> 00:00:05,000
    # This is a caption text.
    #
    # We'll parse line by line.
    lines = srt.split('\n')
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit():
            # Next line should have time
            i += 1
            time_line = lines[i].strip()
            start_str, end_str = time_line.split('-->')
            start_str = start_str.strip()
            end_str = end_str.strip()

            start_sec = srt_time_to_seconds(start_str)
            end_sec = srt_time_to_seconds(end_str)

            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip() != '':
                text_lines.append(lines[i].strip())
                i += 1
            caption_text = " ".join(text_lines)
            duration = end_sec - start_sec
            entries.append({
                "text": caption_text,
                "start": start_sec,
                "duration": duration
            })
        i += 1
    return entries


def srt_time_to_seconds(t_str):
    # Format: HH:MM:SS,mmm
    h, m, s_milli = t_str.split(':')
    s, ms = s_milli.split(',')
    return int(h)*3600 + int(m)*60 + float(s) + float(ms)/1000.0


def generate_prompt(transcript_text, analysis_type):
    if analysis_type == 'detailed_summary':
        return (f"Please provide a detailed summary of the following video transcript. "
                f"Also include key topics and important points:\n\n{transcript_text}")
    else:
        # Default fallback
        return (f"Please provide insights and a summary of the following transcript:\n\n{transcript_text}")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
