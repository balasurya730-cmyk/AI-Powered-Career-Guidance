/* a-z-careers.js
   ========================================================================= */

document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();

  const directoryGrid = document.getElementById("directoryGrid");
  const loadingIndicator = document.getElementById("loadingIndicator");
  const searchInput = document.getElementById("searchInput");
  const noResultsMsg = document.getElementById("noResultsMsg");
  const btnGenerateCareer = document.getElementById("btnGenerateCareer");
  let allCareers = [];

  try {
    const data = await apiRequest("/api/career/directory");
    allCareers = data.careers || [];
    renderCareers(allCareers);
  } catch (err) {
    console.error("Failed to load directory", err);
  } finally {
    loadingIndicator.classList.add("hidden");
    directoryGrid.classList.remove("hidden");
  }

  searchInput.addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase();
    const filtered = allCareers.filter(c => 
      c.career_name.toLowerCase().includes(query) || 
      c.description.toLowerCase().includes(query) ||
      c.required_skills.some(s => s.toLowerCase().includes(query))
    );
    renderCareers(filtered);
  });

  btnGenerateCareer.addEventListener("click", async () => {
    const careerName = searchInput.value.trim();
    if (!careerName) return;
    
    const originalText = btnGenerateCareer.textContent;
    btnGenerateCareer.textContent = "✨ Generating AI Profile... (This may take a minute)";
    btnGenerateCareer.disabled = true;

    try {
      const res = await apiRequest("/api/career/directory/generate", "POST", {
        career_name: careerName
      });
      // Add the newly generated career to the list and re-render
      allCareers.push(res);
      // Sort alphabetically
      allCareers.sort((a, b) => a.career_name.localeCompare(b.career_name));
      // Clear search to show all, including the new one
      searchInput.value = "";
      renderCareers(allCareers);
    } catch (err) {
      alert("Failed to generate career: " + err.message);
    } finally {
      btnGenerateCareer.textContent = originalText;
      btnGenerateCareer.disabled = false;
    }
  });

  function renderCareers(careers) {
    if (careers.length === 0) {
      directoryGrid.innerHTML = "";
      noResultsMsg.classList.remove("hidden");
      return;
    }
    
    noResultsMsg.classList.add("hidden");
    directoryGrid.innerHTML = careers.map(c => {
      const skillsHtml = c.required_skills.map(s => `<span>${escapeHtml(s)}</span>`).join("");
      return `
        <div class="card career-card">
          <div>
            <h3>${escapeHtml(c.career_name)}</h3>
            <div class="skills-tags">${skillsHtml}</div>
            <p>${escapeHtml(c.description)}</p>
            <p style="font-size: 0.85rem; color: var(--pine-300);"><strong>Future Scope:</strong> ${escapeHtml(c.future_scope)}</p>
            <div id="matchScoreContainer-${c.id}" style="margin-top: 12px;">
              <button class="btn btn-outline" style="font-size: 0.8rem; padding: 4px 8px;" onclick="calculateFitScore(${c.id}, '${escapeHtml(c.career_name)}', this)">
                🎯 Calculate Predictive Fit Score
              </button>
            </div>
          </div>
          <button class="btn btn-primary" style="margin-top: 16px; width: 100%;" onclick="selectDirectoryCareer(${c.id}, this)">
            Choose Path
          </button>
        </div>
      `;
    }).join("");
  }
});

async function calculateFitScore(careerId, careerName, btn) {
  const container = document.getElementById(`matchScoreContainer-${careerId}`);
  btn.textContent = "Calculating...";
  btn.disabled = true;

  try {
    const res = await apiRequest("/api/career/match-score", { method: "POST", body: { career_name: careerName } });
    
    // Determine color based on score
    let scoreColor = "var(--pine-300)";
    if (res.score >= 80) scoreColor = "var(--trail)";
    else if (res.score < 50) scoreColor = "#ef4444"; // Red for low fit
    
    container.innerHTML = `
      <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; border-left: 3px solid ${scoreColor}; margin-top: 8px;">
        <div style="font-weight: bold; color: ${scoreColor}; font-size: 1.1rem; margin-bottom: 4px;">${res.score}% Match</div>
        <div style="font-size: 0.85rem; color: var(--fog);">${escapeHtml(res.reason)}</div>
      </div>
    `;
  } catch (err) {
    alert("Failed to calculate score: " + err.message);
    btn.textContent = "🎯 Calculate Predictive Fit Score";
    btn.disabled = false;
  }
}

async function selectDirectoryCareer(globalCareerId, btn) {
  const originalText = btn.textContent;
  btn.textContent = "Selecting...";
  btn.disabled = true;

  try {
    const res = await apiRequest("/api/career/directory/select", {
      method: "POST",
      body: { global_career_id: globalCareerId }
    });
    // Redirect to learning planner after successfully selecting
    window.location.href = "learning-planner.html";
  } catch (err) {
    console.error("Selection failed", err);
    alert(err.message || "Failed to select career.");
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
