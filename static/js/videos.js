document.addEventListener("DOMContentLoaded", () => {
  const filterInput = document.getElementById("filterInput");
  const applyFilterBtn = document.getElementById("applyFilterBtn");
  const videosList = document.getElementById("videosList");
  const prevPageBtn = document.getElementById("prevPageBtn");
  const nextPageBtn = document.getElementById("nextPageBtn");
  const pageInfo = document.getElementById("pageInfo");
  const summarizeBtn = document.getElementById("summarizeBtn");
  const methodSelect = document.getElementById("methodSelect");
  const summaryStatus = document.getElementById("summaryStatus");
  
  // For column header links:
  const sortTitleLink = document.getElementById("sortTitleLink");
  const sortDateLink = document.getElementById("sortDateLink");

  let currentPage = 1;
  let pageSize = 50;
  let totalVideos = 0;
  let currentVideos = [];

  // Track sort column & order. 
  // Default to sorting by 'title' ascending, for example.
  let currentSort = {
    by: 'title',
    order: 'asc'
  };

  // ==========================
  //  Define updateSortIndicators
  // ==========================
  function updateSortIndicators() {
    // Clear out any existing indicators
    sortTitleLink.innerText = "Title";
    sortDateLink.innerText = "Date";
  
    // Show an arrow on whichever is selected
    if (currentSort.by === "title") {
      sortTitleLink.innerText += (currentSort.order === "asc") ? " ↑" : " ↓";
    } else if (currentSort.by === "date") {
      sortDateLink.innerText += (currentSort.order === "asc") ? " ↑" : " ↓";
    }
  }

  // =====================
  //    EVENT LISTENERS
  // =====================
  // 1) Filter
  applyFilterBtn.addEventListener("click", () => {
    currentPage = 1;
    loadVideos();
  });

  // 2) Pagination
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

  // 3) Sorting by clicking column headers
  sortTitleLink.addEventListener("click", (e) => {
    e.preventDefault();
    
    // If already sorting by 'title', flip the order. Otherwise, set to asc.
    if (currentSort.by === 'title') {
      currentSort.order = (currentSort.order === 'asc') ? 'desc' : 'asc';
    } else {
      currentSort.by = 'title';
      currentSort.order = 'asc';
    }
    updateSortIndicators();
    currentPage = 1;
    loadVideos();
    
  });

  sortDateLink.addEventListener("click", (e) => {
    e.preventDefault();
    
    // If already sorting by 'date', flip the order. Otherwise, set to desc or asc (your preference).
    if (currentSort.by === 'date') {
      currentSort.order = (currentSort.order === 'asc') ? 'desc' : 'asc';
    } else {
      currentSort.by = 'date';
      // maybe default to descending for date so newest first:
      currentSort.order = 'desc';
    }
    updateSortIndicators();
    currentPage = 1;
    loadVideos();
    
  });

  // 4) Summarize button
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
          channel_name: channel_name, 
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

  // Load the Ollama models for the Summarize <select>
  loadOllamaModels();

  // Initially load the first page of videos
  loadVideos();

  // =====================
  //    MAIN FUNCTIONS
  // =====================
  async function loadVideos() {
    const filterVal = filterInput.value;
    const url = `/api/videos/${channel_name}?page=${currentPage}&page_size=${pageSize}`
              + `&sort_by=${currentSort.by}&sort_order=${currentSort.order}`
              + `&filter=${encodeURIComponent(filterVal)}`;

    videosList.innerHTML = "<tr><td colspan='5'>Loading...</td></tr>";
    try {
      const res = await fetch(url);
      const data = await res.json();
      totalVideos = data.total;
      currentVideos = data.videos;
      renderVideos(data.videos);
      pageInfo.innerText = `Page ${data.page} of ${Math.ceil(data.total / data.page_size)}`;
    } catch (err) {
      videosList.innerHTML = `<tr><td colspan='5'>Error loading videos: ${err}</td></tr>`;
    }
  }

  function renderVideos(videos) {
    if (!videos || videos.length === 0) {
      videosList.innerHTML = "<tr><td colspan='5'>No videos found.</td></tr>";
      return;
    }

    let html = "";
    videos.forEach(v => {
      let summariesList = "";
      if (v.summaries_v2 && v.summaries_v2.length > 0) {
        summariesList = v.summaries_v2.map(s => {
          return `
            <div>
              <a href="/summaries_v2/${s.id}" target="_blank">
                ${s.model_name}
              </a>
            </div>
          `;
        }).join("");
      } else {
        summariesList = `<em>No Summaries</em>`;
      }

      const transcriptLink = `<a href="/transcript/${v.video_id}">View</a>`;

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

  // Load Ollama models
  async function loadOllamaModels() {
    try {
      const resp = await fetch("/api/ollama/models");
      const data = await resp.json();
      methodSelect.innerHTML = ""; // clear existing

      (data.data || []).forEach(m => {
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

