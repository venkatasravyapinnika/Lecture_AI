
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from google.genai import types
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing from backend/.env"
    )

client = genai.Client(api_key=API_KEY)

DB_PATH = BASE_DIR / "lectures.db"


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_database():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS lectures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Preserve compatibility with an older database
        # that already has a user_id column.
        lecture_columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(lectures)"
            ).fetchall()
        ]

        if "user_id" not in lecture_columns:
            conn.execute("""
                ALTER TABLE lectures
                ADD COLUMN user_id INTEGER
            """)

        if "segments" not in lecture_columns:
            conn.execute("""
                ALTER TABLE lectures
                ADD COLUMN segments TEXT
            """)

        conn.commit()


create_database()


# --------------------------------------------------
# FASTAPI APP
# --------------------------------------------------

app = FastAPI(title="AI Lecture Companion API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class NotesRequest(BaseModel):
    transcript: str


class AskRequest(BaseModel):
    transcript: str
    question: str


class SaveLectureRequest(BaseModel):
    title: str
    transcript: str
    notes: dict | None = None
    segments: list | None = None


# --------------------------------------------------
# GEMINI HELPER
# --------------------------------------------------

def generate_json(prompt):

    try:

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json"
            }
        )

        return json.loads(response.text)

    except Exception as error:

        print("Gemini error:", error)

        raise HTTPException(
            status_code=502,
            detail="Unable to generate a response from Gemini. Please try again."
        )


# --------------------------------------------------
# BASIC ROUTES
# --------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "AI Lecture Companion backend is running."
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


# --------------------------------------------------
# GENERATE STUDY NOTES
# --------------------------------------------------

@app.post("/api/notes")
def generate_notes(request: NotesRequest):

    if len(request.transcript.strip()) < 20:

        raise HTTPException(
            status_code=400,
            detail="Transcript is too short."
        )

    prompt = f"""
    You are an AI lecture assistant.

    Create structured study notes from this lecture.

    Return valid JSON with exactly these keys:

    {{
        "title": "Lecture title",
        "summary": "Short summary",
        "key_concepts": [
            {{"term": "Concept", "meaning": "Explanation"}}
        ],
        "notes": [
            {{
                "heading": "Section heading",
                "points": ["Point 1", "Point 2"]
            }}
        ],
        "questions": [
            {{"q": "Question", "a": "Answer"}}
        ]
    }}

    Lecture transcript:
    {request.transcript}
    """

    return generate_json(prompt)


# --------------------------------------------------
# ASK YOUR LECTURE
# --------------------------------------------------

@app.post("/api/ask")
def ask_lecture(request: AskRequest):

    if not request.transcript.strip():

        raise HTTPException(
            status_code=400,
            detail="Lecture transcript is empty."
        )

    if not request.question.strip():

        raise HTTPException(
            status_code=400,
            detail="Please enter a question."
        )

    prompt = f"""
    You are an AI lecture assistant.

    Answer the student's question using the lecture transcript.

    If the answer is not available in the transcript,
    clearly mention that.

    Lecture:
    {request.transcript}

    Student question:
    {request.question}

    Return JSON:

    {{
        "answer": "Your answer"
    }}
    """

    return generate_json(prompt)


# --------------------------------------------------
# SAVE A LECTURE
# --------------------------------------------------

@app.post("/api/lectures")
def save_lecture(request: SaveLectureRequest):

    title = request.title.strip()
    transcript = request.transcript.strip()

    if not title:

        raise HTTPException(
            status_code=400,
            detail="Lecture title is required."
        )

    if not transcript:

        raise HTTPException(
            status_code=400,
            detail="Lecture transcript is required."
        )

    notes_json = (
        json.dumps(request.notes)
        if request.notes is not None
        else None
    )

    segments_json = (
        json.dumps(request.segments)
        if request.segments is not None
        else None
    )

    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO lectures
            (title, transcript, notes, created_at, user_id, segments)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (
                title,
                transcript,
                notes_json,
                created_at,
                segments_json
            )
        )

        lecture_id = cursor.lastrowid

        conn.commit()

    return {
        "message": "Lecture saved successfully.",
        "id": lecture_id,
        "title": title
    }


# --------------------------------------------------
# GET ALL SAVED LECTURES
# --------------------------------------------------

@app.get("/api/lectures")
def get_lectures():

    with get_connection() as conn:

        rows = conn.execute(
            """
            SELECT id, title, created_at
            FROM lectures
            ORDER BY id DESC
            """
        ).fetchall()

    return {
        "lectures": [dict(row) for row in rows]
    }


# --------------------------------------------------
# OPEN A PARTICULAR LECTURE
# --------------------------------------------------

@app.get("/api/lectures/{lecture_id}")
def get_lecture(lecture_id: int):

    with get_connection() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM lectures
            WHERE id = ?
            """,
            (lecture_id,)
        ).fetchone()

    if row is None:

        raise HTTPException(
            status_code=404,
            detail="Lecture not found."
        )

    lecture = dict(row)

    if lecture["notes"]:

        lecture["notes"] = json.loads(
            lecture["notes"]
        )

    else:

        lecture["notes"] = None

    if lecture.get("segments"):

        lecture["segments"] = json.loads(
            lecture["segments"]
        )

    else:

        lecture["segments"] = None

    return lecture


# --------------------------------------------------
# DELETE A SAVED LECTURE
# --------------------------------------------------

@app.delete("/api/lectures/{lecture_id}")
def delete_lecture(lecture_id: int):

    with get_connection() as conn:

        cursor = conn.execute(
            """
            DELETE FROM lectures
            WHERE id = ?
            """,
            (lecture_id,)
        )

        conn.commit()

        if cursor.rowcount == 0:

            raise HTTPException(
                status_code=404,
                detail="Lecture not found."
            )

    return {
        "message": "Lecture deleted successfully."
    }


# --------------------------------------------------
# MICROPHONE TRANSCRIPTION
# --------------------------------------------------

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("en")
):
    try:
        audio_data = await file.read()

        if not audio_data:
            raise HTTPException(
                status_code=400,
                detail="No audio received."
            )

        mime_type = file.content_type or "audio/webm"

        prompt = f"""
        Transcribe this audio accurately.
        The expected language is {language}.

        Split the transcription into segments of roughly 20 to 40 seconds each.
        Estimate the start time of each segment in integer seconds from the
        beginning of the audio.

        Return valid JSON with this exact structure:
        {{
            "segments": [
                {{"start_sec": 0, "text": "Spoken words for the first segment"}},
                {{"start_sec": 25, "text": "Spoken words for the next segment"}}
            ]
        }}

        Rules:
        - Each segment should contain roughly 20 to 40 seconds of spoken content.
        - start_sec must be an integer (seconds from the start of the audio).
        - text must contain only the spoken words, with no summaries or commentary.
        - Do not include any text outside the JSON structure.
        """

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=audio_data,
                    mime_type=mime_type
                )
            ],
            config={
                "response_mime_type": "application/json"
            }
        )

        result = json.loads(response.text)
        raw_segments = result.get("segments", [])

        # Validate and clean each segment.
        clean_segments = []
        for s in raw_segments:
            text = str(s.get("text", "")).strip()
            if text:
                clean_segments.append({
                    "start_sec": (
                        int(s["start_sec"])
                        if s.get("start_sec") is not None
                        else None
                    ),
                    "text": text
                })

        if not clean_segments:
            raise HTTPException(
                status_code=502,
                detail="No transcription was returned."
            )

        full_text = " ".join(s["text"] for s in clean_segments)

        return {"text": full_text, "segments": clean_segments}

    except HTTPException:
        raise

    except Exception as error:
        print("Transcription error:", error)

        raise HTTPException(
            status_code=502,
            detail="Audio transcription failed. Please try again."
        )

