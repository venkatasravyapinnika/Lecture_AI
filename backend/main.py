
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
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
    raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

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
        conn.commit()


create_database()


# --------------------------------------------------
# FASTAPI APP
# --------------------------------------------------

app = FastAPI(title="AI Lecture Companion API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_credentials=True,
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
        raise HTTPException(
            status_code=502,
            detail=f"Gemini error: {str(error)}"
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
    return {"status": "healthy"}


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

    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO lectures
            (title, transcript, notes, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (title, transcript, notes_json, created_at)
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
        lecture["notes"] = json.loads(lecture["notes"])
    else:
        lecture["notes"] = None

    return lecture


# --------------------------------------------------
# DELETE A SAVED LECTURE
# --------------------------------------------------

@app.delete("/api/lectures/{lecture_id}")
def delete_lecture(lecture_id: int):

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM lectures WHERE id = ?",
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
