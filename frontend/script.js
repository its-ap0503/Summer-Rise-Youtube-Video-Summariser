let ytPlayer = null;
let isPlayerReady = false;
let ytApiLoaded = false;
let currentVideoId = null;
let currentSummaryData = null;
let answeredCount = 0;
let correctCount = 0;

const summarizeForm = document.getElementById("summarize-form");
const videoUrlInput = document.getElementById("video-url-input");
const submitBtn = document.getElementById("submit-btn");
const btnText = document.getElementById("btn-text");
const btnSpinner = document.getElementById("btn-spinner");
const statusBanner = document.getElementById("status-banner");

const welcomeState = document.getElementById("welcome-state");
const studyWorkspace = document.getElementById("study-workspace");

const lectureTitle = document.getElementById("lecture-title");
const lectureOverview = document.getElementById("lecture-overview");
const videoIdBadge = document.getElementById("video-id-badge");

const notesContainer = document.getElementById("notes-container");
const quizContainer = document.getElementById("quiz-container");
const notesCount = document.getElementById("notes-count");
const quizCount = document.getElementById("quiz-count");
const quizScoreText = document.getElementById("quiz-score-text");
const resetQuizBtn = document.getElementById("reset-quiz-btn");
const copyNotesBtn = document.getElementById("copy-notes-btn");

const historyList = document.getElementById("history-list");
const refreshHistoryBtn = document.getElementById("refresh-history-btn");
const themeToggleBtn = document.getElementById("theme-toggle-btn");
const themeLabel = document.getElementById("theme-label");

// Theme Toggle (Carbon Dark <-> Clean Light)
if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    themeLabel.textContent = next === "dark" ? "Light" : "Dark";
  });
}

// Parse "MM:SS" or "HH:MM:SS" into integer seconds if start_seconds is missing
function parseTimestampToSeconds(timestampStr, explicitSeconds) {
  if (typeof explicitSeconds === "number" && !Number.isNaN(explicitSeconds)) {
    return explicitSeconds;
  }
  if (!timestampStr || typeof timestampStr !== "string") return 0;
  const cleaned = timestampStr.replace(/[\[\]()]/g, "").trim();
  const parts = cleaned.split(":").map((part) => parseInt(part, 10));
  if (parts.some((n) => Number.isNaN(n))) return 0;
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }
  return parts[0] || 0;
}

// Extract 11-char YouTube Video ID from URL if backend omits video_id
function extractYouTubeId(urlOrId) {
  if (!urlOrId) return "";
  if (/^[a-zA-Z0-9_-]{11}$/.test(urlOrId)) return urlOrId;
  const match = urlOrId.match(/(?:v=|\/embed\/|youtu\.be\/|\/shorts\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : "";
}

function ensureYouTubePlayer(videoId) {
  if (!videoId) return;
  if (ytPlayer && isPlayerReady && typeof ytPlayer.cueVideoById === "function") {
    ytPlayer.cueVideoById(videoId);
    return;
  }
  if (window.YT && window.YT.Player && !ytPlayer) {
    ytPlayer = new YT.Player("yt-player", {
      height: "100%",
      width: "100%",
      videoId: videoId,
      playerVars: { playsinline: 1, rel: 0, modestbranding: 1 },
      events: {
        onReady: () => {
          isPlayerReady = true;
        },
      },
    });
  }
}

window.onYouTubeIframeAPIReady = function () {
  ytApiLoaded = true;
  if (currentVideoId) {
    ensureYouTubePlayer(currentVideoId);
  }
};

function seekToTimestamp(seconds) {
  if (ytPlayer && isPlayerReady && typeof ytPlayer.seekTo === "function") {
    ytPlayer.seekTo(seconds, true);
    ytPlayer.playVideo();
  }
}

function showStatus(message, type = "info") {
  statusBanner.textContent = message;
  statusBanner.className = `status-banner ${type}`;
  statusBanner.classList.remove("hidden");
}

function hideStatus() {
  statusBanner.classList.add("hidden");
}

function setLoadingState(isLoading) {
  submitBtn.disabled = isLoading;
  if (isLoading) {
    btnText.textContent = "Processing";
    btnSpinner.classList.remove("hidden");
    showStatus("Extracting transcript & generating structured study guide...", "info");
  } else {
    btnText.textContent = "Summarize";
    btnSpinner.classList.add("hidden");
  }
}

function renderStudyGuide(rawPayload, sourceUrl = "") {
  const videoId = rawPayload.video_id || extractYouTubeId(sourceUrl);
  const notes = rawPayload.notes || rawPayload.sections || rawPayload.timestamps || [];
  const quiz = rawPayload.quiz || rawPayload.questions || [];

  currentSummaryData = {
    ...rawPayload,
    video_id: videoId,
    title: rawPayload.title || "Lecture Study Guide",
    overview: rawPayload.overview || rawPayload.summary || "",
    notes,
    quiz,
  };
  currentVideoId = videoId;

  // Unhide workspace BEFORE initializing/cueing the YouTube iframe
  welcomeState.classList.add("hidden");
  studyWorkspace.classList.remove("hidden");

  lectureTitle.textContent = currentSummaryData.title;
  lectureOverview.textContent = currentSummaryData.overview;
  videoIdBadge.textContent = videoId || "VIDEO";

  ensureYouTubePlayer(videoId);

  notesCount.textContent = notes.length;
  const fragment = document.createDocumentFragment();

  notes.forEach((note) => {
    const card = document.createElement("div");
    card.className = "note-card";

    const header = document.createElement("div");
    header.className = "note-header";

    const displayTime = note.timestamp || "00:00";
    const startSeconds = parseTimestampToSeconds(displayTime, note.start_seconds);

    const timeBtn = document.createElement("button");
    timeBtn.type = "button";
    timeBtn.className = "timestamp-btn";
    timeBtn.textContent = displayTime;
    timeBtn.addEventListener("click", () => seekToTimestamp(startSeconds));

    const heading = document.createElement("h3");
    heading.className = "note-heading";
    heading.textContent = note.heading || note.topic || "Key Concept";

    const summary = document.createElement("p");
    summary.className = "note-summary";
    summary.textContent = note.summary || note.content || "";

    header.appendChild(timeBtn);
    header.appendChild(heading);
    card.appendChild(header);
    card.appendChild(summary);
    fragment.appendChild(card);
  });

  notesContainer.innerHTML = "";
  notesContainer.appendChild(fragment);
  renderQuiz(quiz);
}

function renderQuiz(quizItems) {
  quizCount.textContent = quizItems.length;
  quizContainer.innerHTML = "";
  answeredCount = 0;
  correctCount = 0;
  quizScoreText.textContent = `Score: 0 / ${quizItems.length}`;

  quizItems.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "quiz-card";

    const questionEl = document.createElement("div");
    questionEl.className = "quiz-question";
    questionEl.textContent = `${index + 1}. ${item.question}`;

    const optionsList = document.createElement("div");
    optionsList.className = "quiz-options";

    const explanationEl = document.createElement("div");
    explanationEl.className = "quiz-explanation hidden";
    explanationEl.textContent = item.explanation || "";

    const correctAnswer = item.correct_answer || item.answer;

    (item.options || []).forEach((optionText) => {
      const optBtn = document.createElement("button");
      optBtn.type = "button";
      optBtn.className = "quiz-option-btn";
      optBtn.textContent = optionText;

      optBtn.addEventListener("click", () => {
        optionsList.querySelectorAll(".quiz-option-btn").forEach((btn) => {
          btn.disabled = true;
          if (btn.textContent === correctAnswer) btn.classList.add("correct");
        });

        answeredCount += 1;
        if (optionText === correctAnswer) {
          correctCount += 1;
        } else {
          optBtn.classList.add("wrong");
        }

        if (item.explanation) {
          explanationEl.classList.remove("hidden");
        }
        quizScoreText.textContent = `Score: ${correctCount} / ${quizItems.length} (${answeredCount} answered)`;
      });

      optionsList.appendChild(optBtn);
    });

    card.appendChild(questionEl);
    card.appendChild(optionsList);
    card.appendChild(explanationEl);
    quizContainer.appendChild(card);
  });
}

if (resetQuizBtn) {
  resetQuizBtn.addEventListener("click", () => {
    if (currentSummaryData?.quiz) renderQuiz(currentSummaryData.quiz);
  });
}

if (copyNotesBtn) {
  copyNotesBtn.addEventListener("click", async () => {
    if (!currentSummaryData) return;
    const lines = [
      `# ${currentSummaryData.title}`,
      "",
      currentSummaryData.overview,
      "",
      "## Timestamped Notes",
      ...currentSummaryData.notes.map(
        (n) => `- **[${n.timestamp}] ${n.heading}**: ${n.summary}`
      ),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      const prev = copyNotesBtn.textContent;
      copyNotesBtn.textContent = "Copied!";
      setTimeout(() => {
        copyNotesBtn.textContent = prev;
      }, 1500);
    } catch {
      showStatus("Could not copy notes to clipboard.", "error");
    }
  });
}

async function summarizeByUrl(targetUrl) {
  hideStatus();
  setLoadingState(true);

  try {
    const response = await fetch("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: targetUrl }),
    });

    const rawText = await response.text();
    let data = null;

    try {
      data = JSON.parse(rawText);
    } catch {
      if (rawText.includes("<!DOCTYPE") || response.status === 502 || response.status === 504) {
        showStatus(
          "Upstream timeout or YouTube IP rate-limit on cloud server (502). Try a shorter video or retry in a few seconds.",
          "error"
        );
      } else {
        showStatus(`Server error (${response.status}). Please try again.`, "error");
      }
      return;
    }

    if (!response.ok) {
      showStatus(data.detail || data.error || `Error ${response.status}: Could not summarize video.`, "error");
      return;
    }

    hideStatus();
    renderStudyGuide(data, targetUrl);
    await loadRevisionHistory();
  } catch (error) {
    showStatus(`Network error: ${error.message}`, "error");
  } finally {
    setLoadingState(false);
  }
}

summarizeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = videoUrlInput.value.trim();
  if (!url) {
    showStatus("Please paste a valid YouTube link first.", "error");
    return;
  }
  summarizeByUrl(url);
});

async function loadRevisionHistory() {
  try {
    const response = await fetch("/api/history?limit=20");
    if (!response.ok) return;

    const payload = await response.json();
    const items = payload.items || payload || [];

    if (!Array.isArray(items) || items.length === 0) {
      historyList.innerHTML = `<div class="empty-history">No saved lectures yet.</div>`;
      return;
    }

    historyList.innerHTML = "";
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = `history-item ${item.video_id === currentVideoId ? "active" : ""}`;

      const title = document.createElement("div");
      title.className = "history-item-title";
      title.textContent = item.title || item.video_id;

      const meta = document.createElement("div");
      meta.className = "history-item-meta";
      meta.textContent = item.video_id;

      card.appendChild(title);
      card.appendChild(meta);
      card.addEventListener("click", () => {
        const ytUrl = `https://www.youtube.com/watch?v=${item.video_id}`;
        videoUrlInput.value = ytUrl;
        summarizeByUrl(ytUrl);
      });

      historyList.appendChild(card);
    });
  } catch (err) {
    console.warn("History fetch error:", err);
  }
}

document.querySelectorAll(".tab-btn").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    const targetTab = document.getElementById(button.getAttribute("data-tab"));
    if (targetTab) targetTab.classList.add("active");
  });
});

if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", loadRevisionHistory);
}
document.addEventListener("DOMContentLoaded", loadRevisionHistory);