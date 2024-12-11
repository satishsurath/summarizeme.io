document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('transcript-form');
    const transcriptResult = document.getElementById('transcript-result');
    const analysisSection = document.getElementById('analysis-section');
    const analyzeBtn = document.getElementById('analyze-btn');
    const analysisResult = document.getElementById('analysis-result');

    // IndexedDB setup
    let db;
    const request = indexedDB.open('video_transcripts', 1);
    request.onupgradeneeded = function(e) {
        db = e.target.result;
        if(!db.objectStoreNames.contains('transcripts')) {
            db.createObjectStore('transcripts', { keyPath: 'video_id' });
        }
        if(!db.objectStoreNames.contains('insights')) {
            db.createObjectStore('insights', { keyPath: 'video_id' });
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

        transcriptResult.innerHTML = 'Fetching transcript...';
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
                // Store in IndexedDB
                const tx = db.transaction('transcripts', 'readwrite');
                tx.objectStore('transcripts').put({
                    video_id: data.video_id,
                    transcript: data.transcript
                });
                tx.oncomplete = () => {
                    transcriptResult.innerHTML = 'Transcript fetched and stored.';
                    analysisSection.style.display = 'block';
                };
                // Optional: show snippet of transcript
                const snippet = data.transcript.slice(0,5).map(t => t.text).join('\n');
                transcriptResult.innerHTML = `<pre>${snippet}</pre>`;
            } else {
                transcriptResult.innerHTML = `Error: ${data.message}`;
            }
        } catch (err) {
            transcriptResult.innerHTML = 'Error fetching transcript.';
        }
    });

    analyzeBtn.addEventListener('click', async () => {
        analysisResult.innerHTML = 'Analyzing transcript...';

        // Retrieve transcript from IndexedDB
        const video_id = await getLatestVideoID();
        if (!video_id) {
            analysisResult.innerHTML = 'No transcript to analyze.';
            return;
        }
        const transcriptEntry = await getTranscriptByVideoID(video_id);
        if (!transcriptEntry) {
            analysisResult.innerHTML = 'Transcript not found in database.';
            return;
        }

        try {
            const res = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_id: video_id,
                    transcript: transcriptEntry.transcript,
                    analysis_type: 'detailed_summary'
                })
            });
            const data = await res.json();
            if (data.status === 'success') {
                analysisResult.innerHTML = `<pre>${JSON.stringify(data.insights, null, 2)}</pre>`;
                // Store insights
                const tx = db.transaction('insights', 'readwrite');
                tx.objectStore('insights').put({
                    video_id: video_id,
                    insights: data.insights
                });
            } else {
                analysisResult.innerHTML = `Error: ${data.message}`;
            }
        } catch (err) {
            analysisResult.innerHTML = 'Error analyzing transcript.';
        }
    });

    async function getLatestVideoID() {
        return new Promise((resolve, reject) => {
            const tx = db.transaction('transcripts', 'readonly');
            const store = tx.objectStore('transcripts');
            const req = store.getAll();
            req.onsuccess = function() {
                if (req.result.length > 0) {
                    // Return the last fetched video's ID (or first if you prefer)
                    resolve(req.result[req.result.length - 1].video_id);
                } else {
                    resolve(null);
                }
            };
            req.onerror = function() {
                resolve(null);
            };
        });
    }

    async function getTranscriptByVideoID(video_id) {
        return new Promise((resolve, reject) => {
            const tx = db.transaction('transcripts', 'readonly');
            const store = tx.objectStore('transcripts');
            const req = store.get(video_id);
            req.onsuccess = function() {
                resolve(req.result);
            };
            req.onerror = function() {
                resolve(null);
            };
        });
    }
});
