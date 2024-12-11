# summarizeme.io - YouTube Transcript Analyzer

This application allows you to fetch transcripts from YouTube videos using `pytube`, store them in the browser’s IndexedDB, and then analyze the transcript using OpenAI’s ChatGPT-4 model for detailed insights.

## Features
- Fetch YouTube transcripts by URL.
- Store transcripts locally in the user's browser (no server database).
- Analyze transcripts using the OpenAI ChatGPT-4 model.
- Display insights to the user.

## Requirements
- Python 3.10+
- Virtualenv or pipenv recommended

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-organization/your-repo.git
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
Enter a YouTube URL and click "Get Transcript".
Once fetched, click "Analyze Transcript" to get insights from OpenAI.
