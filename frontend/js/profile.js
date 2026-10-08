/* =========================================================================
   profile.js
   Loads any existing profile into the form (edit mode), and saves the
   form via POST /api/profile (which upserts on the backend). After a
   successful save with no career_goal set, sends the student to the
   Career Advisor; otherwise straight to the Learning Planner.
   ========================================================================= */

document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();



  const errorBanner = document.getElementById("errorBanner");
  const successBanner = document.getElementById("successBanner");
  const form = document.getElementById("profileForm");
  const submitBtn = document.getElementById("submitBtn");

  // Try to preload an existing profile so returning students can edit it
  try {
    const existing = await apiRequest("/api/profile");
    document.getElementById("name").value = existing.name || "";
    document.getElementById("education").value = existing.education || "";
    document.getElementById("department").value = existing.department || "";
    document.getElementById("college").value = existing.college || "";
    document.getElementById("current_year").value = existing.current_year || "";
    document.getElementById("skills").value = existing.skills || "";
    document.getElementById("interests").value = existing.interests || "";
    document.getElementById("daily_study_hours").value = existing.daily_study_hours || "";
    document.getElementById("career_goal").value = existing.career_goal || "";
  } catch (_) {
    // No profile yet - that's fine, the form just starts blank.
    const user = Auth.getUser();
    if (user) document.getElementById("name").value = user.name;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner(errorBanner);
    hideBanner(successBanner);
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";

    const hoursInput = document.getElementById("daily_study_hours").value;
    const parsedHours = parseFloat(hoursInput);

    const payload = {
      name: document.getElementById("name").value.trim() || (Auth.getUser() ? Auth.getUser().name : "Student"),
      education: document.getElementById("education").value || "Other",
      department: document.getElementById("department").value.trim() || "General",
      college: document.getElementById("college").value.trim() || "College",
      current_year: document.getElementById("current_year").value || "1st Year",
      skills: document.getElementById("skills").value.trim() || "General",
      interests: document.getElementById("interests").value.trim() || "General",
      daily_study_hours: isNaN(parsedHours) || parsedHours <= 0 ? 2.0 : parsedHours,
      career_goal: document.getElementById("career_goal").value.trim() || null,
    };

    try {
      const saved = await apiRequest("/api/profile", { method: "POST", body: payload });
      showBanner(successBanner, "Profile saved!");
      setTimeout(() => {
        window.location.href = saved.career_goal ? "learning-planner.html" : "career-advisor.html";
      }, 600);
    } catch (err) {
      if (err.message && (err.message.includes("log in") || err.message.includes("Invalid or expired session"))) {
        Auth.logout();
        return;
      }
      showBanner(errorBanner, err.message || "Failed to save profile. Please try again.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Save profile & continue";
    }
  });


});
