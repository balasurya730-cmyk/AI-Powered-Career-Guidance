/* =========================================================================
   dashboard.js
   Powers dashboard.html. Pulls everything from a single endpoint,
   GET /api/dashboard, and renders:
     - profile summary
     - selected career (if any)
     - progress percentage + progress bar
     - a checklist of tasks (grouped by daily/weekly/monthly/skill/project)
       that toggle complete/incomplete via POST /api/progress/update.
   ========================================================================= */

const TASK_TYPE_LABELS = {
  daily: "Daily tasks",
  weekly: "Weekly tasks",
  monthly: "Monthly roadmap",
  skill: "Skills to learn",
  project: "Practice project",
};

document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();

  const emptyState = document.getElementById("emptyState");
  const dashboardContent = document.getElementById("dashboardContent");

  try {
    const data = await apiRequest("/api/dashboard");

    if (!data.profile) {
      emptyState.classList.remove("hidden");
      return;
    }

    dashboardContent.classList.remove("hidden");
    renderProfile(data.profile, data.student_code);
    renderCareer(data.selected_career);
    renderProgressSummary(data.progress_percentage, data.progress);
    renderPlanOverview(data.learning_plan);
    renderTasks(data.progress);
    updateCongratsCard(data);
    renderStreaksAndBadges(data);

    // Predictions & Alerts
    const predictionContainer = document.getElementById("predictionContainer");
    const timeToJobWeeks = document.getElementById("timeToJobWeeks");
    const alertsContainer = document.getElementById("alertsContainer");
    
    if (predictionContainer && timeToJobWeeks && data.time_to_job_weeks) {
      predictionContainer.classList.remove("hidden");
      timeToJobWeeks.textContent = data.time_to_job_weeks;
    } else if (predictionContainer) {
      predictionContainer.classList.add("hidden");
    }

    if (alertsContainer) {
      if (data.off_track_alerts && data.off_track_alerts.length > 0) {
        alertsContainer.innerHTML = data.off_track_alerts.map(alert => `
          <div class="card" style="background: rgba(239, 68, 68, 0.05); border-left: 4px solid #ef4444; padding: 12px; margin-bottom: 0;">
            <h4 style="margin: 0 0 4px 0; color: #ef4444;">⚠️ Off-Track Alert</h4>
            <p style="margin: 0; font-size: 0.95rem; color: var(--fog);">${escapeHtml(alert)}</p>
          </div>
        `).join("");
      } else {
        alertsContainer.innerHTML = "";
      }
    }
  } catch (err) {
    emptyState.classList.remove("hidden");
  }

  function renderProfile(profile, studentCode) {
    document.getElementById("dashName").textContent = profile.name;
    const dashCode = document.getElementById("dashStudentCode");
    if (dashCode) {
      dashCode.textContent = studentCode || "—";
    }
    const details = document.getElementById("dashEdu");
    const rows = [
      ["Education", `${profile.education} — ${profile.department}`],
      ["College", profile.college],
      ["Current year", profile.current_year],
      ["Skills", profile.skills],
      ["Interests", profile.interests],
      ["Daily study hours", `${profile.daily_study_hours} hrs/day`],
    ];
    details.innerHTML = rows.map(([label, value]) => `
      <div class="dash-label">${label}</div>
      <div class="dash-value">${escapeHtml(value || "—")}</div>
    `).join("");
    
    const copyBtn = document.getElementById("btnCopyStudentCode");
    if (copyBtn && studentCode) {
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(studentCode);
        const originalText = copyBtn.textContent;
        copyBtn.textContent = "Copied!";
        setTimeout(() => copyBtn.textContent = originalText, 2000);
      });
    }
  }

  function renderCareer(career) {
    if (!career) {
      document.getElementById("noCareerCard").classList.remove("hidden");
      return;
    }
    document.getElementById("careerCard").classList.remove("hidden");
    document.getElementById("careerName").textContent = career.career_name;
    document.getElementById("careerDescription").textContent = career.description;
    document.getElementById("careerSkills").innerHTML = (career.required_skills || [])
      .map((s) => `<span class="skill-chip">${escapeHtml(s)}</span>`).join("");
  }

  function renderProgressSummary(percentage, progress) {
    document.getElementById("progressPercent").textContent = percentage || 0;
    document.getElementById("progressFill").style.width = `${percentage || 0}%`;
    const subtext = document.getElementById("progressSubtext");
    if (!progress || progress.length === 0) {
      subtext.textContent = "No tasks yet — generate a learning plan to get started";
    } else {
      const done = progress.filter((p) => p.is_completed).length;
      subtext.textContent = `${done} of ${progress.length} tasks completed`;
    }
  }

  function renderTasks(progress) {
    const wrap = document.getElementById("taskGroups");
    if (!progress || progress.length === 0) {
      document.getElementById("noPlanCard").classList.remove("hidden");
      return;
    }

    const grouped = {};
    progress.forEach((task) => {
      if (!grouped[task.task_type]) grouped[task.task_type] = [];
      grouped[task.task_type].push(task);
    });

    wrap.innerHTML = "";
    Object.keys(TASK_TYPE_LABELS).forEach((type) => {
      if (!grouped[type]) return;
      const group = document.createElement("div");
      group.className = "task-group";
      group.innerHTML = `
        <span class="task-group-label">${TASK_TYPE_LABELS[type]}</span>
        ${grouped[type].map((task) => `
          <div class="task-item ${task.is_completed ? "completed" : ""}" data-task-id="${task.id}">
            <div class="task-checkbox">${task.is_completed ? checkmarkSvg() : ""}</div>
            <div class="task-text">${escapeHtml(task.task_name)}</div>
          </div>
        `).join("")}
      `;
      wrap.appendChild(group);
    });

    wrap.querySelectorAll(".task-item").forEach((item) => {
      item.addEventListener("click", () => toggleTask(item));
    });
  }

  function renderPlanOverview(plan) {
    const wrap = document.getElementById("planOverview");
    if (!wrap) return;
    if (!plan) {
      wrap.innerHTML = "";
      return;
    }

    const sections = [
      ["Daily tasks", plan.daily_plan],
      ["Weekly tasks", plan.weekly_plan],
      ["Monthly tasks", plan.monthly_roadmap],
      ["Skills to learn", plan.skills_to_learn],
    ];
    const sectionMarkup = sections
      .filter(([, items]) => Array.isArray(items) && items.length)
      .map(([title, items]) => `
        <section class="plan-section">
          <h3>${escapeHtml(title)}</h3>
          <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </section>
      `).join("");
    const projectMarkup = plan.practice_project ? `
      <section class="plan-section plan-project">
        <h3>Practice project</h3>
        <p>${escapeHtml(plan.practice_project)}</p>
      </section>
    ` : "";
    wrap.innerHTML = sectionMarkup + projectMarkup;
  }

  async function toggleTask(itemEl) {
    const taskId = parseInt(itemEl.getAttribute("data-task-id"));
    const willComplete = !itemEl.classList.contains("completed");

    // Optimistic UI update
    itemEl.classList.toggle("completed", willComplete);
    const checkbox = itemEl.querySelector(".task-checkbox");
    checkbox.innerHTML = willComplete ? checkmarkSvg() : "";

    try {
      await apiRequest("/api/progress/update", {
        method: "POST",
        body: { progress_id: taskId, is_completed: willComplete },
      });
      // Refresh the top progress summary from the server for accuracy
      const data = await apiRequest("/api/dashboard");
      renderProgressSummary(data.progress_percentage, data.progress);
      updateCongratsCard(data);
      renderStreaksAndBadges(data);
    } catch (err) {
      // Revert on failure
      itemEl.classList.toggle("completed", !willComplete);
      checkbox.innerHTML = !willComplete ? checkmarkSvg() : "";
      alert("Could not update progress: " + err.message);
    }
  }

  function checkmarkSvg() {
    return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function updateCongratsCard(data) {
    const card = document.getElementById("congratsCard");
    if (!card) return;

    const progress = data.progress;
    if (!progress || progress.length === 0) {
      card.classList.add("hidden");
      return;
    }

    const done = progress.filter((p) => p.is_completed).length;
    const allDone = done === progress.length;

    if (allDone) {
      const titleEl = document.getElementById("congratsTitle");
      const textEl = document.getElementById("congratsText");
      const btnEl = document.getElementById("congratsBtn");

      if (data.has_phases) {
        titleEl.textContent = "Phase Tasks Completed! 🚀";
        textEl.textContent = "All weekly tasks for this phase are done! Head over to your Roadmap to submit your phase-end project and take the proctored test.";
        btnEl.textContent = "Go to my Roadmap";
        btnEl.href = "phases.html";
      } else {
        titleEl.textContent = "All Tasks Completed! 🎉";
        textEl.textContent = "Congratulations on finishing your learning plan! Take the next step and break it into a structured, multi-phase roadmap with projects and proctored tests.";
        btnEl.textContent = "Unlock Phased Roadmap";
        btnEl.href = "phases.html";
      }
      card.classList.remove("hidden");
    } else {
      card.classList.add("hidden");
    }
  }

  function renderStreaksAndBadges(data) {
    document.getElementById("currentStreakVal").textContent = `${data.current_streak || 0} day${data.current_streak === 1 ? "" : "s"}`;
    document.getElementById("longestStreakVal").textContent = data.longest_streak || 0;

    const badgesContainer = document.getElementById("badgesContainer");
    if (!badgesContainer) return;

    if (!data.badges || data.badges.length === 0) {
      badgesContainer.innerHTML = `<span class="hint">Earn streaks and complete phases to unlock badges!</span>`;
      return;
    }

    badgesContainer.innerHTML = data.badges.map((b) => `
      <div class="skill-chip" style="background:rgba(204,107,60,0.15); border:1px solid var(--accent); color:var(--accent); display:inline-flex; align-items:center; gap:5px; padding:6px 12px; font-weight:600;" title="${escapeHtml(b.description)}">
        🏅 ${escapeHtml(b.badge_name)}
      </div>
    `).join("");
  }

  const btnExportResume = document.getElementById("btnExportResume");
  if (btnExportResume) {
    btnExportResume.addEventListener("click", async () => {
      btnExportResume.disabled = true;
      btnExportResume.textContent = "Generating...";
      try {
        const res = await apiRequest("/api/resume/export");
        const blob = new Blob([res.resume_markdown], { type: "text/markdown" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "Resume.md";
        a.click();
      } catch (err) {
        alert("Failed to export resume: " + err.message);
      } finally {
        btnExportResume.disabled = false;
        btnExportResume.textContent = "Export Resume (AI)";
      }
    });
  }

  const btnSharePortfolio = document.getElementById("btnSharePortfolio");
  if (btnSharePortfolio) {
    btnSharePortfolio.addEventListener("click", () => {
      const user = Auth.getUser();
      const slug = user.name.toLowerCase().replace(/\s+/g, '-');
      const url = window.location.origin + "/portfolio/" + slug;
      navigator.clipboard.writeText(url).then(() => {
        alert("Portfolio link copied to clipboard! (Ensure you have set it to public in settings)");
      });
    });
  }

  // --- Peer Search & Recommendations ---
  const btnSearchPeer = document.getElementById("btnSearchPeer");
  const peerSearchInput = document.getElementById("peerSearchInput");
  const peerSearchResult = document.getElementById("peerSearchResult");

  if (btnSearchPeer && peerSearchInput && peerSearchResult) {
    btnSearchPeer.addEventListener("click", async () => {
      const code = peerSearchInput.value.trim();
      if (!code) {
        peerSearchResult.innerHTML = "<span class='hint'>Please enter a code</span>";
        return;
      }
      btnSearchPeer.disabled = true;
      try {
        const res = await apiRequest("/api/users/search?code=" + encodeURIComponent(code));
        if (res.users && res.users.length > 0) {
          peerSearchResult.innerHTML = res.users.map(u => `
            <div style="background:rgba(255,255,255,0.05); padding:8px; border-radius:4px; margin-bottom:8px;">
              <strong>${escapeHtml(u.name)}</strong> <span style="font-size:0.8rem;color:var(--fog);">(${escapeHtml(u.student_code)})</span><br>
              <span class="hint" style="font-size:0.8rem;">Goal: ${escapeHtml(u.career_goal || "Unknown")}</span>
            </div>
          `).join("");
        } else {
          peerSearchResult.innerHTML = "<span class='hint'>No peers found.</span>";
        }
      } catch (err) {
        peerSearchResult.innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
      } finally {
        btnSearchPeer.disabled = false;
      }
    });
  }

  // Fetch AI Peer Recommendations
  fetchPeerRecommendations();

  async function fetchPeerRecommendations() {
    try {
      const res = await apiRequest("/api/peers/recommendations");
      if (res.peers && res.peers.length > 0) {
        // We can render this below the search box
        const recDiv = document.createElement("div");
        recDiv.style.marginTop = "16px";
        recDiv.innerHTML = `
          <h4 style="margin:0 0 8px 0; color:var(--pine-300);">AI Recommended Peers</h4>
          ${res.peers.map(p => `
            <div style="background:rgba(59,130,246,0.1); border-left:2px solid var(--trail); padding:8px; border-radius:4px; margin-bottom:8px;">
              <strong>${escapeHtml(p.name)}</strong> <span style="font-size:0.8rem;color:var(--fog);">(${escapeHtml(p.student_code)})</span><br>
              <span class="hint" style="font-size:0.8rem;">Goal: ${escapeHtml(p.career_goal)}</span>
            </div>
          `).join("")}
        `;
        if (peerSearchResult) {
          peerSearchResult.parentNode.appendChild(recDiv);
        }
      }
    } catch (e) {
      console.warn("Failed to load peer recommendations:", e);
    }
  }

});
