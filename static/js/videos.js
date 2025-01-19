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
  let pageSize = 50;
  let totalVideos = 0;
  let currentVideos = [];

  // Dynamically load available Ollama models
  loadOllamaModels();

  // Initial load
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
    if (currentPage * pageSize < totalVideos) {
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
      const chosenModel = methodSelect.value;
      const res = await fetch("/api/summarize_v2", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_name: channel_name, // the variable from <script> above
          video_ids: selected,
          model: chosenModel
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
    const url = `/api/videos/${channel_name}?page=${currentPage}&page_size=${pageSize}&sort_by=${sortVal}&filter=${encodeURIComponent(filterVal)}`;

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
      <table class="table table-hover table-striped align-middle">
        <thead>
          <tr>
            <th><input type="checkbox" id="selectAll" /> Select</th>
            <th>Title</th>
            <th>Date</th>
            <th>Existing Summaries</th>
            <th>Transcript</th>
          </tr>
        </thead>
        <tbody>
    `;

    videos.forEach(v => {
      let summariesList = "";
      if (v.summaries_v2 && v.summaries_v2.length > 0) {
        summariesList = v.summaries_v2.map(s => {
          // Provide a link to the new route /summaries_v2/<s.id>
          return `
            <div>
              <a href="/summaries_v2/${s.id}" target="_blank">
                ${s.model_name} (ID: ${s.id})
              </a>
            </div>
          `;
        }).join("");
      } else {
        summariesList = `<em>No Summaries</em>`;
      }

      const transcriptLink = `<a href="/summaries/${channel_name}/transcript/${v.video_id}" target="_blank">View</a>`;

      html += `
        <tr>
          <td>
            <input 
              type="checkbox" 
              class="form-check-input videoCheckbox" 
              id="check_${v.video_id}" 
            />
          </td>
          <td>${v.title}</td>
          <td>${v.upload_date}</td>
          <td>${summariesList}</td>
          <td>${transcriptLink}</td>
        </tr>
      `;
    });

    html += "</tbody></table>";
    videosList.innerHTML = html;

    // "Select All" logic
    const selectAllCheckbox = document.getElementById("selectAll");
    const videoCheckboxes = document.querySelectorAll(".videoCheckbox");
    selectAllCheckbox.addEventListener("change", () => {
      const isChecked = selectAllCheckbox.checked;
      videoCheckboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
      });
    });
  }

  // Dynamically load available Ollama models
  async function loadOllamaModels() {
    try {
      const resp = await fetch("/api/ollama/models");
      const data = await resp.json();
      methodSelect.innerHTML = ""; // clear existing

      data.data.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.id;
        methodSelect.appendChild(opt);
      });
    } catch (err) {
      console.error("Failed to load Ollama models:", err);
      // fallback
      methodSelect.innerHTML = "<option value='phi4:latest'>phi4:latest</option>";
    }
  }
});