document.addEventListener("DOMContentLoaded", () => {
  const statusResult = document.getElementById("statusResult");

  // Function to fetch and display all tasks
  async function fetchAllTasks() {
    try {
      const res = await fetch("/api/all-tasks");
      const data = await res.json();  // data is an array of tasks

      // Build a simple HTML table
      let tableHTML = `
        <table border="1">
          <thead>
            <tr>
              <th>Task ID</th>
              <th>Type</th>
              <th>Status</th>
              <th>Processed</th>
              <th>Total</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
      `;

      data.forEach(task => {
        tableHTML += `
          <tr>
            <td>${task.task_id}</td>
            <td>${task.type}</td>
            <td>${task.status}</td>
            <td>${task.processed}</td>
            <td>${task.total}</td>
            <td>${task.errors.join(", ")}</td>
          </tr>
        `;
      });

      tableHTML += `
          </tbody>
        </table>
      `;

      statusResult.innerHTML = tableHTML;
    } catch (err) {
      statusResult.innerText = `Error fetching tasks: ${err}`;
    }
  }

  // Initial fetch
  fetchAllTasks();

  // Refresh every 5 seconds (adjust as needed)
  setInterval(fetchAllTasks, 5000);
});