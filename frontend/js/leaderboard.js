/* =========================================================================
   leaderboard.js
   Loads GET /api/leaderboard and renders the ranked table. Points formula
   (streak days + badges*5 + completed phases*10) is computed server-side;
   this file only displays what comes back.
   ========================================================================= */

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();

  const emptyState = document.getElementById("emptyState");
  const boardCard = document.getElementById("boardCard");
  const tbody = document.getElementById("leaderboardBody");

  try {
    const data = await apiRequest("/api/leaderboard");
    if (!data.entries || data.entries.length === 0) {
      emptyState.classList.remove("hidden");
      return;
    }

    boardCard.classList.remove("hidden");
    tbody.innerHTML = data.entries.map((e) => `
      <tr style="border-bottom:1px solid var(--border,#eee);${e.is_you ? "background:rgba(204,107,60,0.08);font-weight:600;" : ""}">
        <td style="padding:10px 8px;">${e.rank}</td>
        <td style="padding:10px 8px;">${escapeHtml(e.name)}${e.is_you ? " (you)" : ""}</td>
        <td style="padding:10px 8px;">${e.current_streak}d</td>
        <td style="padding:10px 8px;">${e.longest_streak}d</td>
        <td style="padding:10px 8px;">${e.badge_count}</td>
        <td style="padding:10px 8px;">${e.phases_completed}</td>
        <td style="padding:10px 8px;">${e.points}</td>
      </tr>
    `).join("");
  } catch (err) {
    emptyState.classList.remove("hidden");
    emptyState.querySelector("h3").textContent = "Couldn't load the leaderboard";
    emptyState.querySelector("p").textContent = err.message;
  }

  // --- Gamification: Add Friend ---
  const addFriendBtn = document.getElementById("addFriendBtn");
  const friendUsernameInput = document.getElementById("friendUsernameInput");
  const addFriendMsg = document.getElementById("addFriendMsg");

  if (addFriendBtn) {
    addFriendBtn.addEventListener("click", async () => {
      const username = friendUsernameInput.value.trim();
      if (!username) return;
      
      addFriendBtn.disabled = true;
      try {
        const res = await apiRequest("/api/friends/add", {
          method: "POST",
          body: { friend_username: username }
        });
        addFriendMsg.textContent = res.message;
        addFriendMsg.style.color = "var(--accent)";
        friendUsernameInput.value = "";
      } catch (err) {
        addFriendMsg.textContent = err.message;
        addFriendMsg.style.color = "var(--error, #e53e3e)";
      } finally {
        addFriendBtn.disabled = false;
        setTimeout(() => { addFriendMsg.textContent = ""; }, 3000);
      }
    });
  }

  // --- Gamification: Activity Feed ---
  const activityFeed = document.getElementById("activityFeed");
  if (activityFeed) {
    try {
      const data = await apiRequest("/api/friends/activity");
      if (!data.activities || data.activities.length === 0) {
        activityFeed.innerHTML = '<span class="hint">No recent activity from friends.</span>';
      } else {
        activityFeed.innerHTML = data.activities.map(a => `
          <div style="padding: 10px; border-bottom: 1px solid var(--border-subtle);">
            <div style="font-weight: 600;">${escapeHtml(a.name)}</div>
            <div style="font-size: 0.9rem; color: var(--fog);">Earned badge 🏅 <strong>${escapeHtml(a.badge_name)}</strong></div>
            <div style="font-size: 0.75rem; color: var(--hint); margin-top: 4px;">${new Date(a.awarded_at).toLocaleDateString()}</div>
          </div>
        `).join("");
      }
    } catch (err) {
      activityFeed.innerHTML = '<span class="hint">Failed to load activity.</span>';
    }
  }
});
