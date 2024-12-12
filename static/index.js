document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('transcript-form');
    const transcriptResult = document.getElementById('transcript-result');
    const analysisSection = document.getElementById('analysis-section');
    const analyzeBtn = document.getElementById('analyze-btn');
    const analysisResult = document.getElementById('analysis-result');
    const saveKeyBtn = document.getElementById('save-key-btn');
    const openaiKeyInput = document.getElementById('openai_key');

    // Load key from localStorage if available
    const savedKey = localStorage.getItem('openai_api_key');
    if (savedKey) {
        openaiKeyInput.value = savedKey;
    }

    saveKeyBtn.addEventListener('click', () => {
        const key = openaiKeyInput.value.trim();
        if (key) {
          localStorage.setItem('openai_api_key', key);
          alert('OpenAI API Key saved locally!');
          console.log('Key saved to localStorage:', key);
        } else {
          alert('Please enter a valid OpenAI API key.');
        }
      });

    let db;
    const request = indexedDB.open('video_transcripts', 2);
    request.onupgradeneeded = function(e) {
        db = e.target.result;
        if(!db.objectStoreNames.contains('videos')) {
            const store = db.createObjectStore('videos', { keyPath: 'video_id' });
            store.createIndex('title', 'title', { unique: false });
            store.createIndex('upload_date', 'upload_date', { unique: false });
        }
    };
    request.onsuccess = function(e) {
        db = e.target.result;
    };
    request.onerror = function() {
        console.error('IndexedDB error');
    };

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const youtube_url = document.getElementById('youtube_url').value.trim();
        if (!youtube_url) return;

        transcriptResult.textContent = 'Fetching transcript...';
        analysisSection.style.display = 'none';
        analysisResult.innerHTML = '';

        try {
            const res = await fetch('/api/transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json'},
                body: JSON.stringify({youtube_url})
            });
            const data = await res.json();
            if (data.status === 'success') {
                transcriptResult.innerHTML = 'Transcript fetched.';

                const tx = db.transaction('videos', 'readwrite');
                const store = tx.objectStore('videos');
                store.put({
                    video_id: data.video_id,
                    youtube_url: youtube_url,
                    title: data.title,
                    upload_date: data.upload_date,
                    transcript: data.transcript,
                    analysis_markdown: null
                });
                tx.oncomplete = () => {
                    analysisSection.style.display = 'block';
                    const snippet = data.transcript.slice(0,5).map(t => t.text).join('\n');
                    transcriptResult.innerHTML = `<pre>${snippet}</pre>`;
                };
            } else {
                transcriptResult.innerHTML = `Error: ${data.message}`;
            }
        } catch (err) {
            transcriptResult.innerHTML = 'Error fetching transcript.';
        }
    });

    analyzeBtn.addEventListener('click', async () => {
        analysisResult.textContent = 'Analyzing transcript...';

        const video = await getLatestVideo();
        if (!video) {
            analysisResult.textContent = 'No transcript to analyze.';
            return;
        }

        const key = localStorage.getItem('openai_api_key');
        if (!key) {
            analysisResult.textContent = 'No OpenAI API key provided. Please enter your key above.';
            return;
        }

        try {
            const res = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_id: video.video_id,
                    title: video.title,
                    upload_date: video.upload_date,
                    transcript: video.transcript,
                    analysis_type: 'detailed_summary',
                    openai_api_key: key
                })
            });
            const data = await res.json();
            if (data.status === 'success') {
                const htmlContent = marked.parse(data.analysis_markdown);
                analysisResult.innerHTML = htmlContent;
                const tx = db.transaction('videos', 'readwrite');
                const store = tx.objectStore('videos');
                store.put({
                    ...video,
                    analysis_markdown: data.analysis_markdown
                });
            } else {
                analysisResult.innerHTML = `Error: ${data.message}`;
            }
        } catch (err) {
            analysisResult.innerHTML = 'Error analyzing transcript.';
            console.error(err);
        }
    });

    async function getLatestVideo() {
        return new Promise((resolve) => {
            const tx = db.transaction('videos', 'readonly');
            const store = tx.objectStore('videos');
            const req = store.getAll();
            req.onsuccess = function() {
                if (req.result.length > 0) {
                    resolve(req.result[req.result.length - 1]);
                } else {
                    resolve(null);
                }
            };
        });
    }
});
