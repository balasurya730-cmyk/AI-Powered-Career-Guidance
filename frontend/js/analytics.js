document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();
  
  const noDataState = document.getElementById("noDataState");
  const analyticsContent = document.getElementById("analyticsContent");

  try {
    const data = await apiRequest("/api/analytics");
    if (data.has_plan) {
      analyticsContent.classList.remove("hidden");
      renderCharts(data);
    } else {
      noDataState.classList.remove("hidden");
    }
  } catch (err) {
    noDataState.classList.remove("hidden");
    console.error("Could not load analytics:", err);
  }
});

function renderCharts(data) {
  // Chart defaults for dark/light themes
  Chart.defaults.color = '#f8fafc';
  Chart.defaults.font.family = "'Inter', sans-serif";

  // 1. Trends Chart (Line)
  const ctxTrends = document.getElementById('trendsChart').getContext('2d');
  new Chart(ctxTrends, {
    type: 'line',
    data: {
      labels: data.trends.labels,
      datasets: [{
        label: 'Tasks Completed',
        data: data.trends.data,
        borderColor: '#0ea5e9',
        backgroundColor: 'rgba(14, 165, 233, 0.2)',
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1 } }
      }
    }
  });

  // 2. Progress Chart (Doughnut)
  const ctxProgress = document.getElementById('progressChart').getContext('2d');
  new Chart(ctxProgress, {
    type: 'doughnut',
    data: {
      labels: ['Completed', 'Remaining'],
      datasets: [{
        data: [data.progress.completed, data.progress.remaining],
        backgroundColor: ['#10b981', 'rgba(255,255,255,0.05)'],
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      cutout: '70%',
      plugins: {
        legend: { position: 'bottom' }
      }
    }
  });

  // 3. Skills Chart (Radar)
  const ctxSkills = document.getElementById('skillsChart').getContext('2d');
  new Chart(ctxSkills, {
    type: 'radar',
    data: {
      labels: data.skills.labels,
      datasets: [{
        label: 'Your Mastery',
        data: data.skills.mastery,
        backgroundColor: 'rgba(14, 165, 233, 0.2)',
        borderColor: '#0ea5e9',
        pointBackgroundColor: '#0ea5e9'
      }, {
        label: 'Required',
        data: data.skills.required,
        backgroundColor: 'rgba(139, 92, 246, 0.2)',
        borderColor: '#8b5cf6',
        pointBackgroundColor: '#8b5cf6'
      }]
    },
    options: {
      responsive: true,
      scales: {
        r: {
          angleLines: { color: 'rgba(255, 255, 255, 0.1)' },
          grid: { color: 'rgba(255, 255, 255, 0.1)' },
          pointLabels: { color: '#a0aec0' },
          ticks: { display: false, min: 0, max: 100 }
        }
      }
    }
  });
}
