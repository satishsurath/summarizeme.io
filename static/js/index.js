document.addEventListener("DOMContentLoaded", () => {
  const startDownloadBtn = document.getElementById("startDownloadBtn");
  const channelUrlInput = document.getElementById("channelUrl");
  const downloadStatus = document.getElementById("downloadStatus");
  const channelList = document.getElementById("channelList");

  // Start Download
  startDownloadBtn.addEventListener("click", async () => {
    const url = channelUrlInput.value.trim();
    if (!url) {
      downloadStatus.innerText = "Please enter a URL.";
      downloadStatus.className = "mt-4 text-red-500 dark:text-red-400";
      return;
    }

    downloadStatus.innerText = "Starting download...";
    downloadStatus.className = "mt-4 text-blue-500 dark:text-blue-400";
    
    try {
      const res = await fetch("/api/channel/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_url: url }),
      });
      const data = await res.json();
      if (data.status === "initiated") {
        downloadStatus.innerText = `Download initiated. Task ID: ${data.task_id}`;
        downloadStatus.className = "mt-4 text-green-500 dark:text-green-400";
      } else {
        downloadStatus.innerText = `Error: ${data.message}`;
        downloadStatus.className = "mt-4 text-red-500 dark:text-red-400";
      }
    } catch (err) {
      downloadStatus.innerText = `Error starting download: ${err}`;
      downloadStatus.className = "mt-4 text-red-500 dark:text-red-400";
    }
  });

  // Load Channels
  async function loadChannels() {
    channelList.innerText = "Loading...";
    try {
      const res = await fetch("/api/channels");
      let channels = await res.json();
          // If channels is not an array (e.g., a single object), convert it to an array
    if (!Array.isArray(channels)) {
      channels = [channels];
    }
      if (!Array.isArray(channels) || channels.length === 0) {
        channelList.innerText = "No channels found.";
        return;
      }

      let html = '<ul class="space-y-4">';
      channels.forEach(channel => {
        html += `
          <li class="flex items-center space-x-4 p-2 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors duration-200">
            <span class="edit-icon cursor-pointer text-gray-600 dark:text-gray-400 hover:text-blue-500 transition-colors duration-200" data-channel="${channel.folder_name}">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 -960 960 960">
                <path fill="currentColor" d="M200-200h57l391-391-57-57-391 391v57Zm-80 80v-170l528-527q12-11 26.5-17t30.5-6q16 0 31 6t26 18l55 56q12 11 17.5 26t5.5 30q0 16-5.5 30.5T817-647L290-120H120Z"/>
              </svg>
            </span>
            
            <span class="delete-icon cursor-pointer text-gray-600 dark:text-gray-400 hover:text-red-500 transition-colors duration-200" data-channel="${channel.folder_name}">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 -960 960 960">
                <path fill="currentColor" d="M280-120q-33 0-56.5-23.5T200-200v-520h-40v-80h200v-40h240v40h200v80h-40v520q0 33-23.5 56.5T680-120H280Z"/>
              </svg>
            </span>

            <span class="refresh-icon cursor-pointer text-gray-600 dark:text-gray-400 hover:text-green-500 transition-colors duration-200" data-channel="${channel.folder_name}">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24">
                <path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 .34-.03.67-.08 1h2.02c.05-.33.06-.66.06-1 0-4.42-3.58-8-8-8zm-6 8c0-.34.03-.67.08-1H4.06c-.05.33-.06.66-.06 1 0 4.42 3.58 8 8 8v3l4-4-4-4v3c-3.31 0-6-2.69-6-6z"/>
              </svg>
            </span>

            <span class="chat-icon cursor-pointer text-gray-600 dark:text-gray-400 hover:text-purple-500 transition-colors duration-200" data-channel="${channel.folder_name}">
              <a href="/chat-channel/${channel.folder_name}" class="block">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 -960 960 960">
                  <path fill="currentColor" d="M240-400h320v-80H240v80Zm0-120h480v-80H240v80Zm0-120h480v-80H240v80ZM80-80v-720q0-33 23.5-56.5T160-880h640q33 0 56.5 23.5T880-800v480q0 33-23.5 56.5T800-240H240L80-80Z"/>
                </svg>
              </a>
            </span>

            <span class="yt-icon cursor-pointer text-gray-600 dark:text-gray-400 hover:text-purple-500 transition-colors duration-200" data-channel="${channel.folder_name}">
            <a href="https://www.youtube.com/playlist?list=${channel.original_playlist_id}" 
                target="_blank"
                class="text-gray-500 hover:text-red-500 dark:text-gray-400 dark:hover:text-red-400 transition-colors">
                <svg class="w-5 h-5" viewBox="0 0 48 48">
                    <use href="#icon-summarizeYouTube" xlink:href="#icon-summarizeYouTube"></use>
                </svg>
            </a>
            </span>

            <span class="channel-name flex-grow" data-channel="${channel.folder_name}">
              <a href="/videos/${channel.folder_name}" class="text-gray-700 dark:text-gray-300 hover:text-blue-500 dark:hover:text-blue-400 transition-colors duration-200">${channel.folder_name}</a>
            </span>
          </li>
        `;
      });
      html += '</ul>';
      channelList.innerHTML = html;

      // Bind events
      document.querySelectorAll(".edit-icon").forEach(icon => {
        icon.addEventListener("click", handleEditClick);
      });
      document.querySelectorAll(".delete-icon").forEach(icon => {
        icon.addEventListener("click", handleDeleteClick);
      });
      document.querySelectorAll(".refresh-icon").forEach(icon => {
        icon.addEventListener("click", handleRefreshClick);
      });

    } catch (err) {
      channelList.innerHTML = `<div class="text-red-500 dark:text-red-400">Error loading channels: ${err}</div>`;
    }
  }

  // Handle Edit Click
  function handleEditClick(event) {
    const oldName = event.currentTarget.dataset.channel;
    if (!oldName) return;

    const spanElem = document.querySelector(`span.channel-name[data-channel="${oldName}"]`);
    if (!spanElem) return;

    const linkElem = spanElem.querySelector("a");
    const currentValue = linkElem ? linkElem.textContent.trim() : oldName;

    spanElem.innerHTML = `
      <input type="text" 
             class="rename-input w-full px-2 py-1 rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent" 
             value="${currentValue}" />
    `;
    
    const input = spanElem.querySelector(".rename-input");
    input.focus();

    let renameTriggered = false;

    input.addEventListener("blur", () => {
      if (!renameTriggered) {
        renameTriggered = true;
        finalizeRename(oldName, input.value);
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (!renameTriggered) {
          renameTriggered = true;
          finalizeRename(oldName, input.value);
        }
      }
    });
  }

  // Finalize Rename
  async function finalizeRename(oldName, newName) {
    if (newName.trim() === oldName.trim()) {
      revertSpan(oldName, oldName);
      return;
    }
    
    try {
      const res = await fetch("/api/channels/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_name: oldName, new_name: newName })
      });
      
      const data = await res.json();
      if (data.status === "ok") {
        revertSpan(oldName, data.new_name);
        const editIcon = document.querySelector(`.edit-icon[data-channel="${oldName}"]`);
        if (editIcon) {
          editIcon.dataset.channel = data.new_name;
        }
      } else {
        alert(`Rename error: ${data.message}`);
        revertSpan(oldName, oldName);
      }
    } catch (err) {
      alert(`Rename error: ${err}`);
      revertSpan(oldName, oldName);
    }
  }

  // Revert Span
  function revertSpan(oldName, newName) {
    const spanElem = document.querySelector(`span.channel-name[data-channel="${oldName}"]`);
    if (!spanElem) return;
    
    spanElem.innerHTML = `
      <a href="/videos/${newName}" 
         class="text-gray-700 dark:text-gray-300 hover:text-blue-500 dark:hover:text-blue-400 transition-colors duration-200">
        ${newName}
      </a>
    `;
    spanElem.dataset.channel = newName;
  }

  // Handle Delete Click
  function handleDeleteClick(event) {
    const channelName = event.currentTarget.dataset.channel;
    if (!channelName) return;
    
    if (!confirm(`Are you sure you want to delete the channel "${channelName}"? This will remove its videos if they are not used elsewhere.`)) {
      return;
    }
    
    deleteChannel(channelName);
  }

  // Delete Channel
  async function deleteChannel(channelName) {
    try {
      const res = await fetch("/api/channels/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: channelName }),
      });
      const data = await res.json();
    
      if (res.ok && data.status === "ok") {
        const liElem = document.querySelector(`li > .channel-name[data-channel="${channelName}"]`)?.parentElement;
        if (liElem) {
          liElem.classList.add('fade-out');
          setTimeout(() => liElem.remove(), 300);
        }
      } else {
        alert(`Error deleting channel: ${data.message || "Unknown error"}`);
      }
    } catch (err) {
      alert(`Error deleting channel: ${err}`);
    }
  }

  // Handle Refresh Click
  function handleRefreshClick(event) {
    const channelName = event.currentTarget.dataset.channel;
    if (!channelName) return;
    
    if (!confirm(`Refresh channel "${channelName}" to check for new videos?`)) {
      return;
    }
    console.log('refreshing channel', channelName);
    fetch("/api/channels/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel_name: channelName })
    })
    .then(response => response.json())
    .then(data => {
      if (data.status === "initiated") {
        console.log('refresh initiated', data.task_id);
        const icon = event.currentTarget.querySelector('svg');
        icon.classList.add('animate-spin');
        setTimeout(() => icon.classList.remove('animate-spin'), 1000);
        alert(`Refresh initiated. Task ID: ${data.task_id}`);
      } else {
        alert(`Error refreshing channel: ${data.message}`);
      }
    })
    .catch(err => {
      alert(`Error refreshing channel: ${err}`);
    });
  }

  // Add fade-out animation style
  const style = document.createElement('style');
  style.textContent = `
    .fade-out {
      opacity: 0;
      transition: opacity 300ms ease-in-out;
    }
  `;
  document.head.appendChild(style);

  // Load channels on page load
  loadChannels();
});