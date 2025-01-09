document.addEventListener("DOMContentLoaded", () => {
    const filterInput = document.getElementById("filterInput");
    const sortSelect = document.getElementById("sortSelect");
    const applyFilterBtn = document.getElementById("applyFilterBtn");
    const videosList = document.getElementById("videosList");
    const prevPageBtn = document.getElementById("prevPageBtn");
    const nextPageBtn = document.getElementById("nextPageBtn");
    const pageInfo = document.getElementById("pageInfo");
    const summarizeBtn = document.getElementById("summarizeBtn");
    const methodSelect = document.getElementById("methodSelect");
    const summaryStatus = document.getElementById("summaryStatus");
  
    let currentPage = 1;
    let pageSize = 5;
    let totalVideos = 0;
    let currentVideos = [];
  
    loadVideos();
  
    applyFilterBtn.addEventListener("click", () => {
      currentPage = 1;
      loadVideos();
    });
  
    prevPageBtn.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        loadVideos();
      }
    });
  
    nextPageBtn.addEventListener("click", () => {
      if ((currentPage * pageSize) < totalVideos) {
        currentPage++;
        loadVideos();
      }
    });
  
    summarizeBtn.addEventListener("click", async () => {
      const selected = currentVideos
        .filter(v => document.getElementById(`check_${v.video_id}`).checked)
        .map(v => v.video_id);
  
      if (selected.length === 0) {
        summaryStatus.innerText = "No videos selected.";
        return;
      }
  
      summaryStatus.innerText = "Starting summarization...";
      try {
        const res = await fetch("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            channel_id: channelId,
            video_ids: selected,
            method: methodSelect.value
          })
        });
        const data = await res.json();
        if (data.status === "initiated") {
          summaryStatus.innerText = `Summarization started. Task ID: ${data.task_id}`;
        } else {
          summaryStatus.innerText = `Error: ${data.message}`;
        }
      } catch (err) {
        summaryStatus.innerText = `Error summarizing: ${err}`;
      }
    });
  
    async function loadVideos() {
      const filterVal = filterInput.value;
      const sortVal = sortSelect.value;
      const url = `/api/videos/${channelId}?page=${currentPage}&page_size=${pageSize}&sort_by=${sortVal}&filter=${encodeURIComponent(filterVal)}`;
  
      videosList.innerHTML = "Loading...";
      try {
        const res = await fetch(url);
        const data = await res.json();
        totalVideos = data.total;
        currentVideos = data.videos;
        renderVideos(data.videos);
        pageInfo.innerText = `Page ${data.page} / ${Math.ceil(data.total / data.page_size)}`;
      } catch (err) {
        videosList.innerHTML = `Error loading videos: ${err}`;
      }
    }
  
    function renderVideos(videos) {
      if (!videos || videos.length === 0) {
        videosList.innerHTML = "<p>No videos found.</p>";
        return;
      }
      let html = `
        <table>
          <thead>
            <tr>
              <th><input type="checkbox" id="selectAll" /> Select</th>
              <th>Title</th>
              <th>Date</th>
              <th>OpenAI Summary</th>
              <th>Ollama Summary</th>
              <th>Transcript</th>
            </tr>
          </thead>
          <tbody>
      `;
      videos.forEach(v => {
        const openaiLink = v.openai_summary_exists 
          ? `<a href="/summaries/${channelId}/openai/${v.video_id}" target="_blank">View</a>` 
          : "N/A";
  
        const ollamaLink = v.ollama_summary_exists 
          ? `<a href="/summaries/${channelId}/ollama/${v.video_id}" target="_blank">View</a>` 
          : "N/A";
  
        // Transcript link: always assumed to exist if the video is downloaded
        // We'll link to method=transcript
        const transcriptLink = `<a href="/summaries/${channelId}/transcript/${v.video_id}" target="_blank">View</a>`;
  
        html += `
          <tr>
            <td><input type="checkbox" class="videoCheckbox" id="check_${v.video_id}" /></td>
            <td>${v.title}</td>
            <td>${v.upload_date}</td>
            <td>${openaiLink}</td>
            <td>${ollamaLink}</td>
            <td>${transcriptLink}</td>
          </tr>
        `;
      });
      html += "</tbody></table>";
      videosList.innerHTML = html;
        // Add event listener for "Select All" checkbox
  const selectAllCheckbox = document.getElementById("selectAll");
  const videoCheckboxes = document.querySelectorAll(".videoCheckbox");

  selectAllCheckbox.addEventListener("change", () => {
    const isChecked = selectAllCheckbox.checked;
    videoCheckboxes.forEach(checkbox => {
      checkbox.checked = isChecked;
    });
  });
    }
  });