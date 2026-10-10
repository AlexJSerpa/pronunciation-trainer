let cards = [];
let currentIndex = 0;
let currentCard = null;

let clozeWord = "";
let baseWord = "";
let sentenceText = "";
let isWordVerified = false;

let recorder = null;
let chunks = [];
let isRecording = false;
let timerInterval = null;
let recordingStartTime = 0;
let userAudioBlobUrl = null;

// DOM Elements
const cardCounterEl = document.getElementById("cardCounter");
const cardIdBadgeEl = document.getElementById("cardIdBadge");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const randomBtn = document.getElementById("randomBtn");
const nextCardBottomBtn = document.getElementById("nextCardBottomBtn");

// Step 1 Elements
const step1ContainerEl = document.getElementById("step1Container");
const clozeSentenceEl = document.getElementById("clozeSentence");
const partOfSpeechEl = document.getElementById("partOfSpeech");
const definitionTextEl = document.getElementById("definitionText");
const typingFormEl = document.getElementById("typingForm");
const wordInputEl = document.getElementById("wordInput");
const checkWordBtn = document.getElementById("checkWordBtn");
const revealWordBtn = document.getElementById("revealWordBtn");
const typingFeedbackEl = document.getElementById("typingFeedback");

// Step 2 Elements
const step2ContainerEl = document.getElementById("step2Container");
const targetSentenceEl = document.getElementById("targetSentence");
const playSentenceAudioBtn = document.getElementById("playSentenceAudioBtn");
const playWordAudioBtn = document.getElementById("playWordAudioBtn");
const recordBtn = document.getElementById("recordBtn");
const recordBtnText = document.getElementById("recordBtnText");
const recordingTimerEl = document.getElementById("recordingTimer");
const loadingStatusEl = document.getElementById("loadingStatus");
const errorMessageEl = document.getElementById("errorMessage");

// Feedback Elements
const feedbackSectionEl = document.getElementById("feedbackSection");
const scoreBadgeEl = document.getElementById("scoreBadge");
const resultBoxEl = document.getElementById("result");
const heardTextEl = document.getElementById("heardText");
const extrasRowEl = document.getElementById("extrasRow");
const extrasTextEl = document.getElementById("extrasText");
const userAudioContainerEl = document.getElementById("userAudioContainer");
const userAudioPlayerEl = document.getElementById("userAudioPlayer");

// Initialize
async function init() {
  try {
    const res = await fetch("/api/cards");
    if (!res.ok) throw new Error("Failed to load cards: " + res.statusText);
    cards = await res.json();
    if (!cards || cards.length === 0) {
      showError("No cards found in database.");
      return;
    }
    showCard(0);
  } catch (err) {
    showError("Could not connect to server: " + err.message);
  }
}

// Display Card
function showCard(index) {
  if (index < 0) index = 0;
  if (index >= cards.length) index = cards.length - 1;
  currentIndex = index;
  currentCard = cards[currentIndex];

  cardCounterEl.textContent = `Card ${currentIndex + 1} of ${cards.length}`;
  cardIdBadgeEl.textContent = `#${currentIndex + 1}`;

  baseWord = (currentCard.word || "").trim();
  sentenceText = (currentCard.example || currentCard.text || baseWord).trim();
  
  // Extract cloze target word
  const rawCloze = currentCard.example_cloze || "";
  const clozeMatch = rawCloze.match(/\{\{c\d+::([^}]+)\}\}/);
  if (clozeMatch) {
    clozeWord = clozeMatch[1].trim();
  } else {
    clozeWord = baseWord;
  }

  // Build sentence with cloze blank
  setupClozeView();

  // Definition & POS hints
  partOfSpeechEl.textContent = currentCard.part_of_speech ? `(${currentCard.part_of_speech}) ` : "";
  definitionTextEl.textContent = currentCard.definition || currentCard.answer || "";

  // Reset Step 1 input
  wordInputEl.value = "";
  wordInputEl.disabled = false;
  wordInputEl.classList.remove("input-error", "input-success");
  typingFeedbackEl.hidden = true;
  typingFeedbackEl.textContent = "";
  checkWordBtn.disabled = false;
  revealWordBtn.disabled = false;

  // Lock Step 2 initially
  isWordVerified = false;
  step2ContainerEl.classList.add("step-locked");
  recordBtn.disabled = true;
  targetSentenceEl.textContent = sentenceText;

  // Clear audio & recording feedback
  clearError();
  feedbackSectionEl.hidden = true;
  if (userAudioBlobUrl) {
    URL.revokeObjectURL(userAudioBlobUrl);
    userAudioBlobUrl = null;
  }
  userAudioContainerEl.hidden = true;

  // Focus typing input
  setTimeout(() => wordInputEl.focus(), 50);
}

function setupClozeView() {
  clozeSentenceEl.replaceChildren();

  // If we have an exact cloze template:
  const rawCloze = currentCard.example_cloze || "";
  const match = rawCloze.match(/^(.*?)\{\{c\d+::([^}]+)\}\}(.*)$/);

  if (match) {
    const before = match[1];
    const after = match[3];

    clozeSentenceEl.appendChild(document.createTextNode(before));
    
    const blankSpan = document.createElement("span");
    blankSpan.className = "cloze-blank";
    blankSpan.id = "clozeBlank";
    blankSpan.textContent = "_______";
    clozeSentenceEl.appendChild(blankSpan);

    clozeSentenceEl.appendChild(document.createTextNode(after));
  } else if (sentenceText && baseWord) {
    // Replace first occurrence of baseWord in sentenceText
    const regex = new RegExp(`\\b${baseWord}\\b`, "i");
    const parts = sentenceText.split(regex);
    if (parts.length > 1) {
      clozeSentenceEl.appendChild(document.createTextNode(parts[0]));

      const blankSpan = document.createElement("span");
      blankSpan.className = "cloze-blank";
      blankSpan.id = "clozeBlank";
      blankSpan.textContent = "_______";
      clozeSentenceEl.appendChild(blankSpan);

      clozeSentenceEl.appendChild(document.createTextNode(parts.slice(1).join(baseWord)));
    } else {
      clozeSentenceEl.textContent = sentenceText;
    }
  } else {
    clozeSentenceEl.textContent = sentenceText;
  }
}

// Clean text helper for matching
function normalizeWord(str) {
  return (str || "")
    .toLowerCase()
    .replace(/[^\w]/g, "")
    .trim();
}

// Step 1: Check Typed Word
function checkWord() {
  if (isWordVerified) return;

  const typed = normalizeWord(wordInputEl.value);
  if (!typed) {
    wordInputEl.focus();
    return;
  }

  const expectedCloze = normalizeWord(clozeWord);
  const expectedBase = normalizeWord(baseWord);

  if (typed === expectedCloze || typed === expectedBase) {
    onWordCorrect(clozeWord || baseWord);
  } else {
    onWordIncorrect();
  }
}

function onWordCorrect(wordToDisplay) {
  isWordVerified = true;
  wordInputEl.disabled = true;
  wordInputEl.classList.remove("input-error");
  wordInputEl.classList.add("input-success");
  checkWordBtn.disabled = true;
  revealWordBtn.disabled = true;

  // Replace blank in cloze with green word
  const blankEl = document.getElementById("clozeBlank");
  if (blankEl) {
    blankEl.className = "cloze-filled";
    blankEl.textContent = wordToDisplay;
  }

  // Show success feedback
  typingFeedbackEl.className = "typing-feedback feedback-success";
  typingFeedbackEl.textContent = "✓ Correct! Now read the sentence aloud.";
  typingFeedbackEl.hidden = false;

  // Unlock Step 2
  unlockStep2();
}

function onWordIncorrect() {
  wordInputEl.classList.add("input-error");
  typingFeedbackEl.className = "typing-feedback feedback-error";
  typingFeedbackEl.textContent = "✗ Incorrect. Try again!";
  typingFeedbackEl.hidden = false;

  setTimeout(() => {
    wordInputEl.classList.remove("input-error");
  }, 600);

  wordInputEl.focus();
  wordInputEl.select();
}

function revealWord() {
  const answer = clozeWord || baseWord;
  wordInputEl.value = answer;
  onWordCorrect(answer);
  typingFeedbackEl.className = "typing-feedback feedback-info";
  typingFeedbackEl.textContent = `Word revealed: "${answer}". Practice reading the sentence below.`;
}

function unlockStep2() {
  step2ContainerEl.classList.remove("step-locked");
  recordBtn.disabled = false;
  // Smooth scroll to Step 2 if needed
  step2ContainerEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Audio Playback
function playSentenceAudio() {
  const audioFile = currentCard.example_audio || (currentCard.audio && currentCard.audio[0]);
  if (!audioFile) {
    showError("No audio recording available for this sentence.");
    return;
  }
  const audio = new Audio("/media/" + encodeURIComponent(audioFile));
  audio.play().catch(err => {
    showError("Could not play sentence audio: " + err.message);
  });
}

function playWordAudio() {
  const audioFile = currentCard.word_audio || (currentCard.audio && currentCard.audio[0]);
  if (!audioFile) {
    showError("No audio recording available for this word.");
    return;
  }
  const audio = new Audio("/media/" + encodeURIComponent(audioFile));
  audio.play().catch(err => {
    showError("Could not play word audio: " + err.message);
  });
}

// Step 2: Audio Recording & Verification
async function toggleRecording() {
  if (!isWordVerified) {
    showError("Please complete Step 1 (type the correct word) before recording.");
    wordInputEl.focus();
    return;
  }

  if (isRecording) {
    stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  clearError();
  feedbackSectionEl.hidden = true;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError("Microphone access is not supported by your browser or requires HTTPS / localhost.");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    let mimeType = "";
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      mimeType = "audio/webm;codecs=opus";
    } else if (MediaRecorder.isTypeSupported("audio/webm")) {
      mimeType = "audio/webm";
    } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
      mimeType = "audio/mp4";
    }

    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    chunks = [];

    recorder.ondataavailable = e => {
      if (e.data && e.data.size > 0) {
        chunks.push(e.data);
      }
    };

    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      clearInterval(timerInterval);
      recordingTimerEl.hidden = true;
      recordBtn.classList.remove("recording");
      recordBtnText.textContent = "Record";
      isRecording = false;

      const blobType = recorder.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type: blobType });

      if (blob.size < 100) {
        showError("Recording is too short or empty. Please speak clearly.");
        return;
      }

      // Replay user's audio
      if (userAudioBlobUrl) URL.revokeObjectURL(userAudioBlobUrl);
      userAudioBlobUrl = URL.createObjectURL(blob);
      userAudioPlayerEl.src = userAudioBlobUrl;
      userAudioContainerEl.hidden = false;

      await sendRecording(blob);
    };

    recorder.start();
    isRecording = true;
    recordBtn.classList.add("recording");
    recordBtnText.textContent = "Stop";

    recordingStartTime = Date.now();
    recordingTimerEl.hidden = false;
    recordingTimerEl.textContent = "00:00";
    timerInterval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - recordingStartTime) / 1000);
      const m = String(Math.floor(elapsedSec / 60)).padStart(2, "0");
      const s = String(elapsedSec % 60).padStart(2, "0");
      recordingTimerEl.textContent = `${m}:${s}`;
    }, 500);

  } catch (err) {
    showError("Microphone error: " + err.message);
  }
}

function stopRecording() {
  if (recorder && recorder.state !== "inactive") {
    recorder.stop();
  }
}

async function sendRecording(blob) {
  loadingStatusEl.hidden = false;
  clearError();

  const fd = new FormData();
  fd.append("card_id", currentCard.id);
  // Send the full sentence as the target to pronounce
  fd.append("target_text", sentenceText);
  const ext = blob.type.includes("mp4") ? "m4a" : "webm";
  fd.append("audio", blob, `recording.${ext}`);

  try {
    const res = await fetch("/api/check", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showError(data.detail || "Server error while evaluating pronunciation.");
      return;
    }
    renderResult(data);
  } catch (err) {
    showError("Network or server error: " + err.message);
  } finally {
    loadingStatusEl.hidden = true;
  }
}

function renderResult(result) {
  feedbackSectionEl.hidden = false;
  resultBoxEl.replaceChildren();

  // Words list
  for (const w of result.words || []) {
    const span = document.createElement("span");
    span.textContent = w.word + " ";
    span.className = "w-" + w.status; // correct | close | wrong | missing
    if (w.heard) {
      span.title = `heard: "${w.heard}" (${w.status})`;
    } else if (w.status === "missing") {
      span.title = "missing";
    }
    resultBoxEl.appendChild(span);
  }

  // Heard text
  heardTextEl.textContent = result.heard ? `"${result.heard}"` : "(none)";

  // Extras
  if (result.extras && result.extras.length > 0) {
    extrasTextEl.textContent = result.extras.join(" ");
    extrasRowEl.hidden = false;
  } else {
    extrasRowEl.hidden = true;
  }

  // Score
  const pct = Math.round((result.score || 0) * 100);
  scoreBadgeEl.textContent = `${pct}%`;
  scoreBadgeEl.className = "score-badge " + (pct >= 80 ? "score-high" : pct >= 50 ? "score-mid" : "score-low");
}

function showError(msg) {
  errorMessageEl.textContent = msg;
  errorMessageEl.hidden = false;
}

function clearError() {
  errorMessageEl.hidden = true;
  errorMessageEl.textContent = "";
}

// Event Listeners
typingFormEl.addEventListener("submit", e => {
  e.preventDefault();
  checkWord();
});

revealWordBtn.addEventListener("click", revealWord);
playSentenceAudioBtn.addEventListener("click", playSentenceAudio);
playWordAudioBtn.addEventListener("click", playWordAudio);
recordBtn.addEventListener("click", toggleRecording);

prevBtn.addEventListener("click", () => {
  if (currentIndex > 0) showCard(currentIndex - 1);
});

nextBtn.addEventListener("click", () => {
  if (currentIndex < cards.length - 1) showCard(currentIndex + 1);
});

nextCardBottomBtn.addEventListener("click", () => {
  if (currentIndex < cards.length - 1) {
    showCard(currentIndex + 1);
  } else {
    showCard(0);
  }
});

randomBtn.addEventListener("click", () => {
  if (cards.length <= 1) return;
  let nextIdx;
  do {
    nextIdx = Math.floor(Math.random() * cards.length);
  } while (nextIdx === currentIndex && cards.length > 1);
  showCard(nextIdx);
});

// Keyboard Shortcuts
document.addEventListener("keydown", e => {
  if (document.activeElement === wordInputEl) {
    if (e.key === "Enter") {
      e.preventDefault();
      checkWord();
    }
    return;
  }

  if (e.code === "Space") {
    if (isWordVerified) {
      e.preventDefault();
      toggleRecording();
    }
  } else if (e.key === "p" || e.key === "P") {
    e.preventDefault();
    playSentenceAudio();
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    if (currentIndex > 0) showCard(currentIndex - 1);
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    if (currentIndex < cards.length - 1) showCard(currentIndex + 1);
  } else if (e.key === "r" || e.key === "R") {
    e.preventDefault();
    randomBtn.click();
  }
});

// Start app
init();
