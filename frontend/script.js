
/* ==========================================
   LECTUREAI - FRONTEND JAVASCRIPT
   ========================================== */

let recognition = null;
let listening = false;
let transcript = "";
let lastNotes = null;

const API_URL = "http://127.0.0.1:8000";

const $ = id => document.getElementById(id);


/* ==========================================
   COMMON HELPERS
   ========================================== */

function setStatus(message, isError = false) {
    $("status").textContent = message;
    $("status").style.color = isError
        ? "var(--danger)"
        : "var(--muted)";
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

function syncTranscriptFromEditor() {
    transcript = $("transcript").value;
    updateCounts();
}

function updateCounts() {
    const count = transcript.trim()
        ? transcript.trim().split(/\s+/).length
        : 0;

    $("wordCount").textContent = count;

    $("transcriptCount").textContent =
        count + (count === 1 ? " word" : " words");
}

function updateTranscript() {
    $("transcript").value = transcript;
    updateCounts();
}

$("transcript").addEventListener("input", () => {
    syncTranscriptFromEditor();
    setStatus("Transcript updated. You can generate notes from this text.");
});

function scrollToSection(id) {
    const section = $(id);

    if (section) {
        section.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }
}


/* ==========================================
   MICROPHONE TRANSCRIPTION
   ========================================== */

function toggleMic() {
    if (listening) {
        stopMic();
        return;
    }

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        setStatus(
            "Speech recognition is not supported. Please use Google Chrome.",
            true
        );
        return;
    }

    syncTranscriptFromEditor();

    recognition = new SpeechRecognition();

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = $("lang").value;

    recognition.onresult = event => {
        let interim = "";

        for (
            let i = event.resultIndex;
            i < event.results.length;
            i++
        ) {
            const spokenText =
                event.results[i][0].transcript.trim();

            if (event.results[i].isFinal && spokenText) {
                transcript += (transcript ? " " : "") + spokenText;
            } else {
                interim += spokenText;
            }
        }

        updateTranscript();

        if (interim) {
            $("transcript").value =
                transcript + (transcript ? " " : "") + interim;
        }
    };

    recognition.onerror = event => {
        setStatus("Microphone issue: " + event.error, true);
    };

    recognition.onend = () => {
        if (listening && recognition) {
            try {
                recognition.start();
            } catch (error) {
                console.warn("Recognition restart:", error);
            }
        }
    };

    try {
        recognition.start();

        listening = true;

        $("micBtn").classList.add("recording");
        $("micBtn").textContent = "■";

        $("recordState").textContent = "● LISTENING";
        $("recordState").style.color = "var(--danger)";

        setStatus("Listening... Speak clearly. Click Stop when finished.");

    } catch (error) {
        setStatus("Could not start microphone: " + error.message, true);
    }
}

function stopMic() {
    listening = false;

    if (recognition) {
        recognition.onend = null;
        recognition.stop();
        recognition = null;
    }

    $("micBtn").classList.remove("recording");
    $("micBtn").textContent = "🎙";

    $("recordState").textContent = "● READY";
    $("recordState").style.color = "var(--green)";

    syncTranscriptFromEditor();

    setStatus("Recording stopped. You can edit the transcript or generate notes.");
}


/* ==========================================
   DEMO LECTURE
   ========================================== */

function loadSample() {
    if (listening) {
        stopMic();
    }

    const demoText =
        "Today we will learn about photosynthesis. " +
        "Photosynthesis is the process plants use to make food from sunlight. " +
        "It happens inside chloroplasts, which contain a green pigment called chlorophyll. " +
        "Chlorophyll absorbs light energy, mostly red and blue light. " +
        "The plant takes in carbon dioxide from the air through tiny holes called stomata, " +
        "and water from the soil through the roots. " +
        "Using light energy, the plant converts carbon dioxide and water into glucose and oxygen. " +
        "The oxygen is released into the air. " +
        "The glucose is used as food for growth or stored as starch. " +
        "The process has two stages. First, the light reactions, which happen in the thylakoid membranes and make ATP. " +
        "Second, the Calvin cycle, which happens in the stroma and uses ATP to build glucose. " +
        "Factors that affect photosynthesis are light intensity, carbon dioxide level, and temperature.";

    transcript = demoText;

    updateTranscript();

    $("transcript").focus();

    setStatus("Demo lecture inserted. You can edit or replace this text.");
}


/* ==========================================
   CLEAR SESSION
   ========================================== */

function clearAll() {
    if (listening) {
        stopMic();
    }

    transcript = "";
    lastNotes = null;

    updateTranscript();

    $("notesContent").className = "note-placeholder";
    $("notesContent").innerHTML =
        "<div><span>✧</span>Your structured notes, key concepts and summary will appear here.</div>";

    $("revisionContent").className = "note-placeholder";
    $("revisionContent").innerHTML =
        "<div><span>◈</span>Generate notes to create practice questions with answers.</div>";

    $("chat").innerHTML =
        '<div class="message">Your chat has been cleared. Add a lecture transcript to ask questions.</div>';

    $("questionInput").value = "";
    $("lectureTitle").value = "";

    setStatus("Session cleared. You can now add a new lecture.");
}


/* ==========================================
   API CONNECTION
   ========================================== */

async function requestJSON(path, options = {}) {
    let response;

    try {
        response = await fetch(API_URL + path, options);
    } catch (error) {
        throw new Error(
            "Cannot connect to the backend. Make sure FastAPI is running."
        );
    }

    const contentType = response.headers.get("content-type") || "";

    let data;

    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        data = await response.text();
    }

    if (!response.ok) {
        const detail =
            typeof data === "object"
                ? data.detail || data.error
                : data;

        throw new Error(detail || "The server returned an error.");
    }

    return data;
}

function postJSON(path, body) {
    return requestJSON(path, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
    });
}


/* ==========================================
   GENERATE AI STUDY NOTES
   ========================================== */

async function makeNotes() {
    syncTranscriptFromEditor();

    if (transcript.trim().length < 20) {
        setStatus(
            "Please enter a lecture of at least 20 characters.",
            true
        );
        return;
    }

    const button = $("notesBtn");

    button.disabled = true;
    button.textContent = "Generating...";

    $("notesContent").className = "note-placeholder";
    $("notesContent").textContent =
        "Gemini is organizing your lecture into study materials...";

    setStatus("Sending transcript to Gemini...");

    try {
        const data = await postJSON("/api/notes", {
            transcript: transcript
        });

        lastNotes = data;

        renderNotes(data);
        renderRevision(data.questions || []);

        setStatus("Your notes and practice questions are ready.");

    } catch (error) {
        $("notesContent").textContent =
            "Could not generate notes: " + error.message;

        setStatus(error.message, true);

    } finally {
        button.disabled = false;
        button.textContent = "✦ Generate study notes";
    }
}


/* ==========================================
   DISPLAY AI NOTES
   ========================================== */

function renderNotes(data) {
    let html = `
        <h3>${escapeHTML(data.title || "Lecture notes")}</h3>
        <p>${escapeHTML(data.summary || "")}</p>
        <h3>Key concepts</h3>
        <div>
    `;

    (data.key_concepts || []).forEach(item => {
        html += `
            <div class="concept">
                <b>${escapeHTML(item.term)}</b> —
                ${escapeHTML(item.meaning)}
            </div>
        `;
    });

    html += "</div>";

    (data.notes || []).forEach(section => {
        html += `
            <h3>${escapeHTML(section.heading)}</h3>
            <ul>
        `;

        (section.points || []).forEach(point => {
            html += `<li>${escapeHTML(point)}</li>`;
        });

        html += "</ul>";
    });

    $("notesContent").className = "notes-content";
    $("notesContent").innerHTML = html;
}


/* ==========================================
   REVISION QUESTIONS
   ========================================== */

function renderRevision(questions) {
    if (!questions || questions.length === 0) {
        $("revisionContent").className = "note-placeholder";

        $("revisionContent").textContent =
            "No practice questions were returned. Try generating notes again.";

        return;
    }

    $("revisionContent").className = "notes-content";

    $("revisionContent").innerHTML = questions.map((item, index) => `
        <div class="question">
            <b>Q${index + 1}. ${escapeHTML(item.q)}</b>
            <br>

            <button type="button"
                onclick="toggleAnswer(this)">
                Show / hide answer
            </button>

            <div class="answer">
                ${escapeHTML(item.a)}
            </div>
        </div>
    `).join("");
}

function toggleAnswer(button) {
    const answer = button.nextElementSibling;

    answer.style.display =
        answer.style.display === "block"
            ? "none"
            : "block";
}


/* ==========================================
   ASK YOUR LECTURE
   ========================================== */

async function ask() {
    syncTranscriptFromEditor();

    const question = $("questionInput").value.trim();

    if (!question) {
        return;
    }

    if (!transcript.trim()) {
        setStatus("Add a lecture transcript before asking questions.", true);
        return;
    }

    const chat = $("chat");

    chat.insertAdjacentHTML(
        "beforeend",
        `<div class="message user">${escapeHTML(question)}</div>`
    );

    $("questionInput").value = "";

    chat.insertAdjacentHTML(
        "beforeend",
        '<div class="message" id="thinking">Thinking...</div>'
    );

    chat.scrollTop = chat.scrollHeight;

    try {
        const data = await postJSON("/api/ask", {
            transcript: transcript,
            question: question
        });

        $("thinking")?.remove();

        chat.insertAdjacentHTML(
            "beforeend",
            `<div class="message">${escapeHTML(data.answer || "No answer returned.")}</div>`
        );

    } catch (error) {
        $("thinking")?.remove();

        chat.insertAdjacentHTML(
            "beforeend",
            `<div class="message">Sorry, I couldn't get an answer: ${escapeHTML(error.message)}</div>`
        );
    }

    chat.scrollTop = chat.scrollHeight;
}


/* ==========================================
   MY LECTURES - STATUS AND DATE
   ========================================== */

function setLibraryStatus(message, isError = false) {
    $("libraryStatus").textContent = message;

    $("libraryStatus").style.color = isError
        ? "var(--danger)"
        : "var(--muted)";
}

function formatLectureDate(value) {
    if (!value) {
        return "Date unavailable";
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleString();
}


/* ==========================================
   SAVE LECTURE
   ========================================== */

async function saveLecture() {
    syncTranscriptFromEditor();

    if (transcript.trim().length < 20) {
        setStatus(
            "Add a lecture transcript of at least 20 characters before saving.",
            true
        );
        return;
    }

    const title = $("lectureTitle").value.trim();

    if (!title) {
        $("lectureTitle").focus();

        setStatus(
            "Please enter a title for this lecture before saving.",
            true
        );

        return;
    }

    const button = $("saveLectureBtn");

    button.disabled = true;
    button.textContent = "Saving...";

    try {
        const result = await postJSON("/api/lectures", {
            title: title,
            transcript: transcript,
            notes: lastNotes
        });

        setStatus("Lecture saved successfully: " + result.title);

        setLibraryStatus("Your lecture was saved.");

        $("lectureTitle").value = "";

        await loadLectures();

    } catch (error) {
        setStatus("Could not save lecture: " + error.message, true);

        setLibraryStatus(error.message, true);

    } finally {
        button.disabled = false;
        button.textContent = "▣ Save lecture";
    }
}


/* ==========================================
   LOAD ALL SAVED LECTURES
   ========================================== */

async function loadLectures() {
    const list = $("lectureList");

    list.innerHTML =
        '<div class="empty-library">Loading saved lectures...</div>';

    try {
        const data = await requestJSON("/api/lectures");

const lectures = Array.isArray(data)
    ? data
    : (data.lectures || []);

        if (!Array.isArray(lectures) || lectures.length === 0) {
            list.innerHTML = `
                <div class="empty-library">
                    No saved lectures yet. Add a transcript and select Save lecture.
                </div>
            `;

            setLibraryStatus("0 saved lectures.");
            return;
        }

        list.innerHTML = lectures.map(lecture => `
            <div class="lecture-item">

                <div>
                    <strong>${escapeHTML(lecture.title)}</strong>

                    <small>
                        Saved: ${escapeHTML(formatLectureDate(lecture.created_at))}
                        · ID: ${Number(lecture.id)}
                    </small>
                </div>

                <div class="lecture-actions">
                    <button
                        class="btn primary"
                        onclick="openLecture(${Number(lecture.id)})">
                        Open
                    </button>

                    <button
                        class="btn danger"
                        onclick="deleteLecture(${Number(lecture.id)})">
                        Delete
                    </button>
                </div>

            </div>
        `).join("");

        setLibraryStatus(
            lectures.length +
            (lectures.length === 1
                ? " saved lecture."
                : " saved lectures.")
        );

    } catch (error) {
        list.innerHTML = `
            <div class="empty-library">
                Could not load saved lectures. Check that the backend is running.
            </div>
        `;

        setLibraryStatus(error.message, true);
    }
}


/* ==========================================
   OPEN A SAVED LECTURE
   ========================================== */

async function openLecture(id) {
    try {
        const lecture = await requestJSON(
            "/api/lectures/" + encodeURIComponent(id)
        );

        if (listening) {
            stopMic();
        }

        transcript = lecture.transcript || "";
        lastNotes = lecture.notes || null;

        updateTranscript();

        $("lectureTitle").value = lecture.title || "";

        if (lastNotes) {
            renderNotes(lastNotes);

            renderRevision(lastNotes.questions || []);
        } else {
            $("notesContent").className = "note-placeholder";

            $("notesContent").innerHTML = `
                <div>
                    <span>✧</span>
                    No saved AI notes for this lecture yet.
                </div>
            `;

            $("revisionContent").className = "note-placeholder";

            $("revisionContent").innerHTML = `
                <div>
                    <span>◈</span>
                    No saved revision questions for this lecture.
                </div>
            `;
        }

        $("chat").innerHTML = `
            <div class="message">
                Saved lecture loaded. Ask a question about this lecture.
            </div>
        `;

        $("questionInput").value = "";

        setStatus("Opened saved lecture: " + lecture.title);

        scrollToSection("capture");

    } catch (error) {
        setLibraryStatus(
            "Could not open lecture: " + error.message,
            true
        );
    }
}


/* ==========================================
   DELETE A SAVED LECTURE
   ========================================== */

async function deleteLecture(id) {
    const confirmed = confirm(
        "Delete this saved lecture permanently?"
    );

    if (!confirmed) {
        return;
    }

    try {
        await requestJSON(
            "/api/lectures/" + encodeURIComponent(id),
            {
                method: "DELETE"
            }
        );

        setLibraryStatus("Lecture deleted successfully.");

        await loadLectures();

    } catch (error) {
        setLibraryStatus(
            "Could not delete lecture: " + error.message,
            true
        );
    }
}


/* ==========================================
   LOAD LIBRARY WHEN PAGE OPENS
   ========================================== */

document.addEventListener("DOMContentLoaded", () => {
    loadLectures();
});
