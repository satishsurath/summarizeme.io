# summarizeme.io - YouTube Transcript Analyzer

This open-source Python Flask application downloads YouTube transcripts (channel-wide) and summarizes them using either:
- **OpenAI’s ChatGPT 4o**  
- **Locally Hosted Ollama LLaMA 3.2**

All transcripts and summaries are stored in a local folder structure. This project includes asynchronous-like behavior via background threads for demonstration. For production, consider a full task queue solution (Celery, RQ, etc.).

## Features
1. **Channel-Wide Transcript Download**: Provide a channel URL or a video link from the channel. The app iterates over all videos and saves transcripts to `data/channels/<channel-id>/transcripts`.
2. **Separate Summaries**: 
   - OpenAI => `data/channels/<channel-id>/summaries_openai/`
   - Ollama => `data/channels/<channel-id>/summaries_ollama/`
3. **Pagination & Filtering**: The UI allows filtering by title and basic pagination.
4. **Robust Error Handling**: Continues downloading/summarizing if a single video fails.
5. **Status Updates**: The front-end polls status endpoints to show progress (in-progress, completed, failed, etc.).
6. **No Database**: All data stored on disk.

## Folder Structure
my_youtube_transcript_summarizer/
├─ app.py
├─ youtube_utils.py
├─ openai_summarizer.py
├─ ollama_summarizer.py
├─ requirements.txt
├─ .env.example
├─ README.md
├─ data/
│  └─ channels/
│     └─ /
│        ├─ transcripts/
│        │  └─ .json
│        ├─ summaries_openai/
│        │  └─ .md
│        └─ summaries_ollama/
│           └─ .md
├─ templates/
│  ├─ layout.html
│  ├─ index.html
│  ├─ status.html
│  ├─ videos.html
└─ static/
├─ css/
│  └─ styles.css
└─ js/
├─ index.js
├─ status.js
└─ videos.js

## Requirements
- Python 3.10+
- Virtualenv or pipenv recommended

## Setup

1. Clone the repository:
   ```bash
   git clone [this Repo]
   cd your-repo


2. Set up a virtual environment:

```
python3 -m venv venv
source venv/bin/activate
```


3. Install dependencies:

```
pip install -r requirements.txt
```
Create a .env file (based on .env.example):

```
makefile
Copy code
OPENAI_API_KEY=your-openai-key
```

4. Run the app:

```
flask run
```

The app will run on http://127.0.0.1:5000.

5. Using the App

Navigate to http://127.0.0.1:5000.


6.	(Optional) Ollama:
•	Make sure Ollama LLaMA 3.2 is installed and running locally if you want to use local summarization.


Usage
	1.	Open the app in your browser.
	2.	Enter a YouTube channel URL (or a video from that channel) and click “Start Download.”
	3.	Check Status to see progress as transcripts are downloaded.
	4.	Go to the videos page (/videos/<channel-id>) to see the list of videos.
	5.	Select Summarize (using either OpenAI or Ollama) and track progress.
	6.	Summaries are saved as .md files in the appropriate folder.

Deployment to Azure App Services
	1.	Create a Python 3.10 Web App in Azure.
	2.	Configure Environment Variables under App Settings:
	•	OPENAI_API_KEY = your key
	3.	Deploy via GitHub Actions or az webapp up.
	4.	Persistent Storage on Azure is trickier; you may need to mount a persistent volume or switch to Azure Blob Storage. For demonstration, local file storage should work but can be ephemeral unless configured otherwise.
