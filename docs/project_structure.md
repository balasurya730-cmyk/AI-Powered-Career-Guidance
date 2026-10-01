# Project Structure

This document outlines the architecture and file structure of the AI Learning Planner & Career Advisor application.

## Directory Tree

```text
rkle/
├── backend/                  # Fast API Backend
│   ├── main.py               # Application entry point and routing
│   ├── database.py           # SQLite database connection and setup
│   ├── models.py             # Pydantic schemas for data validation
│   ├── auth_utils.py         # Authentication (JWT) and password hashing
│   ├── gemini_service.py     # AI integration with Google Gemini
│   ├── seed_data.py          # Script to load demo data
│   ├── requirements.txt      # Python dependencies
│   ├── .env                  # Environment variables (API Keys, Secrets)
│   ├── .env.example          # Example environment variables
│   └── learning_planner.db   # SQLite Database File
├── frontend/                 # Static HTML/JS/CSS Frontend
│   ├── pages/                # HTML Templates
│   │   ├── index.html        # Landing page
│   │   ├── dashboard.html    # Main user dashboard
│   │   ├── profile.html      # User profile configuration
│   │   ├── career-advisor.html # AI career recommendation page
│   │   └── learning-planner.html # Generated study planner page
│   ├── css/
│   │   └── style.css         # Global stylesheet
│   └── js/
│       ├── api.js            # API wrapper for backend requests
│       ├── auth.js           # Authentication logic
│       ├── dashboard.js      # Dashboard dynamic logic
│       └── ...               # Other page-specific scripts
├── database/                 # Database Schema
│   └── schema.sql            # Raw SQL schema definition
├── tests/                    # Testing Suite
│   ├── test_ui.py            # Unit tests for UI
│   ├── test_endpoints.py     # API endpoint tests
│   ├── e2e_test.py           # End-to-end testing
│   ├── load_test.py          # Load and performance testing
│   └── playwright_smoke.py   # E2E Smoke testing with Playwright
├── docs/                     # Documentation
│   └── project_structure.md  # This file
├── README.md                 # Main project documentation
├── CHANGES.md                # Changelog
└── ENHANCEMENTS.md           # Future enhancement ideas
```

## Stack Summary
- **Frontend**: HTML5, CSS3, Vanilla JS
- **Backend**: Python 3, FastAPI, Uvicorn
- **Database**: SQLite3
- **AI**: Google Gemini API
