# LectureAI – AI-Powered Lecture Companion

## 1. Project Overview

LectureAI is an AI-powered learning assistant designed to help students understand and revise classroom lectures more effectively.

It converts lecture transcripts into structured study notes, provides answers to questions based on lecture content, generates revision questions and allows students to save and revisit their lectures.

## 2. Problem Statement

Students often find it difficult to take complete lecture notes, identify important concepts and revise large amounts of classroom content.

Manually organizing lecture information and preparing revision questions can also consume considerable time.

LectureAI aims to simplify this process using Artificial Intelligence.

## 3. Objectives

- Convert spoken lectures into text using speech recognition.
- Generate structured study notes using AI.
- Allow students to ask questions about lecture content.
- Generate revision questions with answers.
- Store and retrieve previously saved lectures.
- Provide a simple and user-friendly learning interface.

## 4. Key Features

### 4.1 Lecture Transcription
Students can capture lecture content through a microphone or manually enter and edit transcripts.

### 4.2 AI-Generated Study Notes
The application uses Google's Gemini API to generate:
- Lecture summaries
- Key concepts
- Important points
- Structured study notes

### 4.3 Ask Your Lecture
Students can ask questions related to their lecture and receive AI-generated explanations based on the provided transcript.

### 4.4 Revision Room
The system generates practice questions and answers to help students revise lecture topics.

### 4.5 My Lectures
Students can:
- Save lectures with titles.
- View previously saved lectures.
- Open saved lectures.
- Retrieve their transcripts and notes.
- Delete saved lectures.

## 5. Technologies Used

| Technology | Purpose |
|---|---|
| HTML | Frontend structure |
| CSS | User interface and styling |
| JavaScript | Frontend functionality |
| Python | Backend development |
| FastAPI | API development |
| Google Gemini API | AI-powered processing |
| SQLite | Lecture storage |
| Speech Recognition API | Voice transcription |

## 6. System Architecture

```text
              STUDENT
                 |
                 v
        FRONTEND INTERFACE
          HTML / CSS / JS
                 |
                 v
          FASTAPI BACKEND
             /       \
            /         \
           v           v
      GEMINI API     SQLITE
           |           |
           v           v
      AI NOTES       SAVED
      AI ANSWERS     LECTURES
      REVISION
```

## 7. Project Structure

```text
LectureAI/
│
├── frontend/
│   ├── index.html
│   └── script.js
│
└── backend/
    ├── main.py
    ├── .env
    └── lectures.db
```

## 8. Installation and Execution

### Step 1: Install dependencies

Open the backend folder in the terminal and activate your Python virtual environment.

Install the required packages:

```bash
pip install -r requirements.txt
```

### Step 2: Configure API key

Create a `.env` file inside the backend folder and add your Gemini API key using the environment variable name expected by your backend code.

Do not upload your API key to GitHub.

### Step 3: Start the backend

```bash
cd backend
uvicorn main:app --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### Step 4: Run the frontend

Open `frontend/index.html` using the VS Code Live Server extension.

## 9. Expected Outcome

LectureAI provides a centralized platform for capturing, organizing, understanding and revising classroom lectures.

It reduces the manual effort involved in preparing study materials and makes lecture revision more convenient.

## 10. Future Enhancements

- PDF upload and summarization.
- Download study notes as PDF.
- Student authentication.
- Flashcard generation.
- Audio file transcription.
- Multilingual lecture support.
- Personalized learning recommendations.

## 11. Conclusion

LectureAI demonstrates how Artificial Intelligence can support students in their everyday learning process.

By combining speech recognition, generative AI and database storage, the application transforms lecture content into organized and reusable learning materials.