document.addEventListener("DOMContentLoaded", () => {
  const statusResult = document.getElementById("statusResult");
  let previousData = null;

  function getStatusColor(status) {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'text-green-500 dark:text-green-400';
      case 'in progress':
        return 'text-blue-500 dark:text-blue-400';
      case 'failed':
        return 'text-red-500 dark:text-red-400';
      case 'pending':
        return 'text-yellow-500 dark:text-yellow-400';
      default:
        return 'text-gray-500 dark:text-gray-400';
    }
  }

  function getProgressBar(processed, total) {
    const percentage = total > 0 ? (processed / total) * 100 : 0;
    const width = `${percentage}%`;
    
    return `
      <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
        <div class="bg-blue-500 h-2.5 rounded-full" style="width: ${width}"></div>
      </div>
      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
        ${processed} / ${total}
      </div>
    `;
  }

  async function fetchAllTasks() {
    try {
      const res = await fetch("/api/all-tasks");
      const data = await res.json();

      // If no data, show empty state
      if (!data || data.length === 0) {
        statusResult.innerHTML = `
          <div class="text-center py-8">
            <p class="text-gray-500 dark:text-gray-400">No active tasks found</p>
          </div>
        `;
        return;
      }

      let tableHTML = `
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr class="bg-gray-50 dark:bg-gray-700">
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Task ID</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Type</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Progress</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Errors</th>
              </tr>
            </thead>
            <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
      `;

      data.forEach((task, index) => {
        const isNew = !previousData || !previousData.find(p => p.task_id === task.task_id);
        const rowClass = isNew ? 'animate-fade-in' : '';
        
        tableHTML += `
          <tr class="${rowClass} hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
              ${task.task_id}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
              ${task.type}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(task.status)}">
                ${task.status}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="w-48">
                ${getProgressBar(task.processed, task.total)}
              </div>
            </td>
            <td class="px-6 py-4 text-sm text-red-500 dark:text-red-400">
              ${task.errors.length ? task.errors.join(", ") : '-'}
            </td>
          </tr>
        `;
      });

      tableHTML += `
            </tbody>
          </table>
        </div>
      `;

      // Add fade-in animation style if not already present
      if (!document.getElementById('fade-in-style')) {
        const style = document.createElement('style');
        style.id = 'fade-in-style';
        style.textContent = `
          @keyframes fadeIn {
            from { opacity: 0; background-color: rgba(59, 130, 246, 0.1); }
            to { opacity: 1; background-color: transparent; }
          }
          .animate-fade-in {
            animation: fadeIn 1s ease-out;
          }
        `;
        document.head.appendChild(style);
      }

      statusResult.innerHTML = tableHTML;
      previousData = data;

    } catch (err) {
      statusResult.innerHTML = `
        <div class="rounded-md bg-red-50 dark:bg-red-900/50 p-4">
          <div class="flex">
            <div class="flex-shrink-0">
              <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
              </svg>
            </div>
            <div class="ml-3">
              <h3 class="text-sm font-medium text-red-800 dark:text-red-200">
                Error fetching tasks
              </h3>
              <div class="mt-2 text-sm text-red-700 dark:text-red-300">
                ${err.toString()}
              </div>
            </div>
          </div>
        </div>
      `;
    }
  }

  // Initial fetch
  fetchAllTasks();

  // Refresh every 5 seconds
  setInterval(fetchAllTasks, 5000);
});