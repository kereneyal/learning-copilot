# 🎓 AI Learning Copilot

An AI-powered learning assistant that helps students understand course materials, search knowledge, and prepare for exams.

---

## 🚀 Features

- 🔍 **Global Search** – Search across courses, lectures, and documents
- 🤖 **AI Copilot** – Ask questions and get answers based on your materials
- 📚 **Knowledge Center** – Organized view of lectures, summaries, and documents
- 📝 **Exam Simulation** – Generate practice exams automatically
- 📊 **Document Processing** – Upload and analyze PDFs, documents, and media
- 🎯 **Study Mode** – AI-assisted learning experience

---

## 🧠 Tech Stack

### Backend
- FastAPI
- SQLAlchemy
- ChromaDB (vector DB)
- Ollama / OpenAI (LLMs)
- Python

### Frontend
- Next.js
- React
- TailwindCSS

---

## 🏗️ Project Structure
learning-copilot/
├── backend/
│   ├── app/
│   ├── chroma_db/
│   ├── storage/
│   └── …
├── frontend/
│   ├── app/
│   └── …
├── docs/
│   └── images/
└── README.md

---

## ⚙️ Setup Instructions

### 1. Clone the repo
```bash
git clone https://github.com/kereneyal/learning-copilot.git
cd learning-copilot

### 2. Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

Create .env file:
OPENAI_API_KEY=your_key_here

Run server:
uvicorn app.main:app --reload

### 3. Frontend setup
cd frontend
npm install

Create .env.local:
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000

Run:
npm run dev


Future Improvements
	•	User authentication
	•	Multi-course management
	•	Better AI reasoning & summarization
	•	Deployment to production


Author

Eyal Keren


If you like this project

Give it a star on GitHub!
