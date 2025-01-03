document.addEventListener("DOMContentLoaded", () => {
    const checkStatusBtn = document.getElementById("checkStatusBtn");
    const taskIdInput = document.getElementById("taskId");
    const statusResult = document.getElementById("statusResult");
  
    checkStatusBtn.addEventListener("click", async () => {
      const taskId = taskIdInput.value.trim();
      if (!taskId) {
        statusResult.innerText = "Please enter a Task ID.";
        return;
      }
  
      // Determine if it's a download or summarize task by prefix, or attempt both
      let url = "";
      if (taskId.startsWith("dl_")) {
        url = `/api/channel/status/${taskId}`;
      } else if (taskId.startsWith("sum_")) {
        url = `/api/summarize/status/${taskId}`;
      } else {
        statusResult.innerText = "Invalid Task ID format.";
        return;
      }
  
      try {
        const res = await fetch(url);
        const data = await res.json();
        if (data.status === "error") {
          statusResult.innerText = data.message;
        } else {
          statusResult.innerText = JSON.stringify(data, null, 2);
        }
      } catch (err) {
        statusResult.innerText = `Error fetching status: ${err}`;
      }
    });
  });