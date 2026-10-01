# Maintenance Guide

This document outlines the proper maintenance procedures ("meaitanence") for the application to ensure it remains in a working condition.

## 1. Starting the Application
Always ensure that the backend is started from the `backend/` directory to avoid import collision issues:
```bash
cd backend
uvicorn main:app --reload
```

## 2. Database Maintenance
- The database is a local SQLite file (`backend/learning_planner.db`).
- **Backups**: Periodically copy `learning_planner.db` to a secure backup location.
- **Migrations**: If `models.py` is updated with new database schema changes, you may need to clear the existing `learning_planner.db` and let `init_db()` recreate the tables on startup. For production, consider introducing a migration tool like `alembic`.

## 3. Monitoring and Logging
- The backend logs all requests and errors to the console output of the `uvicorn` process. 
- **Error Tracking**: Monitor the logs for `500 Internal Server Error` which usually indicate a bug in the endpoint logic or a failed third-party API call (e.g., Gemini API).

## 4. Running the Load Test
To ensure the system works after a major change, you should simulate user traffic using the load test script.
```bash
# Set NUM_USERS in tests/load_test.py (e.g., 50 or 100)
python tests/load_test.py
```
- A successful output will show `TOTAL CHECKS: X   PASS: X   FAIL: 0`.
- If failures occur, the script will output the exact endpoint and error message at the end of the run.

## 5. Third-Party Integrations
- **Gemini AI**: The system relies on the Gemini AI API for generating plans and chats. Ensure the `GEMINI_API_KEY` in `backend/.env` is valid and has sufficient quota. If AI endpoints start timing out, verify your API dashboard.
