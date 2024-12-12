document.addEventListener('DOMContentLoaded', () => {
    const historyList = document.getElementById('history-list');
    const filterInput = document.getElementById('filter-input');
    const detailsModal = new bootstrap.Modal(document.getElementById('detailsModal'));
    const detailsTitle = document.getElementById('details-title');
    const detailsDate = document.getElementById('details-date');
    const detailsTranscript = document.getElementById('details-transcript');
    const detailsAnalysis = document.getElementById('details-analysis');
    const copyTranscriptBtn = document.getElementById('copy-transcript');
    const copyAnalysisBtn = document.getElementById('copy-analysis');

    let db;
    const request = indexedDB.open('video_transcripts', 2);
    request.onsuccess = function(e) {
        db = e.target.result;
        loadHistory();
    };

    request.onerror = function() {
        console.error('IndexedDB error');
    };

    filterInput.addEventListener('input', loadHistory);

    async function loadHistory() {
        const filterText = filterInput.value.toLowerCase();
        const videos = await getAllVideos();
        const filtered = videos.filter(v => v.title.toLowerCase().includes(filterText));
        
        historyList.innerHTML = '';
        filtered.forEach(video => {
            const col = document.createElement('div');
            col.className = 'col-12';

            const card = document.createElement('div');
            card.className = 'card p-3 shadow-sm';
            const titleEl = document.createElement('h5');
            titleEl.textContent = video.title;
            const dateEl = document.createElement('small');
            dateEl.className = 'text-muted';
            dateEl.textContent = `Uploaded: ${video.upload_date}`;

            const btnDetails = document.createElement('button');
            btnDetails.className = 'btn btn-link p-0 mt-2';
            btnDetails.textContent = 'View Details';
            btnDetails.addEventListener('click', () => showDetails(video));

            card.appendChild(titleEl);
            card.appendChild(dateEl);
            card.appendChild(btnDetails);
            col.appendChild(card);
            historyList.appendChild(col);
        });
    }

    function showDetails(video) {
        detailsTitle.textContent = video.title;
        detailsDate.textContent = video.upload_date;

        // Transcript plain text
        const transcriptText = video.transcript.map(t => t.text).join('\n');
        detailsTranscript.textContent = transcriptText;

        // Analysis markdown -> HTML
        if (video.analysis_markdown) {
            detailsAnalysis.innerHTML = marked.parse(video.analysis_markdown);
        } else {
            detailsAnalysis.innerHTML = '<em>No analysis available</em>';
        }

        copyTranscriptBtn.onclick = () => {
            navigator.clipboard.writeText(transcriptText);
        };
        copyAnalysisBtn.onclick = () => {
            const analysisText = video.analysis_markdown || '';
            navigator.clipboard.writeText(analysisText);
        };

        detailsModal.show();
    }

    function getAllVideos() {
        return new Promise((resolve) => {
            const tx = db.transaction('videos', 'readonly');
            const store = tx.objectStore('videos');
            const req = store.getAll();
            req.onsuccess = function() {
                resolve(req.result || []);
            };
        });
    }
});
