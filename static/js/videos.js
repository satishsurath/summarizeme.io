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
  const sortTitleLink = document.getElementById("sortTitleLink");
  const sortDateLink = document.getElementById("sortDateLink");

  let currentPage = 1;
  let pageSize = 50;
  let totalVideos = 0;
  let currentVideos = [];
  let currentSort = {
    by: 'title',
    order: 'asc'
  };

  function updateSortIndicators() {
    // Reset both links to default state
    sortTitleLink.innerText = "Title";
    sortDateLink.innerText = "Date";
    
    const defaultClass = "text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider hover:text-gray-700 dark:hover:text-gray-200";
    const activeClass = "text-xs font-medium text-blue-500 dark:text-blue-400 uppercase tracking-wider";
    
    sortTitleLink.className = defaultClass;
    sortDateLink.className = defaultClass;
  
    if (currentSort.by === "title") {
      sortTitleLink.innerText += currentSort.order === "asc" ? " ↑" : " ↓";
      sortTitleLink.className = activeClass;
    } else if (currentSort.by === "date") {
      sortDateLink.innerText += currentSort.order === "asc" ? " ↑" : " ↓";
      sortDateLink.className = activeClass;
    }
  }

  // Event Listeners
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

  sortTitleLink.addEventListener("click", (e) => {
    e.preventDefault();
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
    if (currentSort.by === 'date') {
      currentSort.order = (currentSort.order === 'asc') ? 'desc' : 'asc';
    } else {
      currentSort.by = 'date';
      currentSort.order = 'desc';
    }
    updateSortIndicators();
    currentPage = 1;
    loadVideos();
  });

  summarizeBtn.addEventListener("click", async () => {
    const selected = currentVideos
      .filter(v => document.getElementById(`check_${v.video_id}`).checked)
      .map(v => v.video_id);

    if (selected.length === 0) {
      summaryStatus.innerText = "No videos selected.";
      summaryStatus.className = "mt-2 text-sm text-red-500 dark:text-red-400";
      return;
    }

    summaryStatus.innerText = "Starting summarization...";
    summaryStatus.className = "mt-2 text-sm text-blue-500 dark:text-blue-400";

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
        summaryStatus.className = "mt-2 text-sm text-green-500 dark:text-green-400";
      } else {
        summaryStatus.innerText = `Error: ${data.message}`;
        summaryStatus.className = "mt-2 text-sm text-red-500 dark:text-red-400";
      }
    } catch (err) {
      summaryStatus.innerText = `Error summarizing: ${err}`;
      summaryStatus.className = "mt-2 text-sm text-red-500 dark:text-red-400";
    }
  });

  async function loadVideos() {
    const filterVal = filterInput.value;
    const url = `/api/videos/${channel_name}?page=${currentPage}&page_size=${pageSize}`
              + `&sort_by=${currentSort.by}&sort_order=${currentSort.order}`
              + `&filter=${encodeURIComponent(filterVal)}`;

    videosList.innerHTML = `
      <tr>
        <td colspan="5" class="px-6 py-4 text-center text-gray-500 dark:text-gray-400">
          <div class="animate-pulse">Loading...</div>
        </td>
      </tr>
    `;

    try {
      const res = await fetch(url);
      const data = await res.json();
      totalVideos = data.total;
      currentVideos = data.videos;
      renderVideos(data.videos);
      pageInfo.innerText = `Page ${data.page} of ${Math.ceil(data.total / data.page_size)}`;
      
      // Update button states
      prevPageBtn.disabled = currentPage <= 1;
      nextPageBtn.disabled = currentPage * pageSize >= totalVideos;
      
      // Update button styles based on disabled state
      [prevPageBtn, nextPageBtn].forEach(btn => {
        if (btn.disabled) {
          btn.className = "px-4 py-2 border border-gray-200 dark:border-gray-700 text-sm font-medium rounded-md text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 cursor-not-allowed";
        } else {
          btn.className = "px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500";
        }
      });
    } catch (err) {
      videosList.innerHTML = `
        <tr>
          <td colspan="5" class="px-6 py-4 text-center text-red-500 dark:text-red-400">
            Error loading videos: ${err}
          </td>
        </tr>
      `;
    }
  }

  function renderVideos(videos) {
    if (!videos || videos.length === 0) {
      videosList.innerHTML = `
        <tr>
          <td colspan="5" class="px-6 py-4 text-center text-gray-500 dark:text-gray-400">
            No videos found.
          </td>
        </tr>
      `;
      return;
    }

    let html = "";
    videos.forEach(v => {
      let summariesList = "";
      if (v.summaries_v2 && v.summaries_v2.length > 0) {
        summariesList = v.summaries_v2.map(s => {
          return `
            <div class="mb-1">
              <a href="/summaries_v2/${s.id}" 
                 class="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300"
                 target="_blank">
                ${s.model_name}
              </a>
            </div>
          `;
        }).join("");
      } else {
        summariesList = `<em class="text-gray-400 dark:text-gray-500">No Summaries</em>`;
      }

      const transcriptLink = `
        <a href="/transcript/${v.video_id}" 
           class="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300">
          View
        </a>
      `;

      html += `
        <tr class="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
          <td class="px-6 py-4">
            <input type="checkbox" 
                   class="videoCheckbox w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700"
                   id="check_${v.video_id}" 
            />
          </td>
          <td class="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">${v.title}</td>
          <td class="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">${v.upload_date}</td>
          <td class="px-6 py-4 text-sm">${summariesList}</td>
          <td class="px-6 py-4 text-sm">${transcriptLink}</td>
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
      methodSelect.innerHTML = `
        <option value="phi4:latest" class="text-gray-900 dark:text-gray-100">
          phi4:latest
        </option>
      `;
    }
  }

  // Initialize
  updateSortIndicators();
  loadOllamaModels();
  loadVideos();
});