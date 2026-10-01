/* =========================================================================
   interview.js
   Powers mock-interview.html:
     1. Loads the student's selected career (via /api/dashboard).
     2. "Start" -> POST /api/interview/start -> shows one question at a time
        with a countdown timer.
     3. Each answer -> POST /api/interview/answer -> shows instant AI
        feedback, then advances to the next question.
     4. After the last question -> POST /api/interview/finish -> shows an
        overall readiness readout.
     5. Also lists past sessions via GET /api/interview/history.
   ========================================================================= */

document.addEventListener("DOMContentLoaded", async () => {
  Auth.requireLogin();

  const noCareerState = document.getElementById("noCareerState");
  const startCard = document.getElementById("startCard");
  const careerNameText = document.getElementById("careerNameText");
  const startErrorBanner = document.getElementById("startErrorBanner");
  const startBtn = document.getElementById("startBtn");
  const loadingStartCard = document.getElementById("loadingStartCard");

  const questionCard = document.getElementById("questionCard");
  const questionProgressText = document.getElementById("questionProgressText");
  const questionTimer = document.getElementById("questionTimer");
  const questionTypeBadge = document.getElementById("questionTypeBadge");
  const questionText = document.getElementById("questionText");
  const answerInput = document.getElementById("answerInput");
  const interviewSpeakBtn = document.getElementById("interviewSpeakBtn");
  const answerErrorBanner = document.getElementById("answerErrorBanner");
  const submitAnswerBtn = document.getElementById("submitAnswerBtn");

  const loadingFeedbackCard = document.getElementById("loadingFeedbackCard");
  const feedbackCard = document.getElementById("feedbackCard");
  const feedbackScore = document.getElementById("feedbackScore");
  const feedbackText = document.getElementById("feedbackText");
  const feedbackStrengths = document.getElementById("feedbackStrengths");
  const feedbackImprovements = document.getElementById("feedbackImprovements");
  const nextBtn = document.getElementById("nextBtn");

  const loadingSummaryCard = document.getElementById("loadingSummaryCard");
  const summaryCard = document.getElementById("summaryCard");
  const overallScore = document.getElementById("overallScore");
  const overallSummaryText = document.getElementById("overallSummaryText");
  const overallStrengths = document.getElementById("overallStrengths");
  const overallImprovements = document.getElementById("overallImprovements");
  const restartBtn = document.getElementById("restartBtn");

  const historyCard = document.getElementById("historyCard");
  const historyList = document.getElementById("historyList");

  let sessionId = null;
  let questions = [];
  let currentIndex = 0;
  let timerInterval = null;
  let questionStartTime = null;

  // Setup Web Speech API
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true; // allow longer pauses
    recognition.interimResults = true;
    recognition.lang = 'en-US';
  } else {
    interviewSpeakBtn.style.display = 'none'; // Hide if unsupported
  }

  let isListening = false;
  let finalTranscript = '';

  if (interviewSpeakBtn && recognition) {
    interviewSpeakBtn.addEventListener("click", () => {
      if (isListening) {
        recognition.stop();
        return;
      }
      isListening = true;
      finalTranscript = answerInput.value; // Keep existing text
      if (finalTranscript && !finalTranscript.endsWith(' ')) finalTranscript += ' ';
      interviewSpeakBtn.textContent = "🎙️ (Listening...)";
      interviewSpeakBtn.classList.add('recording');
      recognition.start();
    });

    recognition.onresult = (event) => {
      let interimTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript + ' ';
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }
      answerInput.value = finalTranscript + interimTranscript;
    };

    recognition.onend = () => {
      isListening = false;
      interviewSpeakBtn.textContent = "🎤";
      interviewSpeakBtn.classList.remove('recording');
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      isListening = false;
      interviewSpeakBtn.textContent = "🎤";
      interviewSpeakBtn.classList.remove('recording');
    };
  }

  // Step 1: does the student have a selected career?
  let selectedCareerName = null;
  try {
    const dashboard = await apiRequest("/api/dashboard");
    if (dashboard.selected_career) {
      selectedCareerName = dashboard.selected_career.career_name;
    }
  } catch (_) { /* fall through to noCareerState below */ }

  if (!selectedCareerName) {
    noCareerState.classList.remove("hidden");
    return;
  }
  startCard.classList.remove("hidden");
  careerNameText.textContent = selectedCareerName;
  console.debug('interview: selected career', selectedCareerName);
  await loadHistory();

  startBtn.addEventListener("click", () => startInterview());
  restartBtn.addEventListener("click", () => {
    resetToStart();
    startInterview();
  });

  async function startInterview() {
    hideBanner(startErrorBanner);
    console.debug('interview: starting interview request');
    startCard.classList.add("hidden");
    summaryCard.classList.add("hidden");
    historyCard.classList.add("hidden");
    loadingStartCard.classList.remove("hidden");
    startBtn.disabled = true;

    try {
      const data = await apiRequest("/api/interview/start", { method: "POST", body: {} });
      console.debug('interview: start response', data);
      sessionId = data.session_id;
      questions = data.questions;
      currentIndex = 0;
      showQuestion();
    } catch (err) {
      startCard.classList.remove("hidden");
      console.error('interview: start failed', err);
      showBanner(startErrorBanner, err.message);
    } finally {
      loadingStartCard.classList.add("hidden");
      startBtn.disabled = false;
    }
  }

  function showQuestion() {
    const q = questions[currentIndex];
    questionProgressText.textContent = `Question ${currentIndex + 1} of ${questions.length}`;
    questionTypeBadge.textContent = q.type === "technical" ? "Technical" : "Behavioral";
    questionText.textContent = q.question;
    answerInput.value = "";
    answerInput.disabled = false;
    submitAnswerBtn.disabled = false;
    hideBanner(answerErrorBanner);

    feedbackCard.classList.add("hidden");
    questionCard.classList.remove("hidden");

    startTimer(q.time_limit_seconds);
  }

  function startTimer(seconds) {
    clearInterval(timerInterval);
    let remaining = seconds;
    questionStartTime = Date.now();
    updateTimerText(remaining);
    timerInterval = setInterval(() => {
      remaining -= 1;
      updateTimerText(remaining);
      if (remaining <= 0) {
        clearInterval(timerInterval);
        answerInput.disabled = true;
        submitAnswerBtn.disabled = true;
        submitAnswer(true);
      }
    }, 1000);
  }

  function updateTimerText(remaining) {
    const m = Math.max(0, Math.floor(remaining / 60));
    const s = Math.max(0, remaining % 60);
    questionTimer.textContent = `${m}:${s.toString().padStart(2, "0")}`;
  }

  submitAnswerBtn.addEventListener("click", () => submitAnswer(false));

  async function submitAnswer(timedOut) {
    clearInterval(timerInterval);
    if (isListening) recognition.stop();
    hideBanner(answerErrorBanner);
    console.debug('interview: submitting answer', { index: currentIndex, timedOut });
    const answerText = answerInput.value.trim();
    if (!timedOut && answerText.length === 0) {
      showBanner(answerErrorBanner, "Please type an answer (or wait for the timer to run out).");
      startTimer(1); // keep countdown from breaking if they had time left; minimal fallback
      return;
    }

    questionCard.classList.add("hidden");
    loadingFeedbackCard.classList.remove("hidden");

    const timeTaken = Math.round((Date.now() - questionStartTime) / 1000);

    try {
      const feedback = await apiRequest("/api/interview/answer", {
        method: "POST",
        body: {
          session_id: sessionId,
          index: questions[currentIndex].index,
          answer: answerText || "(no answer - time ran out)",
          time_taken_seconds: timeTaken,
        },
      });
      console.debug('interview: answer feedback', feedback);
      renderFeedback(feedback);
    } catch (err) {
      questionCard.classList.remove("hidden");
      console.error('interview: submitAnswer failed', err);
      showBanner(answerErrorBanner, err.message);
    } finally {
      loadingFeedbackCard.classList.add("hidden");
    }
  }

  function renderFeedback(feedback) {
    feedbackScore.textContent = feedback.score;
    feedbackText.textContent = feedback.feedback;
    feedbackStrengths.innerHTML = feedback.strengths.length
      ? feedback.strengths.map((s) => `<span class="skill-chip skill-chip-matched">✓ ${escapeHtml(s)}</span>`).join("")
      : `<p class="hint" style="margin:0;">Nothing specific noted this time.</p>`;
    feedbackImprovements.innerHTML = feedback.improvements.length
      ? feedback.improvements.map((s) => `<span class="skill-chip skill-chip-missing">${escapeHtml(s)}</span>`).join("")
      : `<p class="hint" style="margin:0;">Nothing specific noted this time.</p>`;

    nextBtn.textContent = currentIndex + 1 < questions.length ? "Next question" : "See overall results";
    feedbackCard.classList.remove("hidden");
  }

  nextBtn.addEventListener("click", () => {
    currentIndex += 1;
    if (currentIndex < questions.length) {
      showQuestion();
    } else {
      finishInterview();
    }
  });

  async function finishInterview() {
    feedbackCard.classList.add("hidden");
    loadingSummaryCard.classList.remove("hidden");
    console.debug('interview: finishing interview', { sessionId });

    try {
      const result = await apiRequest("/api/interview/finish", {
        method: "POST",
        body: { session_id: sessionId },
      });
      renderSummary(result.overall_feedback, result.overall_score);
      await loadHistory();
    } catch (err) {
      loadingSummaryCard.classList.add("hidden");
      startCard.classList.remove("hidden");
      console.error('interview: finish failed', err);
      showBanner(startErrorBanner, err.message);
    } finally {
      loadingSummaryCard.classList.add("hidden");
    }
  }

  function renderSummary(summary, score) {
    overallScore.textContent = score;
    overallSummaryText.textContent = summary.summary;
    overallStrengths.innerHTML = summary.strengths.length
      ? summary.strengths.map((s) => `<span class="skill-chip skill-chip-matched">✓ ${escapeHtml(s)}</span>`).join("")
      : `<p class="hint" style="margin:0;">—</p>`;
    overallImprovements.innerHTML = summary.improvements.length
      ? summary.improvements.map((s) => `<span class="skill-chip skill-chip-missing">${escapeHtml(s)}</span>`).join("")
      : `<p class="hint" style="margin:0;">—</p>`;
    summaryCard.classList.remove("hidden");
  }

  function resetToStart() {
    summaryCard.classList.add("hidden");
    startCard.classList.remove("hidden");
  }

  async function loadHistory() {
    try {
      const data = await apiRequest("/api/interview/history");
      console.debug('interview: history', data);
      if (!data.sessions || data.sessions.length === 0) return;
      historyList.innerHTML = data.sessions.map((s) => `
        <div class="course-item">
          <div class="course-item-head">
            <span class="phase-badge">${escapeHtml(s.status)}</span>
            ${s.overall_score != null ? `<span class="phase-badge">${s.overall_score}/100</span>` : ""}
          </div>
          <h4 class="mt-0" style="margin-bottom:2px;">${escapeHtml(s.career_name)}</h4>
          <p class="hint" style="margin:0;">${escapeHtml(s.created_at)}</p>
        </div>
      `).join("");
      historyCard.classList.remove("hidden");
    } catch (_) { /* no history yet, that's fine */ }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }
});
