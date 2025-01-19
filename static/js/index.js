document.addEventListener("DOMContentLoaded", () => {
  const startDownloadBtn = document.getElementById("startDownloadBtn");
  const channelUrlInput = document.getElementById("channelUrl");
  const downloadStatus = document.getElementById("downloadStatus");
  const channelList = document.getElementById("channelList");

  // 1. Start Download
  startDownloadBtn.addEventListener("click", async () => {
    const url = channelUrlInput.value.trim();
    if (!url) {
      downloadStatus.innerText = "Please enter a URL.";
      return;
    }

    downloadStatus.innerText = "Starting download...";
    try {
      const res = await fetch("/api/channel/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_url: url }),
      });
      const data = await res.json();
      if (data.status === "initiated") {
        downloadStatus.innerText = `Download initiated. Task ID: ${data.task_id}`;
      } else {
        downloadStatus.innerText = `Error: ${data.message}`;
      }
    } catch (err) {
      downloadStatus.innerText = `Error starting download: ${err}`;
    }
  });

  // 2. Load Already Downloaded Channels
  async function loadChannels() {
    channelList.innerText = "Loading...";
    try {
      const res = await fetch("/api/channels");
      const channels = await res.json();
      if (!Array.isArray(channels) || channels.length === 0) {
        channelList.innerText = "No channels found.";
        return;
      }

      // Build list: pencil icon first, then channel link
      let html = "<ul>";
      channels.forEach(chId => {
        html += `
          <li>
            <span class="edit-icon" data-channel="${chId}" style="cursor: pointer; margin-right: 10px;">
              <svg xmlns="http://www.w3.org/2000/svg" height="18" viewBox="0 -960 960 960" width="18">
                <path d="M200-200h57l391-391-57-57-391 391v57Zm-80 80v-170l528-527q12-11 26.5-17t30.5-6q16 0 31 6t26 18l55 56q12 11 17.5 26t5.5 30q0 16-5.5 30.5T817-647L290-120H120Zm640-584-56-56 56 56Zm-141 85-28-29 57 57-29-28Z"/>
              </svg>
            </span>
            <span class="delete-icon" data-channel="${chId}" style="cursor: pointer; margin-right: 10px;">
              <!-- Trash SVG, for example -->
              <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px"><path d="M280-120q-33 0-56.5-23.5T200-200v-520h-40v-80h200v-40h240v40h200v80h-40v520q0 33-23.5 56.5T680-120H280Zm400-600H280v520h400v-520ZM360-280h80v-360h-80v360Zm160 0h80v-360h-80v360ZM280-720v520-520Z"/></svg>
            </span>     
            <span class="chat-icon" data-channel="${chId}" style="cursor: pointer; margin-right: 10px;">
            <a href="/chat-channel/${chId}"> <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px"><path d="M240-400h320v-80H240v80Zm0-120h480v-80H240v80Zm0-120h480v-80H240v80ZM80-80v-720q0-33 23.5-56.5T160-880h640q33 0 56.5 23.5T880-800v480q0 33-23.5 56.5T800-240H240L80-80Zm126-240h594v-480H160v525l46-45Zm-46 0v-480 480Z"/></svg></a>
            </span>                   
            <span class="channel-name" data-channel="${chId}">
              <a href="/videos/${chId}">${chId}</a>
            </span>


          </li>
        `;
      });
      html += "</ul>";
      channelList.innerHTML = html;

      // Bind events to edit icons
      document.querySelectorAll(".edit-icon").forEach(icon => {
        icon.addEventListener("click", handleEditClick);
      });
      // Bind events to delete icons
      document.querySelectorAll(".delete-icon").forEach(icon => {
        icon.addEventListener("click", handleDeleteClick);
      });

    } catch (err) {
      channelList.innerText = `Error loading channels: ${err}`;
    }
  }

  // 3. Handle Edit Click
  function handleEditClick(event) {
    const oldName = event.currentTarget.dataset.channel;
    if (!oldName) return;

    const spanElem = document.querySelector(`span.channel-name[data-channel="${oldName}"]`);
    if (!spanElem) return;

    // Grab the current text from the link
    const linkElem = spanElem.querySelector("a");
    const currentValue = linkElem ? linkElem.textContent.trim() : oldName;

    // Replace with an input
    spanElem.innerHTML = `<input type="text" class="rename-input" value="${currentValue}" />`;
    const input = spanElem.querySelector(".rename-input");
    input.focus();

    // We'll only call rename once
    let renameTriggered = false;

    // On blur
    input.addEventListener("blur", () => {
      if (!renameTriggered) {
        renameTriggered = true;
        finalizeRename(oldName, input.value);
      }
    });

    // On Enter
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

  // 4. Rename on server
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
        // Revert with new name (including link)
        revertSpan(oldName, data.new_name);

        // Update the edit icon's data-channel
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

  // 5. Revert to a link with new name
  function revertSpan(oldName, newName) {
    const spanElem = document.querySelector(`span.channel-name[data-channel="${oldName}"]`);
    if (!spanElem) return;
    spanElem.innerHTML = `<a href="/videos/${newName}">${newName}</a>`;
    // Update data-channel
    spanElem.dataset.channel = newName;
  }

  // 6. Handle Delete Click
  function handleDeleteClick(event) {
    const channelName = event.currentTarget.dataset.channel;
    if (!channelName) return;
  
    // Optional: confirmation
    if (!confirm(`Are you sure you want to delete the channel "${channelName}"? This will remove its videos if they are not used elsewhere.`)) {
      return;
    }
  
    // Call the delete API
    deleteChannel(channelName);
  }
  
  // 7. Delete channel on server
  async function deleteChannel(channelName) {
    try {
      const res = await fetch("/api/channels/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: channelName }),
      });
      const data = await res.json();
  
      if (res.ok && data.status === "ok") {
        alert(`Channel "${channelName}" has been deleted.`);
        // Remove the channel’s <li> from the DOM
        const liElem = document.querySelector(`li > .channel-name[data-channel="${channelName}"]`)?.parentElement;
        if (liElem) {
          liElem.remove();
        }
      } else {
        alert(`Error deleting channel: ${data.message || "Unknown error"}`);
      }
    } catch (err) {
      alert(`Error deleting channel: ${err}`);
    }
  }



  // Load channels on page load
  loadChannels();
});