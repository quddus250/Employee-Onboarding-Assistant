# Employee Onboarding Assistant

A submission-ready full-stack MVP implementing the four requested scenarios.

## Stack
- React + Vite + Lucide icons
- Python Flask REST API
- SQLite persistent database
- Server-Sent Events (SSE) for HR reminder pings
- OpenAI Responses API when `OPENAI_API_KEY` is configured
- Local policy similarity fallback when no API key is available

## Demo accounts
- Employee: `alex@company.com` / `password` (Engineering)
- Employee: `priya@company.com` / `password` (Sales)
- Employee: `samira@company.com` / `password` (Design)
- HR: `hr@company.com` / `admin123`

## Run backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Optional: copy .env.example to .env and add OPENAI_API_KEY
python app.py
```
Backend runs at http://localhost:5000.

## Run frontend
Open another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

## Scenarios implemented
1. Department-aware personalized tasks and policy chatbot.
2. 100% compliance quiz required before the harassment task can be completed.
3. HR sees cohort progress and can send an instant SSE reminder to an employee.
4. Chatbot reads pending tasks and recommends the next task based on due day/priority.

## Submission notes
This is intentionally compact so it can be demonstrated quickly. For production deployment, add proper authentication/authorization, encrypted secrets, file validation/scanning, CSRF protection, rate limiting, audit logs, and a production WSGI server.
