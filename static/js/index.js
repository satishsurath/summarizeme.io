document.addEventListener("DOMContentLoaded", () => {
    const startDownloadBtn = document.getElementById("startDownloadBtn");
    const channelUrlInput = document.getElementById("channelUrl");
    const downloadStatus = document.getElementById("downloadStatus");
  
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
  });