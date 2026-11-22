
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv
from google import genai
from pwdlib import PasswordHash
import jwt
from jwt.exceptions import InvalidTokenError


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing from backend/.env")

client = genai.Client(api_key=API_KEY)

password_hash = PasswordHash.recommended()
security = HTTPBearer()

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

        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Lectures table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lectures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Add user_id to existing lectures table if needed
        columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(lectures)"
            ).fetchall()
        ]

        if "user_id" not in columns:
            conn.execute("""
                ALTER TABLE lectures
                ADD COLUMN user_id INTEGER REFERENCES users(id)
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

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    name: str


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
# PASSWORD AND TOKEN HELPERS
# --------------------------------------------------

def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str):
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int):
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "exp": expires
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


# --------------------------------------------------
# AUTHENTICATION DEPENDENCY
# --------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = int(payload["sub"])

    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User account not found."
        )

    return dict(user)


# --------------------------------------------------
# AUTHENTICATION ROUTES
# --------------------------------------------------

@app.post("/api/auth/register", response_model=TokenResponse)
def register_user(request: RegisterRequest):

    name = request.name.strip()
    email = str(request.email).strip().lower()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required."
        )

    created_at = datetime.now(timezone.utc).isoformat()
    hashed_password = hash_password(request.password)

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users
                (name, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, hashed_password, created_at)
            )

            user_id = cursor.lastrowid
            conn.commit()

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    token = create_access_token(user_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "name": name
    }


@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(request: LoginRequest):

    email = str(request.email).strip().lower()

    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

    if user is None or not verify_password(
        request.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password."
        )

    token = create_access_token(user["id"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "name": user["name"]
    }


@app.get("/api/auth/me")
def get_my_account(
    current_user: dict = Depends(get_current_user)
):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"]
    }


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

    except Exception:
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
    return {"status": "healthy"}


# --------------------------------------------------
# GENERATE STUDY NOTES
# --------------------------------------------------

@app.post("/api/notes")
def generate_notes(
    request: NotesRequest,
    current_user: dict = Depends(get_current_user)
):

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
def ask_lecture(
    request: AskRequest,
    current_user: dict = Depends(get_current_user)
):

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
def save_lecture(
    request: SaveLectureRequest,
    current_user: dict = Depends(get_current_user)
):

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
            (title, transcript, notes, created_at, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                transcript,
                notes_json,
                created_at,
                current_user["id"]
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
# GET ALL LECTURES FOR CURRENT USER
# --------------------------------------------------

@app.get("/api/lectures")
def get_lectures(
    current_user: dict = Depends(get_current_user)
):

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at
            FROM lectures
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (current_user["id"],)
        ).fetchall()

    return {
        "lectures": [dict(row) for row in rows]
    }


# --------------------------------------------------
# OPEN A PARTICULAR LECTURE
# --------------------------------------------------

@app.get("/api/lectures/{lecture_id}")
def get_lecture(
    lecture_id: int,
    current_user: dict = Depends(get_current_user)
):

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM lectures
            WHERE id = ? AND user_id = ?
            """,
            (lecture_id, current_user["id"])
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
def delete_lecture(
    lecture_id: int,
    current_user: dict = Depends(get_current_user)
):

    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM lectures
            WHERE id = ? AND user_id = ?
            """,
            (lecture_id, current_user["id"])
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
