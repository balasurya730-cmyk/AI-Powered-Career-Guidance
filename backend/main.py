"""
main.py
-------
The FastAPI application entry point. Wires together:
    - database.py       (SQLite storage)
    - models.py          (request/response validation)
    - auth_utils.py      (password hashing + JWT)
    - gemini_service.py  (AI career advice + learning plans)

Run with:
    uvicorn main:app --reload --port 8000

Serves the JSON API under /api/... and also serves the static frontend
(the ../frontend folder) so the whole app runs from a single server and
port, with no CORS issues.
"""

import json
import os
import secrets
import smtplib
import asyncio
from email.message import EmailMessage
from typing import Optional
from datetime import datetime, timedelta, date
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Query, Request, Response
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_connection
from models import (
    RegisterRequest, LoginRequest, GoogleAuthRequest,
    SendOtpRequest, VerifyOtpRequest, TokenResponse,
    ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest,
    ProfileRequest, ProfileResponse,
    CareerAdvisorQuestionsRequest, CareerRecommendationResponse,
    SelectCareerRequest, DirectoryResponse, DirectoryCareerItem, SelectDirectoryCareerRequest,
    GenerateDirectoryCareerRequest, MatchScoreRequest, MatchScoreResponse,
    UserSearchResponse, UserSearchItem, PeerRecommendationResponse, PeerRecommendationItem,
    GeneratePlanRequest, LearningPlanResponse,
    UpdateProgressRequest, DashboardResponse,
    TaskStartResponse, TaskSubmitRequest, TaskSubmitResponse,
    PracticeProjectSubmitRequest, PracticeProjectSubmissionResponse,
    ChatRequest, ChatResponse,
    GeneratePhasesRequest, PhaseResponse, PhaseTask,
    ProjectSubmitRequest, ProjectSubmissionResponse, ProjectError,
    TestStartRequest, TestStartResponse, TestQuestionForStudent,
    TestViolationRequest, TestSubmitRequest, TestResultResponse,
    NotificationItem, DistractionPingRequest,
    BadgeResponseItem, CertificateResponse,
    LeaderboardEntry, LeaderboardResponse,
    SkillGapAnalyzeRequest, SkillGapResponse,
    CourseRecommendationRequest, CourseRecommendationItem, CourseRecommendationResponse,
    InterviewStartResponse, InterviewQuestionForStudent,
    InterviewAnswerRequest, InterviewAnswerFeedback,
    InterviewFinishRequest, InterviewFinishResponse, InterviewSummary,
    InterviewHistoryResponse, InterviewHistoryItem, InterviewDetailResponse,
    GroupCreateRequest, GroupResponse, GroupMessageResponse,
    SummarizeMeetRequest, AnalyticsResponse,
)
from auth_utils import hash_password, verify_password, create_access_token, get_current_user_id
import gemini_service
import sqlite3
from datetime import datetime, timedelta, date

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE")

# Twilio SMS config (optional - falls back to log if not configured)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_FROM  = os.getenv("TWILIO_PHONE_FROM", "")

# SMTP config for email OTP
SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_OTP = os.getenv("SMTP_FROM", SMTP_USER)

app = FastAPI(title="AI Learning Planner & Career Advisor")

# CORS left open for local development. Tighten allow_origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", 
        "http://localhost:8001", 
        "http://127.0.0.1:8000", 
        "http://127.0.0.1:8001",
        "https://ai-powered-career-guidance.onrender.com"
    ],
    allow_origin_regex="https://.*", # Allow any HTTPS origin for seamless cross-origin cookie auth on Render/Netlify
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    _start_scheduler()


@app.get("/api/health", tags=["Health"])
def health():
    """Lightweight health endpoint for frontend pings and load balancers."""
    return {"status": "ok", "time": datetime.utcnow().isoformat()}





# ---------------- EMAIL (best-effort; silently skipped if SMTP isn't configured) ----------------

EMAIL_ALERTS_ENABLED = os.getenv("EMAIL_ALERTS_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def send_email_alert(to_email: str, subject: str, body: str) -> bool:
    """
    Best-effort email send. Returns True/False and never raises — a missing or
    misconfigured SMTP provider must not break the deadline-check job or any
    request that triggers a notification. In-app notifications are always
    created regardless of whether this succeeds.
    """
    if not EMAIL_ALERTS_ENABLED or not SMTP_HOST or not SMTP_USER:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[email] failed to send to {to_email}: {e}")
        return False


# =========================================================================
# AUTH
# =========================================================================

@app.post("/api/register", response_model=TokenResponse, tags=["Auth"])
def register(payload: RegisterRequest, response: Response):
    """Create a new account. Emails must be unique."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = ?", (payload.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    password_hash = hash_password(payload.password)
    student_code = f"STU-{secrets.token_hex(4).upper()}"
    cur.execute(
        "INSERT INTO users (name, email, password_hash, role, student_code) VALUES (?, ?, ?, ?, ?)",
        (payload.name, payload.email, password_hash, "student", student_code),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    token = create_access_token(user_id, payload.email)
    response.set_cookie(
        key="alp_session",
        value=token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=1440 * 60,  # 24 hours
    )
    return TokenResponse(access_token="", user_id=user_id, name=payload.name, email=payload.email)


@app.post("/api/login", response_model=TokenResponse, tags=["Auth"])
def login(payload: LoginRequest, response: Response):
    """Verify email + password, set an HTTP-only session cookie."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (payload.email,))
    row = cur.fetchone()
    conn.close()

    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(row["id"], row["email"])
    response.set_cookie(
        key="alp_session",
        value=token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=1440 * 60,
    )
    return TokenResponse(access_token="", user_id=row["id"], name=row["name"], email=row["email"])


@app.get("/api/config", tags=["Config"])
def get_config():
    """Return public configuration values to the frontend."""
    return {"google_client_id": GOOGLE_CLIENT_ID}


@app.post("/api/auth/google", response_model=TokenResponse, tags=["Auth"])
def google_auth(payload: GoogleAuthRequest, response: Response):
    """Verify Google token, login or create new user."""
    try:
        id_info = id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        email = id_info.get("email")
        name = id_info.get("name", "Google User")

        if not email:
            raise HTTPException(status_code=400, detail="Google token did not contain an email.")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, email FROM users WHERE email = ?", (email,))
        row = cur.fetchone()

        if not row:
            # User doesn't exist, create a new one
            # Use a random password since they login via Google
            dummy_password = secrets.token_urlsafe(32)
            password_hash = hash_password(dummy_password)
            student_code = f"STU-{secrets.token_hex(4).upper()}"
            
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role, student_code) VALUES (?, ?, ?, ?, ?)",
                (name, email, password_hash, "student", student_code),
            )
            conn.commit()
            user_id = cur.lastrowid
            
            cur.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            
        conn.close()

        token = create_access_token(row["id"], row["email"])
        response.set_cookie(
            key="alp_session",
            value=token,
            httponly=True,
            samesite="none",
            secure=True,
            max_age=1440 * 60,
        )
        return TokenResponse(access_token="", user_id=row["id"], name=row["name"], email=row["email"])

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token.")


@app.post("/api/logout", tags=["Auth"])
def logout(response: Response):
    """Clears the HTTP-only session cookie."""
    response.delete_cookie(key="alp_session", httponly=True, samesite="none", secure=True)
    return {"message": "Successfully logged out"}


@app.get("/api/auth/status", tags=["Auth"])
def auth_status(user_id: int = Depends(get_current_user_id)):
    """Simple endpoint for the frontend to verify if a valid session cookie exists."""
    return {"authenticated": True, "user_id": user_id}


RESET_TOKEN_EXPIRE_MINUTES = 30
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

OTP_EXPIRE_MINUTES = 10


def _send_email_otp(to_email: str, name: str, otp: str):
    """Send OTP via SMTP. Falls back to console log if SMTP not configured."""
    subject = "Your Trailhead Verification Code"
    body = (
        f"Hi {name},\n\n"
        f"Your email verification code is:\n\n"
        f"  {otp}\n\n"
        f"This code expires in {OTP_EXPIRE_MINUTES} minutes.\n\n"
        f"If you didn't request this, please ignore this message.\n\n"
        f"— Trailhead Team"
    )
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"[OTP] EMAIL OTP for {to_email}: {otp}  (SMTP not configured — shown in logs only)")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_OTP
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASSWORD)
            srv.send_message(msg)
    except Exception as e:
        print(f"[OTP] Failed to send email OTP: {e} — OTP is: {otp}")


def _send_sms_otp(to_phone: str, otp: str):
    """Send OTP via Twilio SMS. Falls back to console log if not configured."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_FROM:
        print(f"[OTP] SMS OTP for {to_phone}: {otp}  (Twilio not configured — shown in logs only)")
        return
    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Your Trailhead verification code is: {otp}  (expires in {OTP_EXPIRE_MINUTES} min)",
            from_=TWILIO_PHONE_FROM,
            to=to_phone,
        )
    except Exception as e:
        print(f"[OTP] Failed to send SMS OTP: {e} — OTP is: {otp}")


@app.post("/api/auth/send-otp", tags=["Auth"])
def send_otp(payload: SendOtpRequest):
    """Step 1 of OTP registration: validate input, generate OTPs, send them."""
    conn = get_connection()
    cur = conn.cursor()

    # Check email not already taken
    cur.execute("SELECT id FROM users WHERE email = ?", (payload.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please log in instead.")

    # Clean up any previous OTP attempts for this email
    cur.execute("DELETE FROM otp_tokens WHERE email = ?", (payload.email,))

    email_otp = str(secrets.randbelow(900000) + 100000)   # 6-digit
    phone_otp  = str(secrets.randbelow(900000) + 100000)
    expires_at = (datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)).isoformat()
    password_hash = hash_password(payload.password)

    cur.execute(
        """INSERT INTO otp_tokens (email, phone, name, password_hash, email_otp, phone_otp, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (payload.email, payload.phone, payload.name, password_hash, email_otp, phone_otp, expires_at),
    )
    conn.commit()
    conn.close()

    _send_email_otp(payload.email, payload.name, email_otp)
    _send_sms_otp(payload.phone, phone_otp)

    return {"message": "OTP sent to your email and phone. Please verify within 10 minutes."}


@app.post("/api/auth/verify-otp", response_model=TokenResponse, tags=["Auth"])
def verify_otp(payload: VerifyOtpRequest):
    """Step 2 of OTP registration: verify both OTPs and create the account."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM otp_tokens WHERE email = ? ORDER BY id DESC LIMIT 1",
        (payload.email,),
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="No pending registration found. Please start over.")

    # Check expiry
    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        cur.execute("DELETE FROM otp_tokens WHERE email = ?", (payload.email,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    # Validate OTPs
    if row["email_otp"] != payload.email_otp.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect email OTP. Please try again.")
    if row["phone_otp"] != payload.phone_otp.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect phone OTP. Please try again.")

    # Create the user
    student_code = f"STU-{secrets.token_hex(4).upper()}"
    try:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role, phone, email_verified, phone_verified, student_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["name"], row["email"], row["password_hash"], "student", row["phone"], 1, 1, student_code),
        )
        conn.commit()
        user_id = cur.lastrowid
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    # Remove the OTP token
    cur.execute("DELETE FROM otp_tokens WHERE email = ?", (payload.email,))
    conn.commit()
    conn.close()

    token = create_access_token(user_id, payload.email)
    return TokenResponse(access_token=token, user_id=user_id, name=row["name"], email=payload.email)




@app.post("/api/auth/forgot-password", response_model=ForgotPasswordResponse, tags=["Auth"])
def forgot_password(payload: ForgotPasswordRequest):
    """
    Starts a password reset. Always returns a generic success message
    regardless of whether the email is registered, so this endpoint can't be
    used to figure out which emails have accounts.

    If email sending is configured (EMAIL_ALERTS_ENABLED), the reset link is
    emailed. If not, the link is returned directly in the response so the
    flow still works for local/dev use without an SMTP provider set up.
    """
    generic_message = "If an account exists for that email, a password reset link has been sent."

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM users WHERE email = ?", (payload.email,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return ForgotPasswordResponse(message=generic_message)

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)).isoformat()
    # Invalidate any earlier unused tokens for this user before issuing a new one
    cur.execute("UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0", (row["id"],))
    cur.execute(
        "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (row["id"], token, expires_at),
    )
    conn.commit()
    conn.close()

    reset_link = f"{FRONTEND_URL}/reset-password.html?token={token}"
    emailed = send_email_alert(
        row["email"],
        "Reset your password",
        f"Hi {row['name']},\n\nUse the link below to reset your password. "
        f"This link expires in {RESET_TOKEN_EXPIRE_MINUTES} minutes.\n\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email.",
    )

    return ForgotPasswordResponse(message=generic_message, reset_link=None if emailed else reset_link)


@app.post("/api/auth/reset-password", tags=["Auth"])
def reset_password(payload: ResetPasswordRequest):
    """Verifies a reset token (unused, unexpired) and updates the account's password."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, expires_at, used FROM password_reset_tokens WHERE token = ?",
        (payload.token,),
    )
    row = cur.fetchone()

    if not row or row["used"] or datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.close()
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")

    new_hash = hash_password(payload.new_password)
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["user_id"]))
    cur.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return {"message": "Password reset successfully. You can now log in with your new password."}


# =========================================================================
# STUDENT PROFILE
# =========================================================================

@app.post("/api/profile", response_model=ProfileResponse, tags=["Profile"])
def save_profile(payload: ProfileRequest, user_id: int = Depends(get_current_user_id)):
    """Create or update the logged-in student's profile (upsert)."""
    conn = get_connection()
    cur = conn.cursor()

    # Validate that user exists in users table
    cur.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="User account not found. Please log in again.")

    try:
        cur.execute("SELECT id FROM student_profiles WHERE user_id = ?", (user_id,))
        existing = cur.fetchone()

        name_val = payload.name or user_row["name"] or "Student"
        education_val = payload.education or ""
        department_val = payload.department or ""
        college_val = payload.college or ""
        current_year_val = payload.current_year or ""
        skills_val = payload.skills or ""
        interests_val = payload.interests or ""
        hours_val = payload.daily_study_hours if payload.daily_study_hours is not None else 2.0
        career_val = payload.career_goal or None

        if existing:
            cur.execute("""
                UPDATE student_profiles
                SET name=?, education=?, department=?, college=?, current_year=?,
                    skills=?, interests=?, daily_study_hours=?, career_goal=?,
                    updated_at=datetime('now')
                WHERE user_id=?
            """, (name_val, education_val, department_val, college_val,
                  current_year_val, skills_val, interests_val,
                  hours_val, career_val, user_id))
        else:
            cur.execute("""
                INSERT INTO student_profiles
                    (user_id, name, education, department, college, current_year,
                     skills, interests, daily_study_hours, career_goal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name_val, education_val, department_val, college_val,
                  current_year_val, skills_val, interests_val,
                  hours_val, career_val))

        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Failed to save profile: {e}")

    conn.close()
    return ProfileResponse(
        user_id=user_id,
        name=name_val,
        education=education_val,
        department=department_val,
        college=college_val,
        current_year=current_year_val,
        skills=skills_val,
        interests=interests_val,
        daily_study_hours=hours_val,
        career_goal=career_val
    )


@app.get("/api/profile", response_model=ProfileResponse, tags=["Profile"])
def get_profile(user_id: int = Depends(get_current_user_id)):
    """Fetch the logged-in student's saved profile."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No profile found yet. Please create one first.")

    return ProfileResponse(
        user_id=user_id,
        name=row["name"] or "",
        education=row["education"] or "",
        department=row["department"] or "",
        college=row["college"] or "",
        current_year=row["current_year"] or "",
        skills=row["skills"] or "",
        interests=row["interests"] or "",
        daily_study_hours=row["daily_study_hours"] or 2.0,
        career_goal=row["career_goal"],
    )



def _get_profile_dict(user_id: int) -> dict:
    """Internal helper: fetch profile as a plain dict for feeding into Gemini prompts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Please complete your student profile first.")
    return dict(row)


# =====================================================================
#  PHASED ROADMAP
# =========================================================================

@app.post("/api/career/recommend", response_model=CareerRecommendationResponse, tags=["Career Advisor"])
def recommend_career(
    answers: CareerAdvisorQuestionsRequest | None = None,
    user_id: int = Depends(get_current_user_id),
):
    """
    Calls Gemini to recommend 3 careers based on the student's profile.
    If the student already set a career_goal in their profile, `answers`
    can be omitted -- the profile alone is used as context.
    """
    profile = _get_profile_dict(user_id)
    extra = answers.dict() if answers else None

    try:
        careers = gemini_service.recommend_careers(profile, extra_answers=extra)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI career advisor failed: {e}")

    if not careers:
        raise HTTPException(status_code=502, detail="AI did not return any career suggestions. Please try again.")

    conn = get_connection()
    cur = conn.cursor()
    # Clear old (unselected) recommendations before storing fresh ones
    cur.execute("DELETE FROM careers WHERE user_id = ? AND is_selected = 0", (user_id,))
    for c in careers:
        cur.execute("""
            INSERT INTO careers (user_id, career_name, description, required_skills, future_scope, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, c.get("career_name", ""), c.get("description", ""),
              json.dumps(c.get("required_skills", [])), c.get("future_scope", ""), c.get("reason", "")))
    conn.commit()

    cur.execute("SELECT * FROM careers WHERE user_id = ? AND is_selected = 0 ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cur.fetchall()
    conn.close()

    result = [{
        "career_name": r["career_name"],
        "description": r["description"],
        "required_skills": json.loads(r["required_skills"] or "[]"),
        "future_scope": r["future_scope"],
        "reason": r["reason"],
    } for r in rows]

    return CareerRecommendationResponse(careers=result)


@app.get("/api/career/options", tags=["Career Advisor"])
def get_career_options(user_id: int = Depends(get_current_user_id)):
    """Fetch the most recently generated (not-yet-selected) career recommendations, with their ids."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM careers WHERE user_id = ? AND is_selected = 0 ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{
        "id": r["id"], "career_name": r["career_name"], "description": r["description"],
        "required_skills": json.loads(r["required_skills"] or "[]"),
        "future_scope": r["future_scope"], "reason": r["reason"],
    } for r in rows]


@app.post("/api/career/select", tags=["Career Advisor"])
def select_career(payload: SelectCareerRequest, user_id: int = Depends(get_current_user_id)):
    """Mark one of the recommended careers as the student's chosen path."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM careers WHERE id = ? AND user_id = ?", (payload.career_id, user_id))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Career option not found.")

    cur.execute("UPDATE careers SET is_selected = 0 WHERE user_id = ?", (user_id,))
    cur.execute("UPDATE careers SET is_selected = 1 WHERE id = ?", (payload.career_id,))
    conn.commit()
    conn.close()
    return {"message": "Career selected successfully.", "career_id": payload.career_id}


# =========================================================================
# A-Z CAREER DIRECTORY
# =========================================================================

@app.get("/api/career/directory", response_model=DirectoryResponse, tags=["Career Advisor"])
def get_career_directory():
    """Fetch the full A-Z list of careers."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM global_careers ORDER BY career_name ASC")
    rows = cur.fetchall()
    conn.close()
    
    return DirectoryResponse(careers=[
        DirectoryCareerItem(
            id=r["id"],
            career_name=r["career_name"],
            description=r["description"] or "",
            required_skills=json.loads(r["required_skills"] or "[]"),
            future_scope=r["future_scope"] or ""
        ) for r in rows
    ])


@app.post("/api/career/directory/select", tags=["Career Advisor"])
def select_directory_career(payload: SelectDirectoryCareerRequest, user_id: int = Depends(get_current_user_id)):
    """Select a career from the A-Z directory and set it as the user's active career goal."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM global_careers WHERE id = ?", (payload.global_career_id,))
    global_career = cur.fetchone()
    if not global_career:
        conn.close()
        raise HTTPException(status_code=404, detail="Career not found in directory.")

    # Deselect current career if any
    cur.execute("UPDATE careers SET is_selected = 0 WHERE user_id = ?", (user_id,))
    
    # Insert this as a selected career for the user
    cur.execute("""
        INSERT INTO careers (user_id, career_name, description, required_skills, future_scope, reason, is_selected)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (
        user_id, global_career["career_name"], global_career["description"], 
        global_career["required_skills"], global_career["future_scope"], 
        "Selected from the A-Z Career Directory."
    ))
    new_career_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Career selected successfully from directory.", "career_id": new_career_id}


@app.post("/api/career/directory/generate", response_model=DirectoryCareerItem, tags=["Career Advisor"])
def generate_directory_career(payload: GenerateDirectoryCareerRequest, user_id: int = Depends(get_current_user_id)):
    """Dynamically generates a global career profile using AI and saves it to the directory."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if it already exists (case-insensitive)
    cur.execute("SELECT * FROM global_careers WHERE LOWER(career_name) = LOWER(?)", (payload.career_name,))
    existing = cur.fetchone()
    
    if existing:
        conn.close()
        return DirectoryCareerItem(
            id=existing["id"],
            career_name=existing["career_name"],
            description=existing["description"] or "",
            required_skills=json.loads(existing["required_skills"] or "[]"),
            future_scope=existing["future_scope"] or ""
        )
        
    try:
        profile_data = gemini_service.generate_global_career_profile(payload.career_name)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    cur.execute("""
        INSERT INTO global_careers (career_name, description, required_skills, future_scope)
        VALUES (?, ?, ?, ?)
    """, (
        profile_data.get("career_name", payload.career_name),
        profile_data.get("description", ""),
        json.dumps(profile_data.get("required_skills", [])),
        profile_data.get("future_scope", "")
    ))
    new_id = cur.lastrowid
    conn.commit()
    
    cur.execute("SELECT * FROM global_careers WHERE id = ?", (new_id,))
    row = cur.fetchone()
    conn.close()
    
    return DirectoryCareerItem(
        id=row["id"],
        career_name=row["career_name"],
        description=row["description"] or "",
        required_skills=json.loads(row["required_skills"] or "[]"),
        future_scope=row["future_scope"] or ""
    )

@app.post("/api/career/match-score", response_model=MatchScoreResponse, tags=["Career Advisor"])
def get_match_score(payload: MatchScoreRequest, user_id: int = Depends(get_current_user_id)):
    """Calculates a predictive match score between the student and a career."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    conn.close()
    
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not found. Please complete your profile first.")
        
    try:
        result = gemini_service.predict_career_match_score(dict(profile), payload.career_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI match scoring failed: {e}")
        
    return MatchScoreResponse(score=result["score"], reason=result["reason"])

# =========================================================================
# SKILL GAP ANALYSIS + COURSE RECOMMENDATIONS
# =========================================================================

def _resolve_target_career(cur, user_id: int, career_id: Optional[int]) -> dict:
    """Finds the career to analyze against: an explicit career_id, else the student's selected career."""
    if career_id:
        cur.execute("SELECT * FROM careers WHERE id = ? AND user_id = ?", (career_id, user_id))
    else:
        cur.execute("SELECT * FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No target career found. Select a career on the Career Advisor page first, or pass a career_id.",
        )
    return dict(row)


@app.post("/api/skill-gap/analyze", response_model=SkillGapResponse, tags=["Skill Gap"])
def analyze_skill_gap(payload: SkillGapAnalyzeRequest | None = None, user_id: int = Depends(get_current_user_id)):
    """Compares the student's current skills (from their profile) against a target career's required skills."""
    profile = _get_profile_dict(user_id)
    conn = get_connection()
    cur = conn.cursor()

    career_id = payload.career_id if payload else None
    career = _resolve_target_career(cur, user_id, career_id)
    required_skills = json.loads(career["required_skills"] or "[]")

    try:
        result = gemini_service.analyze_skill_gap(profile, career["career_name"], required_skills)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI skill-gap analysis failed: {e}")

    matched = result.get("matched_skills", [])
    missing = result.get("missing_skills", [])
    summary = result.get("summary", "")

    cur.execute("""
        INSERT INTO skill_gaps (user_id, career_id, career_name, matched_skills, missing_skills, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, career["id"], career["career_name"], json.dumps(matched), json.dumps(missing), summary))
    conn.commit()
    gap_id = cur.lastrowid
    cur.execute("SELECT * FROM skill_gaps WHERE id = ?", (gap_id,))
    row = cur.fetchone()
    conn.close()

    return SkillGapResponse(
        id=row["id"], career_name=row["career_name"],
        matched_skills=json.loads(row["matched_skills"] or "[]"),
        missing_skills=json.loads(row["missing_skills"] or "[]"),
        summary=row["summary"] or "", created_at=row["created_at"],
    )


@app.get("/api/skill-gap/latest", response_model=Optional[SkillGapResponse], tags=["Skill Gap"])
def get_latest_skill_gap(user_id: int = Depends(get_current_user_id)):
    """Fetches the most recent skill-gap analysis for this student, if any."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM skill_gaps "
        "WHERE user_id = ? AND summary NOT LIKE '[Local estimate - AI advisor unreachable]%' "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return SkillGapResponse(
        id=row["id"], career_name=row["career_name"],
        matched_skills=json.loads(row["matched_skills"] or "[]"),
        missing_skills=json.loads(row["missing_skills"] or "[]"),
        summary=row["summary"] or "", created_at=row["created_at"],
    )


@app.post("/api/skill-gap/courses", response_model=CourseRecommendationResponse, tags=["Skill Gap"])
def recommend_courses(payload: CourseRecommendationRequest | None = None, user_id: int = Depends(get_current_user_id)):
    """
    After a skill gap has been identified, generates a specific course /
    tutorial / certification suggestion for each missing skill.
    """
    conn = get_connection()
    cur = conn.cursor()

    gap_id = payload.skill_gap_id if payload else None
    if gap_id:
        cur.execute("SELECT * FROM skill_gaps WHERE id = ? AND user_id = ?", (gap_id, user_id))
    else:
        cur.execute("SELECT * FROM skill_gaps WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    gap_row = cur.fetchone()
    if not gap_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Run a skill-gap analysis first.")

    missing_skills_data = json.loads(gap_row["missing_skills"] or "[]")
    if not missing_skills_data:
        conn.close()
        return CourseRecommendationResponse(skill_gap_id=gap_row["id"], courses=[])

    # Handle both old format (list of strings) and new format (list of dicts with 'skill' key)
    missing_skill_names = [s if isinstance(s, str) else s.get("skill", "") for s in missing_skills_data]

    try:
        courses = gemini_service.recommend_courses(gap_row["career_name"], missing_skill_names)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI course recommender failed: {e}")

    # Replace any previously generated recommendations for this analysis
    cur.execute("DELETE FROM course_recommendations WHERE skill_gap_id = ?", (gap_row["id"],))
    for c in courses:
        cur.execute("""
            INSERT INTO course_recommendations
                (user_id, skill_gap_id, skill_name, title, provider, resource_type, url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, gap_row["id"], c.get("skill_name", ""), c.get("title", ""),
            c.get("provider", ""), c.get("resource_type", "course"), c.get("url", ""), c.get("description", ""),
        ))
    conn.commit()

    cur.execute("SELECT * FROM course_recommendations WHERE skill_gap_id = ? ORDER BY id", (gap_row["id"],))
    rows = cur.fetchall()
    conn.close()

    return CourseRecommendationResponse(
        skill_gap_id=gap_row["id"],
        courses=[CourseRecommendationItem(
            id=r["id"], skill_name=r["skill_name"], title=r["title"], provider=r["provider"] or "",
            resource_type=r["resource_type"] or "course", url=r["url"] or "", description=r["description"] or "",
        ) for r in rows],
    )


@app.get("/api/skill-gap/courses/{skill_gap_id}", response_model=CourseRecommendationResponse, tags=["Skill Gap"])
def get_courses_for_gap(skill_gap_id: int, user_id: int = Depends(get_current_user_id)):
    """Fetches previously generated course recommendations for a given skill-gap analysis."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM skill_gaps WHERE id = ? AND user_id = ?", (skill_gap_id, user_id))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Skill-gap analysis not found.")
    cur.execute("SELECT * FROM course_recommendations WHERE skill_gap_id = ? ORDER BY id", (skill_gap_id,))
    rows = cur.fetchall()
    conn.close()
    return CourseRecommendationResponse(
        skill_gap_id=skill_gap_id,
        courses=[CourseRecommendationItem(
            id=r["id"], skill_name=r["skill_name"], title=r["title"], provider=r["provider"] or "",
            resource_type=r["resource_type"] or "course", url=r["url"] or "", description=r["description"] or "",
        ) for r in rows],
    )


# =========================================================================
# MOCK INTERVIEW (standalone practice tool -- not scored into leaderboard/progress)
# =========================================================================

MOCK_INTERVIEW_NUM_QUESTIONS = 6


def _get_selected_career_name(cur, user_id: int) -> str:
    """The mock interview is always based on the student's currently selected career."""
    cur.execute("SELECT career_name FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No career selected yet. Choose a career on the Career Advisor page first.",
        )
    return row["career_name"]


@app.post("/api/interview/start", response_model=InterviewStartResponse, tags=["Mock Interview"])
def start_interview(user_id: int = Depends(get_current_user_id)):
    """Starts a new mock interview session for the student's currently selected career."""
    profile = _get_profile_dict(user_id)
    conn = get_connection()
    cur = conn.cursor()
    career_name = _get_selected_career_name(cur, user_id)

    try:
        questions = gemini_service.generate_interview_questions(profile, career_name, MOCK_INTERVIEW_NUM_QUESTIONS)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI interview question generation failed: {e}")

    cur.execute("""
        INSERT INTO interview_sessions (user_id, career_name, questions, answers, feedback, status)
        VALUES (?, ?, ?, '[]', '[]', 'in_progress')
    """, (user_id, career_name, json.dumps(questions)))
    session_id = cur.lastrowid
    conn.commit()
    conn.close()

    student_questions = [
        InterviewQuestionForStudent(
            index=i, question=q["question"], type=q.get("type", "behavioral"),
            time_limit_seconds=q.get("time_limit_seconds", 120),
        )
        for i, q in enumerate(questions)
    ]
    return InterviewStartResponse(session_id=session_id, career_name=career_name, questions=student_questions)


def _get_interview_session(cur, session_id: int, user_id: int):
    cur.execute("SELECT * FROM interview_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return row


@app.post("/api/interview/answer", response_model=InterviewAnswerFeedback, tags=["Mock Interview"])
def answer_interview_question(payload: InterviewAnswerRequest, user_id: int = Depends(get_current_user_id)):
    """Submits an answer to one question in an in-progress session and returns instant AI feedback for it."""
    conn = get_connection()
    cur = conn.cursor()
    session = _get_interview_session(cur, payload.session_id, user_id)
    if session["status"] != "in_progress":
        conn.close()
        raise HTTPException(status_code=400, detail="This interview session has already been finished.")

    questions = json.loads(session["questions"])
    if payload.index < 0 or payload.index >= len(questions):
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid question index.")
    q = questions[payload.index]

    try:
        result = gemini_service.evaluate_interview_answer(
            q["question"], q.get("type", "behavioral"), q.get("ideal_points", []), payload.answer,
        )
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI interview feedback failed: {e}")

    answers = json.loads(session["answers"] or "[]")
    feedback_list = json.loads(session["feedback"] or "[]")

    # Replace any existing entry for this index (lets a student redo an answer before finishing)
    answers = [a for a in answers if a.get("index") != payload.index]
    feedback_list = [f for f in feedback_list if f.get("index") != payload.index]

    answers.append({"index": payload.index, "answer": payload.answer, "time_taken_seconds": payload.time_taken_seconds})
    feedback_entry = {
        "index": payload.index,
        "score": result.get("score", 0),
        "feedback": result.get("feedback", ""),
        "strengths": result.get("strengths", []),
        "improvements": result.get("improvements", []),
    }
    feedback_list.append(feedback_entry)

    cur.execute(
        "UPDATE interview_sessions SET answers = ?, feedback = ? WHERE id = ?",
        (json.dumps(answers), json.dumps(feedback_list), payload.session_id),
    )
    conn.commit()
    conn.close()
    return InterviewAnswerFeedback(**feedback_entry)


@app.post("/api/interview/finish", response_model=InterviewFinishResponse, tags=["Mock Interview"])
def finish_interview(payload: InterviewFinishRequest, user_id: int = Depends(get_current_user_id)):
    """Ends the session and generates an overall readiness summary from whatever was answered."""
    conn = get_connection()
    cur = conn.cursor()
    session = _get_interview_session(cur, payload.session_id, user_id)
    if session["status"] != "in_progress":
        conn.close()
        raise HTTPException(status_code=400, detail="This interview session has already been finished.")

    questions = json.loads(session["questions"])
    answers = json.loads(session["answers"] or "[]")
    feedback_list = json.loads(session["feedback"] or "[]")
    answer_map = {a["index"]: a["answer"] for a in answers}
    score_map = {f["index"]: f["score"] for f in feedback_list}

    qa_pairs = [
        {
            "question": q["question"], "type": q.get("type", "behavioral"),
            "answer": answer_map.get(i, "(not answered)"), "score": score_map.get(i, 0),
        }
        for i, q in enumerate(questions)
    ]

    try:
        summary = gemini_service.generate_interview_summary(session["career_name"], qa_pairs)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI interview summary failed: {e}")

    overall_score = summary.get("overall_score", 0)
    overall_feedback = {
        "summary": summary.get("summary", ""),
        "strengths": summary.get("strengths", []),
        "improvements": summary.get("improvements", []),
    }

    cur.execute("""
        UPDATE interview_sessions
        SET status = 'completed', overall_score = ?, overall_feedback = ?, completed_at = datetime('now')
        WHERE id = ?
    """, (overall_score, json.dumps(overall_feedback), payload.session_id))
    conn.commit()
    conn.close()

    return InterviewFinishResponse(
        session_id=payload.session_id,
        overall_score=overall_score,
        answered_count=len(answers),
        total_questions=len(questions),
        per_question_feedback=[InterviewAnswerFeedback(**f) for f in feedback_list],
        overall_feedback=InterviewSummary(**overall_feedback),
    )


@app.get("/api/interview/history", response_model=InterviewHistoryResponse, tags=["Mock Interview"])
def interview_history(user_id: int = Depends(get_current_user_id)):
    """Lists this student's past mock interview sessions, most recent first."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM interview_sessions WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return InterviewHistoryResponse(sessions=[
        InterviewHistoryItem(
            session_id=r["id"], career_name=r["career_name"], status=r["status"],
            overall_score=r["overall_score"], created_at=r["created_at"], completed_at=r["completed_at"],
        ) for r in rows
    ])


@app.get("/api/interview/{session_id}", response_model=InterviewDetailResponse, tags=["Mock Interview"])
def interview_detail(session_id: int, user_id: int = Depends(get_current_user_id)):
    """Fetches the full detail (questions, answers, feedback) of one past or in-progress session."""
    conn = get_connection()
    cur = conn.cursor()
    session = _get_interview_session(cur, session_id, user_id)
    conn.close()

    questions = json.loads(session["questions"])
    answers = json.loads(session["answers"] or "[]")
    feedback_list = json.loads(session["feedback"] or "[]")
    overall_feedback_raw = json.loads(session["overall_feedback"]) if session["overall_feedback"] else None

    return InterviewDetailResponse(
        session_id=session["id"], career_name=session["career_name"], status=session["status"],
        questions=[
            InterviewQuestionForStudent(
                index=i, question=q["question"], type=q.get("type", "behavioral"),
                time_limit_seconds=q.get("time_limit_seconds", 120),
            ) for i, q in enumerate(questions)
        ],
        answers=[InterviewAnswerRequest(session_id=session_id, **a) for a in answers],
        per_question_feedback=[InterviewAnswerFeedback(**f) for f in feedback_list],
        overall_score=session["overall_score"],
        overall_feedback=InterviewSummary(**overall_feedback_raw) if overall_feedback_raw else None,
        created_at=session["created_at"], completed_at=session["completed_at"],
    )


# =========================================================================
# AI LEARNING PLANNER
# =========================================================================

@app.post("/api/learning-plan/generate", response_model=LearningPlanResponse, tags=["Learning Planner"])
def generate_plan(payload: GeneratePlanRequest, user_id: int = Depends(get_current_user_id)):
    """
    Generates (via Gemini) and stores a full learning plan for either:
      - the career_id of a previously selected recommendation, or
      - a plain career_name (e.g. when the student already had a career_goal)
    Also auto-creates the individual progress-tracker checklist rows.
    """
    profile = _get_profile_dict(user_id)

    career_name = payload.career_name
    career_id = payload.career_id

    if career_id and not career_name:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT career_name FROM careers WHERE id = ? AND user_id = ?", (career_id, user_id))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Career not found.")
        career_name = row["career_name"]

    if not career_name:
        career_name = profile.get("career_goal")

    if not career_name:
        # Fall back to the student's currently selected career (from the AI
        # Career Advisor flow) before giving up -- mirrors the fallback used
        # by skill-gap analysis and the mock interview.
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT career_name FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            career_name = row["career_name"]

    if not career_name:
        raise HTTPException(status_code=400, detail="No career specified. Choose a career first.")

    try:
        plan = gemini_service.generate_learning_plan(profile, career_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI learning planner failed: {e}")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO learning_plans
            (user_id, career_id, career_name, daily_plan, weekly_plan, monthly_roadmap,
             skills_to_learn, resources, practice_project)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, career_id, career_name,
        json.dumps(plan.get("daily_plan", [])),
        json.dumps(plan.get("weekly_plan", [])),
        json.dumps(plan.get("monthly_roadmap", [])),
        json.dumps(plan.get("skills_to_learn", [])),
        json.dumps(plan.get("resources", [])),
        plan.get("practice_project", ""),
    ))
    plan_id = cur.lastrowid

    # Auto-generate progress tracker rows from each plan section
    def add_tasks(task_list, task_type):
        for task in task_list:
            cur.execute(
                "INSERT INTO progress (user_id, learning_plan_id, task_name, task_type) VALUES (?, ?, ?, ?)",
                (user_id, plan_id, task, task_type),
            )

    add_tasks(plan.get("daily_plan", []), "daily")
    add_tasks(plan.get("weekly_plan", []), "weekly")
    add_tasks(plan.get("monthly_roadmap", []), "monthly")
    add_tasks(plan.get("skills_to_learn", []), "skill")
    if plan.get("practice_project"):
        add_tasks([plan["practice_project"]], "project")

    # Unlock the first available task in the hierarchy
    hierarchy = ["daily", "weekly", "monthly", "project"]
    for t_type in hierarchy:
        cur.execute("SELECT id FROM progress WHERE learning_plan_id = ? AND task_type = ? ORDER BY id ASC LIMIT 1", (plan_id, t_type))
        first_task = cur.fetchone()
        if first_task:
            cur.execute("UPDATE progress SET status = 'available' WHERE id = ?", (first_task["id"],))
            break

    conn.commit()
    conn.close()

    return LearningPlanResponse(
        id=plan_id, career_name=career_name,
        daily_plan=plan.get("daily_plan", []), weekly_plan=plan.get("weekly_plan", []),
        monthly_roadmap=plan.get("monthly_roadmap", []), skills_to_learn=plan.get("skills_to_learn", []),
        resources=plan.get("resources", []), practice_project=plan.get("practice_project", ""),
    )


# =========================================================================
# PROGRESS TRACKER
# =========================================================================

@app.post("/api/progress/update", tags=["Progress"])
def update_progress(payload: UpdateProgressRequest, user_id: int = Depends(get_current_user_id)):
    """Toggle a single checklist task as completed / not completed."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM progress WHERE id = ? AND user_id = ?", (payload.progress_id, user_id))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Progress item not found.")

    cur.execute(
        "UPDATE progress SET is_completed = ?, completed_at = CASE WHEN ? THEN datetime('now') ELSE NULL END WHERE id = ?",
        (1 if payload.is_completed else 0, 1 if payload.is_completed else 0, payload.progress_id),
    )

    if payload.is_completed:
        _update_streak_and_badges(conn, cur, user_id)

    conn.commit()
    conn.close()
    return {"message": "Progress updated."}

@app.post("/api/progress/{progress_id}/start", response_model=TaskStartResponse, tags=["Progress"])
def start_task(progress_id: int, user_id: int = Depends(get_current_user_id)):
    """Starts a task, changing its status and generating questions if needed."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM progress WHERE id = ? AND user_id = ?", (progress_id, user_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found.")
        
    task = dict(row)
    if task["status"] == "locked":
        conn.close()
        raise HTTPException(status_code=400, detail="Task is locked. Complete previous tasks first.")
        
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    profile_row = cur.fetchone()
    profile = dict(profile_row) if profile_row else {}
    
    questions_json = task.get("questions")
    if not questions_json:
        # Generate questions
        q_list = gemini_service.generate_task_questions(profile, task["task_name"], task["task_type"])
        questions_json = json.dumps(q_list)
        
    cur.execute("UPDATE progress SET status = 'question_pending', questions = ? WHERE id = ?", (questions_json, progress_id))
    conn.commit()
    conn.close()
    
    return {
        "id": progress_id,
        "task_name": task["task_name"],
        "questions": json.loads(questions_json)
    }

@app.post("/api/progress/{progress_id}/submit", response_model=TaskSubmitResponse, tags=["Progress"])
def submit_task(progress_id: int, payload: TaskSubmitRequest, user_id: int = Depends(get_current_user_id)):
    """Submits answers for a task, marks it completed, and unlocks the next task."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM progress WHERE id = ? AND user_id = ?", (progress_id, user_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found.")
        
    # In a real app we might grade this via AI. For now, since they attempted it, we consider it a pass (100).
    score = 100
    answers_json = json.dumps([a.dict() for a in payload.answers])
    
    cur.execute("""
        UPDATE progress 
        SET status = 'completed', is_completed = 1, completed_at = datetime('now'), answers = ?, score = ? 
        WHERE id = ?
    """, (answers_json, score, progress_id))
    
    # Unlock logic based on hierarchy
    hierarchy = ["daily", "weekly", "monthly", "project"]
    current_type = row["task_type"]
    
    next_task = None
    
    # 1. Try to find next task of same type
    cur.execute("""
        SELECT id FROM progress 
        WHERE learning_plan_id = ? AND task_type = ? AND id > ? AND is_completed = 0 
        ORDER BY id ASC LIMIT 1
    """, (row["learning_plan_id"], current_type, progress_id))
    next_task = cur.fetchone()
    
    # 2. If none, find the next hierarchy tier
    if not next_task and current_type in hierarchy:
        current_idx = hierarchy.index(current_type)
        if current_idx < len(hierarchy) - 1:
            for next_idx in range(current_idx + 1, len(hierarchy)):
                next_type = hierarchy[next_idx]
                cur.execute("""
                    SELECT id FROM progress 
                    WHERE learning_plan_id = ? AND task_type = ? AND is_completed = 0 
                    ORDER BY id ASC LIMIT 1
                """, (row["learning_plan_id"], next_type))
                next_task = cur.fetchone()
                if next_task:
                    break
            
    next_unlocked = False
    if next_task:
        cur.execute("UPDATE progress SET status = 'available' WHERE id = ?", (next_task["id"],))
        next_unlocked = True
        
    _update_streak_and_badges(conn, cur, user_id)
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "score": score,
        "feedback": "Great job! Task completed.",
        "next_task_unlocked": next_unlocked
    }

@app.post("/api/progress/{progress_id}/submit_project", response_model=PracticeProjectSubmissionResponse, tags=["Progress"])
def submit_practice_project(progress_id: int, payload: PracticeProjectSubmitRequest, user_id: int = Depends(get_current_user_id)):
    """Submits a Practice Project for AI review."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.*, l.practice_project as brief 
        FROM progress p
        JOIN learning_plans l ON p.learning_plan_id = l.id
        WHERE p.id = ? AND p.user_id = ?
    """, (progress_id, user_id))
    row = cur.fetchone()
    
    if not row or row["task_type"] != "project":
        conn.close()
        raise HTTPException(status_code=404, detail="Project task not found.")
        
    if row["status"] == "locked":
        conn.close()
        raise HTTPException(status_code=400, detail="Project is locked. Complete previous tasks first.")
        
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    prof_row = cur.fetchone()
    skills = prof_row["skills"].split(",") if prof_row and prof_row["skills"] else []
    
    try:
        review = gemini_service.review_project_submission(
            phase_name="Practice Project",
            focus_skills=skills,
            project_brief=row["brief"],
            submission_type=payload.submission_type,
            content=payload.content
        )
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI review failed: {e}")
        
    score = review.get("score", 0)
    approved = review.get("approved", False)
    status = "completed" if approved else "in_progress"
    
    cur.execute("""
        UPDATE progress 
        SET status = ?, score = ?, is_completed = ?, completed_at = CASE WHEN ? THEN datetime('now') ELSE NULL END
        WHERE id = ?
    """, (status, score, 1 if approved else 0, 1 if approved else 0, progress_id))
    
    if approved:
        _update_streak_and_badges(conn, cur, user_id)
        
    conn.commit()
    conn.close()
    
    return {
        "id": progress_id,
        "status": status,
        "ai_summary": review.get("summary", ""),
        "ai_errors": review.get("errors", []),
        "ai_score": score,
        "next_task_unlocked": False
    }

# =========================================================================
# DASHBOARD
# =========================================================================

@app.get("/api/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
def get_dashboard(user_id: int = Depends(get_current_user_id)):
    """Aggregates profile + selected career + latest learning plan + progress % for one screen."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT student_code FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    student_code = user_row["student_code"] if user_row and user_row["student_code"] else ""

    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    profile_row = cur.fetchone()
    profile = dict(profile_row) if profile_row else None

    cur.execute("SELECT * FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
    career_row = cur.fetchone()
    selected_career = None
    if career_row:
        selected_career = dict(career_row)
        selected_career["required_skills"] = json.loads(selected_career["required_skills"] or "[]")

    cur.execute("SELECT * FROM learning_plans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    plan_row = cur.fetchone()
    learning_plan = None
    plan_id = None
    # Only return the plan if it matches the currently selected career, otherwise force regeneration
    if plan_row and (not selected_career or plan_row["career_name"] == selected_career["career_name"]):
        plan_id = plan_row["id"]
        learning_plan = {
            "id": plan_row["id"],
            "career_name": plan_row["career_name"],
            "daily_plan": json.loads(plan_row["daily_plan"] or "[]"),
            "weekly_plan": json.loads(plan_row["weekly_plan"] or "[]"),
            "monthly_roadmap": json.loads(plan_row["monthly_roadmap"] or "[]"),
            "skills_to_learn": json.loads(plan_row["skills_to_learn"] or "[]"),
            "resources": json.loads(plan_row["resources"] or "[]"),
            "practice_project": plan_row["practice_project"],
        }

    progress_items = []
    progress_percentage = 0.0
    has_phases = False
    time_to_job_weeks = None
    off_track_alerts = []

    if plan_id:
        # Check if a phased roadmap exists for this plan
        cur.execute("SELECT SUM(duration_weeks) as total_weeks, COUNT(*) as count FROM phases WHERE learning_plan_id = ?", (plan_id,))
        phase_stats = cur.fetchone()
        has_phases = phase_stats["count"] > 0
        
        prog_rows = []
        if has_phases:
            time_to_job_weeks = phase_stats["total_weeks"]

            # Show only tasks belonging to the active phase
            cur.execute("""
                SELECT p.* FROM progress p
                JOIN phases ph ON p.phase_id = ph.id
                WHERE p.learning_plan_id = ? AND ph.status = 'active'
                ORDER BY p.id
            """, (plan_id,))
            prog_rows = cur.fetchall()
            
            # Predict off-track alerts: Check if there are overdue tasks
            cur.execute("""
                SELECT COUNT(*) as overdue_count FROM progress p
                JOIN phases ph ON p.phase_id = ph.id
                WHERE p.learning_plan_id = ? AND ph.status = 'active' AND p.is_completed = 0 AND p.due_date < datetime('now')
            """, (plan_id,))
            overdue = cur.fetchone()["overdue_count"]
            if overdue > 0:
                off_track_alerts.append(f"You have {overdue} overdue task(s) in your active phase. You're slightly off track!")
            
            # Predictive off-track alert based on low progress but nearing phase end
            cur.execute("""
                SELECT ph.end_date, ph.phase_name FROM phases ph 
                WHERE ph.learning_plan_id = ? AND ph.status = 'active'
            """, (plan_id,))
            active_phase = cur.fetchone()
            if active_phase and active_phase["end_date"]:
                # If end date is within 3 days and progress < 50%, they are off track
                try:
                    from datetime import datetime, timedelta
                    end_dt = datetime.fromisoformat(active_phase["end_date"])
                    if end_dt - timedelta(days=3) < datetime.now() and progress_percentage < 50:
                        off_track_alerts.append("Phase end is approaching soon, but you are less than 50% done. Focus up!")
                except Exception:
                    pass

        else:
            # Show legacy tasks (phase_id is NULL)
            cur.execute("SELECT * FROM progress WHERE learning_plan_id = ? AND phase_id IS NULL ORDER BY id", (plan_id,))
            prog_rows = cur.fetchall()

        progress_items = [{
            "id": p["id"], "task_name": p["task_name"], "task_type": p["task_type"],
            "is_completed": bool(p["is_completed"]),
            "status": p["status"],
        } for p in prog_rows]
        if progress_items:
            done = sum(1 for p in progress_items if p["is_completed"])
            progress_percentage = round((done / len(progress_items)) * 100, 1)

    # Fetch streaks & badges for dashboard
    cur.execute("SELECT current_streak, longest_streak FROM student_profiles WHERE user_id = ?", (user_id,))
    streak_row = cur.fetchone()
    current_streak = streak_row["current_streak"] if streak_row else 0
    longest_streak = streak_row["longest_streak"] if streak_row else 0

    # Also add an off-track alert if they lost their streak
    if current_streak == 0 and longest_streak > 0:
        off_track_alerts.append("You lost your streak! Come back daily to stay consistent.")

    cur.execute("SELECT badge_code, badge_name, description, awarded_at FROM badges WHERE user_id = ? ORDER BY id DESC", (user_id,))
    badge_rows = cur.fetchall()
    badges = [{
        "badge_code": b["badge_code"],
        "badge_name": b["badge_name"],
        "description": b["description"] or "",
        "awarded_at": b["awarded_at"]
    } for b in badge_rows]

    conn.close()

    active_phase_name = active_phase["phase_name"] if has_phases and active_phase else None

    return DashboardResponse(
        profile=profile, selected_career=selected_career, learning_plan=learning_plan,
        progress=progress_items, progress_percentage=progress_percentage,
        has_phases=has_phases, active_phase_name=active_phase_name,
        current_streak=current_streak, longest_streak=longest_streak,
        badges=badges, student_code=student_code, time_to_job_weeks=time_to_job_weeks,
        off_track_alerts=off_track_alerts
    )


# =========================================================================
# ANALYTICS
# =========================================================================

@app.get("/api/analytics", response_model=AnalyticsResponse, tags=["Analytics"])
def get_analytics(user_id: int = Depends(get_current_user_id)):
    """
    Returns aggregated data for the Chart.js analytics dashboard.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM learning_plans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    plan_row = cur.fetchone()

    if not plan_row:
        conn.close()
        return {"has_plan": False}

    # 1. Trends: mock 7-day trend
    cur.execute("SELECT COUNT(*) as c FROM progress WHERE user_id = ? AND is_completed = 1", (user_id,))
    total_completed = cur.fetchone()["c"]
    
    import datetime
    import random
    today = datetime.date.today()
    labels = [(today - datetime.timedelta(days=i)).strftime("%a") for i in range(6, -1, -1)]
    trend_data = [0] * 7
    remaining_tasks = min(total_completed, 30) 
    for _ in range(remaining_tasks):
        trend_data[random.randint(0, 6)] += 1
    
    # 2. Progress Doughnut
    cur.execute("SELECT COUNT(*) as c FROM progress WHERE user_id = ? AND is_completed = 0", (user_id,))
    total_remaining = cur.fetchone()["c"]

    # 3. Skills Radar
    cur.execute("SELECT career_name, required_skills FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
    career_row = cur.fetchone()
    
    skill_labels = ["Frontend", "Backend", "Database", "DevOps", "AI"]
    skill_mastery = [0, 0, 0, 0, 0]
    skill_required = [0, 0, 0, 0, 0]
    
    if career_row and career_row["required_skills"]:
        req_skills = json.loads(career_row["required_skills"])
        skill_labels = [s.strip() for s in req_skills[:5]] if req_skills else skill_labels
        skill_mastery = [random.randint(20, 90) for _ in skill_labels]
        skill_required = [random.randint(70, 100) for _ in skill_labels]

    conn.close()
    
    return {
        "has_plan": True,
        "trends": {"labels": labels, "data": trend_data},
        "progress": {"completed": total_completed, "remaining": total_remaining},
        "skills": {"labels": skill_labels, "mastery": skill_mastery, "required": skill_required}
    }


# =========================================================================
# AI CHAT
# =========================================================================

@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
def chat(payload: ChatRequest, user_id: int = Depends(get_current_user_id)):
    """Free-form Q&A with the AI. Optionally uses the student's profile as context."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    profile = dict(row) if row else None

    history = [h.dict() for h in payload.history]

    try:
        reply = gemini_service.chat_reply(payload.message, history=history, profile=profile)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI chat failed: {e}")

    return ChatResponse(reply=reply)



TEST_PASS_PERCENTAGE = 60      # student needs >=60% to pass a phase test and unlock the next phase
MAX_TEST_VIOLATIONS = 3        # tab-switch / minimize events allowed before auto-submit


def _row_learning_plan_owner(cur, learning_plan_id: int, user_id: int):
    cur.execute("SELECT id, career_name FROM learning_plans WHERE id = ? AND user_id = ?", (learning_plan_id, user_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Learning plan not found.")
    return row


def _row_phase_owner(cur, phase_id: int, user_id: int):
    cur.execute("SELECT * FROM phases WHERE id = ? AND user_id = ?", (phase_id, user_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Phase not found.")
    return row


def _phase_tasks_incomplete_count(cur, phase_id: int) -> int:
    """Server-side enforcement mirroring the frontend gate: how many of this phase's weekly tasks are still unticked."""
    cur.execute("SELECT COUNT(*) c FROM progress WHERE phase_id = ? AND is_completed = 0", (phase_id,))
    return cur.fetchone()["c"]


def _activate_phase(cur, phase_row):
    """
    Materializes a phase's stored weekly_tasks into real `progress` rows with
    due dates spread one-per-week across the phase, and flips its status to
    'active'. Called when a phase first becomes reachable.
    """
    phase_dict = dict(phase_row)
    weekly_tasks = json.loads(phase_dict.get("weekly_tasks") or "[]")
    daily_habits = json.loads(phase_dict.get("daily_habits") or "[]")
    monthly_milestone = phase_dict.get("monthly_milestone")
    project_brief = phase_dict.get("project_brief")
    
    start = datetime.utcnow().date()
    
    # 1. Daily Habits
    for i, task in enumerate(daily_habits):
        due = start + timedelta(days=1)
        status = 'available' if i == 0 else 'locked'
        cur.execute("""
            INSERT INTO progress (user_id, learning_plan_id, task_name, task_type, phase_id, due_date, status)
            VALUES (?, ?, ?, 'daily', ?, ?, ?)
        """, (phase_row["user_id"], phase_row["learning_plan_id"], task, phase_row["id"], due.isoformat(), status))

    # 2. Weekly Tasks
    for i, task in enumerate(weekly_tasks):
        due = start + timedelta(weeks=i + 1)
        status = 'available' if i == 0 else 'locked'
        cur.execute("""
            INSERT INTO progress (user_id, learning_plan_id, task_name, task_type, phase_id, due_date, status)
            VALUES (?, ?, ?, 'weekly', ?, ?, ?)
        """, (phase_row["user_id"], phase_row["learning_plan_id"], task, phase_row["id"], due.isoformat(), status))
        
    # 3. Monthly Milestone
    if monthly_milestone:
        due = start + timedelta(days=30)
        cur.execute("""
            INSERT INTO progress (user_id, learning_plan_id, task_name, task_type, phase_id, due_date, status)
            VALUES (?, ?, ?, 'monthly', ?, ?, 'available')
        """, (phase_row["user_id"], phase_row["learning_plan_id"], monthly_milestone, phase_row["id"], due.isoformat()))
        
    # 4. Project Brief
    if project_brief:
        due = start + timedelta(weeks=phase_dict.get("duration_weeks", 4))
        cur.execute("""
            INSERT INTO progress (user_id, learning_plan_id, task_name, task_type, phase_id, due_date, status)
            VALUES (?, ?, ?, 'project', ?, ?, 'available')
        """, (phase_row["user_id"], phase_row["learning_plan_id"], project_brief, phase_row["id"], due.isoformat()))
    cur.execute(
        "UPDATE phases SET status='active', start_date=?, end_date=? WHERE id=?",
        (start.isoformat(), (start + timedelta(weeks=len(weekly_tasks) or phase_row["duration_weeks"])).isoformat(), phase_row["id"]),
    )


def _phase_to_response(cur, phase_row) -> PhaseResponse:
    cur.execute("SELECT * FROM progress WHERE phase_id = ? ORDER BY id", (phase_row["id"],))
    task_rows = cur.fetchall()
    tasks = [PhaseTask(id=t["id"], task_name=t["task_name"], is_completed=bool(t["is_completed"]), due_date=t["due_date"]) for t in task_rows]
    pct = round((sum(1 for t in tasks if t.is_completed) / len(tasks)) * 100, 1) if tasks else 0.0
    return PhaseResponse(
        id=phase_row["id"], phase_order=phase_row["phase_order"], phase_name=phase_row["phase_name"],
        description=phase_row["description"] or "", duration_weeks=phase_row["duration_weeks"],
        focus_skills=json.loads(phase_row["focus_skills"] or "[]"), project_brief=phase_row["project_brief"] or "",
        start_date=phase_row["start_date"], end_date=phase_row["end_date"], status=phase_row["status"],
        tasks=tasks, task_progress_percentage=pct,
    )


# =========================================================================
# PHASED ROADMAP (multi-month curriculum with gated project + test per phase)
# =========================================================================

@app.post("/api/phases/generate", response_model=list[PhaseResponse], tags=["Phased Roadmap"])
def generate_phases(payload: GeneratePhasesRequest, user_id: int = Depends(get_current_user_id)):
    """Breaks a learning plan's goal into sequential, realistically-timed phases. Phase 1 activates immediately; the rest start locked."""
    conn = get_connection()
    cur = conn.cursor()
    plan_row = _row_learning_plan_owner(cur, payload.learning_plan_id, user_id)

    cur.execute("SELECT * FROM phases WHERE learning_plan_id = ? ORDER BY phase_order", (payload.learning_plan_id,))
    existing = cur.fetchall()
    if existing:
        result = [_phase_to_response(cur, r) for r in existing]
        conn.close()
        return result

    profile = _get_profile_dict(user_id)
    
    # Fetch the most recent skill gap for this user and career to personalize the phases
    cur.execute("SELECT missing_skills FROM skill_gaps WHERE user_id = ? AND career_name = ? ORDER BY id DESC LIMIT 1", (user_id, plan_row["career_name"]))
    gap_row = cur.fetchone()
    missing_skills = json.loads(gap_row["missing_skills"]) if gap_row and gap_row["missing_skills"] else []

    try:
        phases = gemini_service.generate_phased_roadmap(profile, plan_row["career_name"], missing_skills)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI phased roadmap generation failed: {e}")

    for i, ph in enumerate(phases):
        cur.execute("""
            INSERT INTO phases (user_id, learning_plan_id, phase_order, phase_name, description,
                                 duration_weeks, focus_skills, daily_habits, weekly_tasks, monthly_milestone, project_brief, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, payload.learning_plan_id, i + 1, ph.get("phase_name", f"Phase {i+1}"),
            ph.get("description", ""), ph.get("duration_weeks", 4),
            json.dumps(ph.get("focus_skills", [])), json.dumps(ph.get("daily_habits", [])), json.dumps(ph.get("weekly_tasks", [])),
            ph.get("monthly_milestone", ""), ph.get("project_brief", ""), "locked",
        ))

    cur.execute("SELECT * FROM phases WHERE learning_plan_id = ? ORDER BY phase_order", (payload.learning_plan_id,))
    all_phases = cur.fetchall()
    if all_phases:
        _activate_phase(cur, all_phases[0])  # unlock phase 1 immediately

    conn.commit()
    cur.execute("SELECT * FROM phases WHERE learning_plan_id = ? ORDER BY phase_order", (payload.learning_plan_id,))
    result = [_phase_to_response(cur, r) for r in cur.fetchall()]
    conn.close()
    return result


@app.get("/api/phases", response_model=list[PhaseResponse], tags=["Phased Roadmap"])
def list_phases(user_id: int = Depends(get_current_user_id)):
    """All phases for the student's most recent learning plan."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM learning_plans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    plan = cur.fetchone()
    if not plan:
        conn.close()
        return []
    cur.execute("SELECT * FROM phases WHERE learning_plan_id = ? ORDER BY phase_order", (plan["id"],))
    result = [_phase_to_response(cur, r) for r in cur.fetchall()]
    conn.close()
    return result


# =========================================================================
# PROJECT SUBMISSION & AI REVIEW
# =========================================================================

@app.post("/api/projects/submit", response_model=ProjectSubmissionResponse, tags=["Projects"])
def submit_project(payload: ProjectSubmitRequest, user_id: int = Depends(get_current_user_id)):
    """Submit a phase-end project. AI reviews it immediately: approves (unlocking the test) or returns specific errors to fix and resubmit."""
    conn = get_connection()
    cur = conn.cursor()
    phase = _row_phase_owner(cur, payload.phase_id, user_id)

    if phase["status"] not in ("active", "project_review"):
        conn.close()
        raise HTTPException(status_code=400, detail=f"This phase is not open for project submission (status: {phase['status']}).")

    if phase["status"] == "active" and _phase_tasks_incomplete_count(cur, payload.phase_id) > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Tick off all of this phase's weekly tasks before submitting the project.")

    try:
        review = gemini_service.review_project_submission(
            phase["phase_name"], json.loads(phase["focus_skills"] or "[]"),
            phase["project_brief"] or "", payload.submission_type, payload.content,
        )
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI project review failed: {e}")

    approved = bool(review.get("approved"))
    errors = review.get("errors", [])
    score = int(review.get("score", 0) or 0)
    summary = review.get("summary", "")

    cur.execute("""
        INSERT INTO project_submissions (user_id, phase_id, submission_type, content, status, ai_summary, ai_errors, ai_score, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (user_id, payload.phase_id, payload.submission_type, payload.content,
          "approved" if approved else "needs_revision", summary, json.dumps(errors), score))
    submission_id = cur.lastrowid

    new_status = "project_approved" if approved else "project_review"
    cur.execute("UPDATE phases SET status=? WHERE id=?", (new_status, payload.phase_id))

    if approved:
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
            (user_id, f"Project approved for '{phase['phase_name']}'! The phase test is now unlocked."),
        )

    conn.commit()
    cur.execute("SELECT * FROM project_submissions WHERE id=?", (submission_id,))
    row = cur.fetchone()
    conn.close()

    return ProjectSubmissionResponse(
        id=row["id"], phase_id=row["phase_id"], status=row["status"], ai_summary=row["ai_summary"] or "",
        ai_errors=[ProjectError(**e) for e in json.loads(row["ai_errors"] or "[]")],
        ai_score=row["ai_score"] or 0, submitted_at=row["submitted_at"], file_name=row["file_name"],
    )


UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".cs", ".go", ".rb",
    ".php", ".html", ".css", ".json", ".md", ".txt", ".sql", ".sh", ".zip",
}


@app.post("/api/projects/submit-file", response_model=ProjectSubmissionResponse, tags=["Projects"])
async def submit_project_file(
    phase_id: int = Form(...),
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """
    Submit a phase-end project as an uploaded file (code archive or single
    source file) instead of pasted code or a link. The file is stored on
    disk under backend/uploads/, and for reviewable text files its content
    is also passed to the same AI reviewer used for pasted code.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (5 MB limit).")

    conn = get_connection()
    cur = conn.cursor()
    phase = _row_phase_owner(cur, phase_id, user_id)

    if phase["status"] not in ("active", "project_review"):
        conn.close()
        raise HTTPException(status_code=400, detail=f"This phase is not open for project submission (status: {phase['status']}).")

    if phase["status"] == "active" and _phase_tasks_incomplete_count(cur, phase_id) > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Tick off all of this phase's weekly tasks before submitting the project.")

    user_dir = os.path.join(UPLOAD_DIR, str(user_id), str(phase_id))
    os.makedirs(user_dir, exist_ok=True)
    safe_name = f"{secrets.token_hex(4)}_{os.path.basename(file.filename)}"
    dest_path = os.path.join(user_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(contents)

    # Text-based files get their content reviewed the same way pasted code does.
    # Archives (.zip) can't be inspected without unpacking, so the reviewer
    # gets a note explaining that instead and evaluates from the project brief alone.
    if ext == ".zip":
        review_content = f"[Uploaded archive '{file.filename}' — {len(contents)} bytes. Contents could not be inspected inline.]"
    else:
        try:
            review_content = contents.decode("utf-8", errors="replace")
        except Exception:
            review_content = f"[Uploaded file '{file.filename}' could not be decoded as text.]"

    try:
        review = gemini_service.review_project_submission(
            phase["phase_name"], json.loads(phase["focus_skills"] or "[]"),
            phase["project_brief"] or "", "file", review_content,
        )
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI project review failed: {e}")

    approved = bool(review.get("approved"))
    errors = review.get("errors", [])
    score = int(review.get("score", 0) or 0)
    summary = review.get("summary", "")

    cur.execute("""
        INSERT INTO project_submissions
            (user_id, phase_id, submission_type, content, status, ai_summary, ai_errors, ai_score, reviewed_at, file_path, file_name)
        VALUES (?, ?, 'file', ?, ?, ?, ?, ?, datetime('now'), ?, ?)
    """, (user_id, phase_id, f"[file upload: {file.filename}]",
          "approved" if approved else "needs_revision", summary, json.dumps(errors), score,
          dest_path, file.filename))
    submission_id = cur.lastrowid

    new_status = "project_approved" if approved else "project_review"
    cur.execute("UPDATE phases SET status=? WHERE id=?", (new_status, phase_id))

    if approved:
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
            (user_id, f"Project approved for '{phase['phase_name']}'! The phase test is now unlocked."),
        )

    conn.commit()
    cur.execute("SELECT * FROM project_submissions WHERE id=?", (submission_id,))
    row = cur.fetchone()
    conn.close()

    return ProjectSubmissionResponse(
        id=row["id"], phase_id=row["phase_id"], status=row["status"], ai_summary=row["ai_summary"] or "",
        ai_errors=[ProjectError(**e) for e in json.loads(row["ai_errors"] or "[]")],
        ai_score=row["ai_score"] or 0, submitted_at=row["submitted_at"], file_name=row["file_name"],
    )


@app.get("/api/projects/{phase_id}", response_model=Optional[ProjectSubmissionResponse], tags=["Projects"])
def get_latest_submission(phase_id: int, user_id: int = Depends(get_current_user_id)):
    """Latest submission + AI feedback for a phase, if any."""
    conn = get_connection()
    cur = conn.cursor()
    _row_phase_owner(cur, phase_id, user_id)
    cur.execute("SELECT * FROM project_submissions WHERE phase_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (phase_id, user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return ProjectSubmissionResponse(
        id=row["id"], phase_id=row["phase_id"], status=row["status"], ai_summary=row["ai_summary"] or "",
        ai_errors=[ProjectError(**e) for e in json.loads(row["ai_errors"] or "[]")],
        ai_score=row["ai_score"] or 0, submitted_at=row["submitted_at"], file_name=row["file_name"],
    )


# =========================================================================
# PROCTORED PHASE-END TEST (25 marks, browser-level anti-cheat)
# =========================================================================

@app.post("/api/tests/start", response_model=TestStartResponse, tags=["Tests"])
def start_test(payload: TestStartRequest, user_id: int = Depends(get_current_user_id)):
    """Generates a fresh 25-question test for an approved phase. The test must be taken fullscreen; the frontend reports violations via /api/tests/violation."""
    conn = get_connection()
    cur = conn.cursor()
    phase = _row_phase_owner(cur, payload.phase_id, user_id)

    if phase["status"] not in ("project_approved", "test_failed"):
        conn.close()
        raise HTTPException(status_code=400, detail="Submit and get your project approved before taking this phase's test.")

    try:
        questions = gemini_service.generate_phase_test(phase["phase_name"], json.loads(phase["focus_skills"] or "[]"))
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"AI test generation failed: {e}")

    cur.execute("""
        INSERT INTO test_attempts (user_id, phase_id, questions, total_marks, status)
        VALUES (?, ?, ?, ?, 'in_progress')
    """, (user_id, payload.phase_id, json.dumps(questions), len(questions)))
    attempt_id = cur.lastrowid
    conn.commit()
    conn.close()

    student_questions = [
        TestQuestionForStudent(index=i, question=q["question"], options=q["options"])
        for i, q in enumerate(questions)
    ]

    return TestStartResponse(
        attempt_id=attempt_id, phase_name=phase["phase_name"], total_marks=len(questions),
        questions=student_questions,
        instructions=[
            "This test will open in fullscreen and must stay that way for the entire attempt.",
            "Do NOT switch tabs, open another app, or minimize this window.",
            f"Doing so is logged as a violation; after {MAX_TEST_VIOLATIONS} violations the test auto-submits with your current answers.",
            f"You need {TEST_PASS_PERCENTAGE}% or higher to pass and unlock the next phase.",
            "Once you start, there is no pausing -- make sure you're ready before continuing.",
        ],
    )


def _grade_test_answers(attempt, answers: list) -> tuple[int, int, bool]:
    """Pure grading calculation shared by a normal submit and a violation-triggered auto-submit."""
    questions = json.loads(attempt["questions"])
    answer_map = {a.index: a.selected_option for a in answers}
    score = sum(1 for i, q in enumerate(questions) if answer_map.get(i) == q.get("correct_index"))
    total = len(questions)
    passed = total > 0 and (score / total) * 100 >= TEST_PASS_PERCENTAGE
    return score, total, passed


def _finalize_test_phase(cur, user_id: int, attempt, score: int, total: int, passed: bool) -> bool:
    """
    Shared post-grading logic (used by both a normal submit and an auto-submit
    triggered by too many proctoring violations): flips the phase to
    completed/test_failed, awards badges, unlocks the next phase on a pass,
    and raises the relevant notifications. Returns whether the next phase was unlocked.
    """
    next_unlocked = False
    if passed:
        cur.execute("UPDATE phases SET status='completed' WHERE id=?", (attempt["phase_id"],))
        cur.execute("SELECT * FROM phases WHERE id=?", (attempt["phase_id"],))
        this_phase = cur.fetchone()
        cur.execute(
            "SELECT * FROM phases WHERE learning_plan_id=? AND phase_order=?",
            (this_phase["learning_plan_id"], this_phase["phase_order"] + 1),
        )
        next_phase = cur.fetchone()

        # Award "Phase Champion" badge
        try:
            badge_code = f"phase_{this_phase['id']}_champion"
            badge_name = f"Phase Champion: {this_phase['phase_name']}"
            badge_desc = f"Successfully completed all requirements and passed the test for '{this_phase['phase_name']}'!"
            cur.execute("""
                INSERT INTO badges (user_id, badge_code, badge_name, description)
                VALUES (?, ?, ?, ?)
            """, (user_id, badge_code, badge_name, badge_desc))
            cur.execute(
                "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
                (user_id, f"Congratulations! You've earned the '{badge_name}' badge!"),
            )
        except sqlite3.IntegrityError:
            pass

        if next_phase:
            _activate_phase(cur, next_phase)
            next_unlocked = True
            cur.execute(
                "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
                (user_id, f"You passed '{this_phase['phase_name']}' ({score}/{total})! '{next_phase['phase_name']}' is now unlocked."),
            )
        else:
            # Award "Roadmap Master" badge
            try:
                cur.execute("SELECT career_name FROM learning_plans WHERE id = ?", (this_phase["learning_plan_id"],))
                lp_row = cur.fetchone()
                c_name = lp_row["career_name"] if lp_row else "selected career"
                cur.execute("""
                    INSERT INTO badges (user_id, badge_code, badge_name, description)
                    VALUES (?, 'roadmap_master', 'Roadmap Master', ?)
                """, (user_id, f"Mastered the entire '{c_name}' roadmap by completing all phases and tests!"))
                cur.execute(
                    "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
                    (user_id, "Congratulations! You've earned the 'Roadmap Master' badge!"),
                )
            except sqlite3.IntegrityError:
                pass

            cur.execute(
                "INSERT INTO notifications (user_id, type, message) VALUES (?, 'phase', ?)",
                (user_id, f"You passed '{this_phase['phase_name']}' ({score}/{total}) -- that was the final phase. Roadmap complete!"),
            )
    else:
        cur.execute("UPDATE phases SET status='test_failed' WHERE id=?", (attempt["phase_id"],))
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'test', ?)",
            (user_id, f"You scored {score}/{total} -- below the {TEST_PASS_PERCENTAGE}% pass mark. Review the phase material and retake when ready."),
        )
    return next_unlocked


@app.post("/api/tests/violation", tags=["Tests"])
def report_test_violation(payload: TestViolationRequest, user_id: int = Depends(get_current_user_id)):
    """
    Frontend calls this whenever it detects a tab-switch/minimize/blur during an
    active test, sending along whatever answers are currently selected. After
    MAX_TEST_VIOLATIONS this triggers an auto-submit that is graded exactly like
    a normal submission (using those answers) rather than being forced to zero,
    so the outcome reflects what the student had actually answered.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM test_attempts WHERE id = ? AND user_id = ?", (payload.attempt_id, user_id))
    attempt = cur.fetchone()
    if not attempt:
        conn.close()
        raise HTTPException(status_code=404, detail="Test attempt not found.")
    if attempt["status"] != "in_progress":
        conn.close()
        return {"violations": attempt["violations"], "auto_submitted": True}

    violations = attempt["violations"] + 1
    auto_submit = violations >= MAX_TEST_VIOLATIONS
    cur.execute("UPDATE test_attempts SET violations = ? WHERE id = ?", (violations, payload.attempt_id))

    result = {"violations": violations, "auto_submitted": auto_submit}

    if auto_submit:
        score, total, passed = _grade_test_answers(attempt, payload.answers)
        cur.execute(
            "UPDATE test_attempts SET answers=?, score=?, status='auto_submitted', completed_at=datetime('now') WHERE id=?",
            (json.dumps([a.dict() for a in payload.answers]), score, payload.attempt_id),
        )
        next_unlocked = _finalize_test_phase(cur, user_id, attempt, score, total, passed)
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'test', ?)",
            (user_id, (
                f"Your test was auto-submitted after {MAX_TEST_VIOLATIONS} violations (tab switch / minimize "
                f"detected), graded on the {len(payload.answers)} answer(s) you'd selected: {score}/{total}"
                f"{' -- you passed!' if passed else ' -- you can retake it.'}"
            )),
        )
        result.update({"score": score, "total_marks": total, "passed": passed, "next_phase_unlocked": next_unlocked})

    conn.commit()
    conn.close()
    return result


@app.post("/api/tests/submit", response_model=TestResultResponse, tags=["Tests"])
def submit_test(payload: TestSubmitRequest, user_id: int = Depends(get_current_user_id)):
    """Grades the test. Passing (>=60%) marks the phase completed and unlocks the next phase; failing allows a retake."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM test_attempts WHERE id = ? AND user_id = ?", (payload.attempt_id, user_id))
    attempt = cur.fetchone()
    if not attempt:
        conn.close()
        raise HTTPException(status_code=404, detail="Test attempt not found.")
    if attempt["status"] != "in_progress":
        conn.close()
        raise HTTPException(status_code=400, detail=f"This test attempt is already {attempt['status']}.")

    score, total, passed = _grade_test_answers(attempt, payload.answers)
    new_status = "passed" if passed else "failed"

    cur.execute("""
        UPDATE test_attempts SET answers=?, score=?, status=?, completed_at=datetime('now') WHERE id=?
    """, (json.dumps([a.dict() for a in payload.answers]), score, new_status, payload.attempt_id))

    next_unlocked = _finalize_test_phase(cur, user_id, attempt, score, total, passed)

    conn.commit()
    conn.close()

    return TestResultResponse(
        attempt_id=payload.attempt_id, score=score, total_marks=total, passed=passed,
        violations=attempt["violations"], status=new_status, next_phase_unlocked=next_unlocked,
    )


# =========================================================================
# NOTIFICATIONS (missed-deadline alerts + focus-mode distraction nudges)
# =========================================================================

def _check_deadlines_for_user(cur, user_id: int):
    """Finds overdue, incomplete phase tasks and raises a notification for each one, once."""
    today = datetime.utcnow().date().isoformat()
    cur.execute("""
        SELECT id, task_name FROM progress
        WHERE user_id = ? AND is_completed = 0 AND notified = 0
              AND due_date IS NOT NULL AND due_date < ?
    """, (user_id, today))
    overdue = cur.fetchall()
    if overdue and EMAIL_ALERTS_ENABLED:
        cur.execute("SELECT email, name FROM users WHERE id = ?", (user_id,))
        user_row = cur.fetchone()
    else:
        user_row = None
    for task in overdue:
        message = f"You missed the deadline for: \"{task['task_name']}\". Complete it soon to stay on your roadmap."
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'deadline', ?)",
            (user_id, message),
        )
        cur.execute("UPDATE progress SET notified = 1 WHERE id = ?", (task["id"],))
        if user_row:
            send_email_alert(user_row["email"], "Missed task deadline", f"Hi {user_row['name']},\n\n{message}")


def _check_all_deadlines_job():
    """APScheduler job: runs daily across every user so overdue-task alerts don't depend on someone opening the app."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM progress WHERE due_date IS NOT NULL")
    for row in cur.fetchall():
        _check_deadlines_for_user(cur, row["user_id"])
    conn.commit()
    conn.close()


STUDY_REMINDER_MESSAGES = [
    "You haven't logged any study activity today. A short session now keeps your streak alive.",
    "Reminder: today's tasks on your roadmap are still waiting for you.",
    "Don't lose momentum -- even {hours} focused minutes today keeps you on track.",
]


def _send_study_reminders_job():
    """
    APScheduler job: once a day, nudges any student who hasn't logged
    activity yet today with an in-app notification. The frontend's browser
    Notification permission (see api.js) turns this into a native OS
    notification for students who've opted in, even if the tab isn't focused.
    Capped to one reminder per user per day via last_reminder_date.
    """
    import random
    today = datetime.utcnow().date().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, daily_study_hours, last_activity_date, last_reminder_date
        FROM student_profiles
    """)
    for row in cur.fetchall():
        if row["last_activity_date"] == today:
            continue  # already studied today, no nudge needed
        if row["last_reminder_date"] == today:
            continue  # already reminded today
        message = random.choice(STUDY_REMINDER_MESSAGES).format(hours=row["daily_study_hours"] or 1)
        cur.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, 'study_reminder', ?)",
            (row["user_id"], message),
        )
        cur.execute(
            "UPDATE student_profiles SET last_reminder_date = ? WHERE user_id = ?",
            (today, row["user_id"]),
        )
    conn.commit()
    conn.close()


_scheduler_started = False


def _start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    scheduler = BackgroundScheduler()
    scheduler.add_job(_check_all_deadlines_job, "interval", hours=24, next_run_time=datetime.utcnow())
    # Runs at 6pm UTC daily -- a reasonable "you still have time to study today" nudge point.
    # Also fires once at startup so the feature is visible immediately without waiting a day.
    scheduler.add_job(_send_study_reminders_job, "cron", hour=18, minute=0)
    scheduler.add_job(_send_study_reminders_job, "date", run_date=datetime.utcnow() + timedelta(seconds=15))
    scheduler.start()
    _scheduler_started = True


@app.get("/api/notifications", response_model=list[NotificationItem], tags=["Notifications"])
def get_notifications(user_id: int = Depends(get_current_user_id)):
    """Also runs an on-demand deadline check for this user, so alerts show up immediately rather than waiting for the next scheduled run."""
    conn = get_connection()
    cur = conn.cursor()
    _check_deadlines_for_user(cur, user_id)
    conn.commit()
    cur.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [NotificationItem(id=r["id"], type=r["type"], message=r["message"], is_read=bool(r["is_read"]), created_at=r["created_at"]) for r in rows]


@app.post("/api/notifications/{notification_id}/read", tags=["Notifications"])
def mark_notification_read(notification_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id))
    conn.commit()
    conn.close()
    return {"message": "Marked as read."}


DISTRACTION_MESSAGES = [
    "Don't waste your time on {site} -- come back and finish today's task with your learning planner.",
    "Noticed you're on {site} during study time. Your roadmap is waiting -- let's get back to it.",
    "{site} can wait. A few more minutes here keeps your streak alive.",
]


@app.post("/api/notifications/distraction", response_model=NotificationItem, tags=["Notifications"])
def log_distraction(payload: DistractionPingRequest, user_id: int = Depends(get_current_user_id)):
    """
    Called by the frontend's optional 'Focus Mode' when it detects the browser
    tab lost focus (e.g. the student switched to a social media tab) during a
    declared study session. Note: a website can only see its OWN tab's focus
    state -- it cannot see activity in a separate native app -- so this is a
    browser-tab-level nudge, not full device-level monitoring.
    """
    import random
    message = random.choice(DISTRACTION_MESSAGES).format(site=payload.site or "that site")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO notifications (user_id, type, message) VALUES (?, 'distraction', ?)", (user_id, message))
    conn.commit()
    notif_id = cur.lastrowid
    cur.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,))
    row = cur.fetchone()
    conn.close()
    return NotificationItem(id=row["id"], type=row["type"], message=row["message"], is_read=bool(row["is_read"]), created_at=row["created_at"])


# =========================================================================
# STREAK AND BADGES HELPERS
# =========================================================================

def _update_streak_and_badges(conn, cur, user_id: int):
    """
    Called whenever a task is marked completed.
    Updates daily study streak, awards badges, and sends notifications.
    """
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    # 1. Fetch profile streak data
    cur.execute("SELECT current_streak, longest_streak, last_activity_date FROM student_profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    if not profile:
        return

    current_streak = profile["current_streak"] or 0
    longest_streak = profile["longest_streak"] or 0
    last_activity = profile["last_activity_date"]

    # 2. Update streak based on last activity
    if last_activity == today_str:
        # Already active today, streak remains same
        pass
    elif last_activity == yesterday_str:
        # Consecutive day activity
        current_streak += 1
        longest_streak = max(current_streak, longest_streak)
        last_activity = today_str
    else:
        # Reset streak to 1
        current_streak = 1
        longest_streak = max(current_streak, longest_streak)
        last_activity = today_str

    cur.execute("""
        UPDATE student_profiles
        SET current_streak = ?, longest_streak = ?, last_activity_date = ?
        WHERE user_id = ?
    """, (current_streak, longest_streak, last_activity, user_id))

    # Helper to insert a badge and notify
    def award_badge(badge_code: str, name: str, desc: str):
        try:
            cur.execute("""
                INSERT INTO badges (user_id, badge_code, badge_name, description)
                VALUES (?, ?, ?, ?)
            """, (user_id, badge_code, name, desc))
            # Send notification
            cur.execute("""
                INSERT INTO notifications (user_id, type, message)
                VALUES (?, 'phase', ?)
            """, (user_id, f"Congratulations! You've earned the '{name}' badge!"))
        except sqlite3.IntegrityError:
            # Already awarded
            pass

    # 3. Check Badge Rules
    # Rule 1: Completed first task -> "First Step"
    cur.execute("SELECT COUNT(*) as count FROM progress WHERE user_id = ? AND is_completed = 1", (user_id,))
    completed_tasks = cur.fetchone()["count"]
    if completed_tasks >= 1:
        award_badge("first_step", "First Step", "Completed your very first task on your learning journey!")

    # Rule 2: Consistency (3-day streak) -> "Consistency"
    if current_streak >= 3:
        award_badge("streak_3", "Consistency", "Maintained a 3-day learning streak!")

    # Rule 3: Dedicated (7-day streak) -> "Dedicated"
    if current_streak >= 7:
        award_badge("streak_7", "Dedicated", "Maintained a 7-day learning streak!")


# =========================================================================
# CERTIFICATES
# =========================================================================

@app.get("/api/certificate/{plan_id}", response_model=CertificateResponse, tags=["Certificates"])
def get_certificate(plan_id: int, user_id: int = Depends(get_current_user_id)):
    """Fetch certificate metadata if the learning plan's roadmap is fully completed."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Verify plan exists and user owns it
    cur.execute("SELECT career_name, created_at FROM learning_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
    plan = cur.fetchone()
    if not plan:
        conn.close()
        raise HTTPException(status_code=404, detail="Learning plan not found.")

    # 2. Check if all phases are completed
    cur.execute("SELECT COUNT(*) as count FROM phases WHERE learning_plan_id = ?", (plan_id,))
    total_phases = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) as count FROM phases WHERE learning_plan_id = ? AND status = 'completed'", (plan_id,))
    completed_phases = cur.fetchone()["count"]

    if total_phases == 0 or completed_phases < total_phases:
        conn.close()
        raise HTTPException(status_code=400, detail="You must complete all phases and pass their tests before generating a certificate.")

    # 3. Get student name
    cur.execute("SELECT name FROM student_profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    student_name = profile["name"] if profile and profile["name"] else "Graduate"

    # Get last phase completion date
    cur.execute("""
        SELECT completed_at FROM test_attempts 
        WHERE phase_id IN (SELECT id FROM phases WHERE learning_plan_id = ?) AND status = 'passed'
        ORDER BY id DESC LIMIT 1
    """, (plan_id,))
    test_attempt = cur.fetchone()
    completed_at = test_attempt["completed_at"] if test_attempt and test_attempt["completed_at"] else date.today().isoformat()

    # Generate unique certificate verification code on-the-fly
    import hashlib
    h = hashlib.sha256(f"{user_id}-{plan_id}-{completed_at}".encode())
    cert_code = f"TR-{h.hexdigest()[:12].upper()}"

    conn.close()
    return CertificateResponse(
        student_name=student_name,
        career_name=plan["career_name"],
        completed_at=completed_at[:10],
        certificate_code=cert_code,
    )


# =========================================================================
# LEADERBOARD
# =========================================================================

@app.get("/api/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
def get_leaderboard(user_id: int = Depends(get_current_user_id)):
    """
    Ranks all students by a simple points formula: streak days + (badges x 5)
    + (completed phases x 10). Top 20 shown; the caller is flagged with
    is_you even if they fall outside the top 20 is not included -- only
    ranks within the returned list are marked.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sp.user_id,
            COALESCE(sp.name, u.name) AS name,
            COALESCE(sp.current_streak, 0) AS current_streak,
            COALESCE(sp.longest_streak, 0) AS longest_streak,
            (SELECT COUNT(*) FROM badges b WHERE b.user_id = sp.user_id) AS badge_count,
            (SELECT COUNT(*) FROM phases p WHERE p.user_id = sp.user_id AND p.status = 'completed') AS phases_completed
        FROM student_profiles sp
        JOIN users u ON u.id = sp.user_id
    """)
    rows = cur.fetchall()
    conn.close()

    scored = []
    for r in rows:
        points = r["current_streak"] + r["badge_count"] * 5 + r["phases_completed"] * 10
        scored.append({
            "user_id": r["user_id"], "name": r["name"], "current_streak": r["current_streak"],
            "longest_streak": r["longest_streak"], "badge_count": r["badge_count"],
            "phases_completed": r["phases_completed"], "points": points,
        })
    scored.sort(key=lambda x: x["points"], reverse=True)

    entries = [
        LeaderboardEntry(
            rank=i + 1, name=s["name"] or "Student", current_streak=s["current_streak"],
            longest_streak=s["longest_streak"], badge_count=s["badge_count"],
            phases_completed=s["phases_completed"], points=s["points"], is_you=(s["user_id"] == user_id),
        )
        for i, s in enumerate(scored[:20])
    ]
    return LeaderboardResponse(entries=entries)





# =========================================================================
# GROUPS & CHAT
# =========================================================================

@app.post("/api/groups", response_model=GroupResponse, tags=["Groups"])
def create_group(payload: GroupCreateRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO groups (name, description) VALUES (?, ?)", (payload.name, payload.description))
    group_id = cur.lastrowid
    cur.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
    conn.commit()
    cur.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return GroupResponse(**dict(row))

@app.get("/api/groups", tags=["Groups"])
def list_groups(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT g.*, 
               CASE WHEN gm.user_id IS NOT NULL THEN 1 ELSE 0 END as is_member 
        FROM groups g 
        LEFT JOIN group_members gm ON g.id = gm.group_id AND gm.user_id = ?
        ORDER BY g.created_at DESC
    ''', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/groups/{group_id}/join", tags=["Groups"])
def join_group(group_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM groups WHERE id = ?", (group_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Group not found")
    try:
        cur.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return {"message": "Joined group successfully."}

@app.get("/api/groups/{group_id}/messages", response_model=list[GroupMessageResponse], tags=["Groups"])
def get_group_messages(group_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Not a member of this group")
    
    cur.execute("SELECT * FROM group_messages WHERE group_id = ? ORDER BY id ASC", (group_id,))
    rows = cur.fetchall()
    conn.close()
    return [GroupMessageResponse(**dict(r)) for r in rows]

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: int):
        await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def disconnect(self, websocket: WebSocket, group_id: int):
        if group_id in self.active_connections and websocket in self.active_connections[group_id]:
            self.active_connections[group_id].remove(websocket)

    async def broadcast(self, message: dict, group_id: int):
        if group_id in self.active_connections:
            for connection in self.active_connections[group_id]:
                await connection.send_json(message)

manager = ConnectionManager()

from auth_utils import decode_access_token

@app.websocket("/ws/groups/{group_id}")
async def websocket_group_chat(websocket: WebSocket, group_id: int, token: Optional[str] = Query(None)):
    cookie_token = websocket.cookies.get("alp_session")
    active_token = token or cookie_token
    if not active_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    payload = decode_access_token(active_token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id = int(payload["sub"])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    if not cur.fetchone():
        conn.close()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    cur.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    user_name = user_row["name"] if user_row else "Unknown"
    conn.close()

    await manager.connect(websocket, group_id)
    try:
        while True:
            data = await websocket.receive_text()
            
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO group_messages (group_id, user_id, sender_name, message) VALUES (?, ?, ?, ?)",
                (group_id, user_id, user_name, data)
            )
            msg_id = cur.lastrowid
            conn.commit()
            
            cur.execute("SELECT * FROM group_messages WHERE id = ?", (msg_id,))
            msg_row = cur.fetchone()
            conn.close()
            
            msg_dict = dict(msg_row)
            await manager.broadcast(msg_dict, group_id)
            
            if "@ai" in data.lower():
                try:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT sender_name, message FROM group_messages WHERE group_id = ? ORDER BY id DESC LIMIT 15", (group_id,))
                    recent_msgs = cur.fetchall()
                    history = [{"sender_name": row["sender_name"], "message": row["message"]} for row in reversed(recent_msgs)]
                    conn.close()

                    from fastapi.concurrency import run_in_threadpool
                    ai_reply_dict = await run_in_threadpool(gemini_service.chat_with_ai, data, history, user_name)
                    ai_reply = ai_reply_dict.get("reply", "No response.")
                    
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO group_messages (group_id, user_id, sender_name, message) VALUES (?, NULL, ?, ?)",
                        (group_id, "AI Assistant", ai_reply)
                    )
                    ai_msg_id = cur.lastrowid
                    conn.commit()
                    
                    cur.execute("SELECT * FROM group_messages WHERE id = ?", (ai_msg_id,))
                    ai_msg_row = cur.fetchone()
                    conn.close()
                    
                    await manager.broadcast(dict(ai_msg_row), group_id)
                except Exception as e:
                    print(f"AI error: {e}")
                    await manager.broadcast({
                        "user_id": None,
                        "sender_name": "AI Assistant",
                        "message": "AI is temporarily unavailable. Please try again later.",
                    }, group_id)
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, group_id)


# =========================================================================
# VIDEO MEET AI SUMMARY
# =========================================================================

@app.post("/api/meet/summarize", response_model=ChatResponse, tags=["Video Meet"])
async def summarize_meet(payload: SummarizeMeetRequest, user_id: int = Depends(get_current_user_id)):
    from fastapi.concurrency import run_in_threadpool
    try:
        reply = await run_in_threadpool(gemini_service.summarize_meeting, payload.content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI summary failed: {e}")
    return ChatResponse(reply=reply)

@app.post("/api/groups/meet/summarize", tags=["Groups"])
def summarize_meet_groups(req: SummarizeMeetRequest, user_id: int = Depends(get_current_user_id)):
    """Summarizes a video meet transcript via Gemini."""
    try:
        summary = gemini_service.summarize_meeting(req.content)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================================
# PORTFOLIO & RESUME
# =========================================================================

@app.get("/api/resume/export", tags=["Portfolio"])
def export_user_resume(user_id: int = Depends(get_current_user_id)):
    """Exports a markdown resume using AI."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    
    if not profile:
        conn.close()
        raise HTTPException(status_code=404, detail="Profile not found.")

    cur.execute("SELECT task_name, due_date as updated_at FROM progress WHERE user_id = ? AND is_completed = 1 AND task_type = 'project'", (user_id,))
    projects = cur.fetchall()
    conn.close()

    resume_json = gemini_service.export_resume(dict(profile), [dict(p) for p in projects])
    return {"resume_json": resume_json}

@app.get("/portfolio/{username}", tags=["Portfolio"])
def get_public_portfolio(username: str):
    """Public read-only portfolio endpoint."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT u.id, u.name, p.custom_url_slug FROM users u JOIN portfolios p ON u.id = p.user_id WHERE p.custom_url_slug = ? AND p.is_public = 1", (username,))
    portfolio = cur.fetchone()
    
    if not portfolio:
        conn.close()
        raise HTTPException(status_code=404, detail="Portfolio not found or not public.")
        
    user_id = portfolio["id"]
    cur.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    
    cur.execute("SELECT badge_name, description FROM badges WHERE user_id = ?", (user_id,))
    badges = cur.fetchall()
    conn.close()
    
    return {
        "name": portfolio["name"],
        "profile": dict(profile) if profile else None,
        "badges": [dict(b) for b in badges]
    }

# =========================================================================
# GAMIFICATION & FRIENDS & NETWORKING
# =========================================================================

@app.get("/api/users/search", response_model=UserSearchResponse, tags=["Networking"])
def search_users(code: str = ""):
    """Search for users by their student code."""
    if not code or len(code) < 3:
        return UserSearchResponse(users=[])
        
    conn = get_connection()
    cur = conn.cursor()
    # Search by student_code
    cur.execute("""
        SELECT u.id, u.name, u.student_code, p.career_goal
        FROM users u
        LEFT JOIN student_profiles p ON u.id = p.user_id
        WHERE u.student_code LIKE ?
        LIMIT 10
    """, (f"%{code}%",))
    
    rows = cur.fetchall()
    conn.close()
    
    users = []
    for row in rows:
        users.append(UserSearchItem(
            user_id=row["id"],
            name=row["name"],
            student_code=row["student_code"],
            career_goal=row["career_goal"]
        ))
        
    return UserSearchResponse(users=users)


@app.get("/api/peers/recommendations", response_model=PeerRecommendationResponse, tags=["Networking"])
def get_peer_recommendations(user_id: int = Depends(get_current_user_id)):
    """Predictive Peer Matching: Find students on the same career path or similar learning phase."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get current user's career and active phase
    cur.execute("SELECT career_name FROM careers WHERE user_id = ? AND is_selected = 1", (user_id,))
    my_career = cur.fetchone()
    my_career_name = my_career["career_name"] if my_career else None
    
    rows = []
    # We look for users with the same selected career
    if my_career_name:
        cur.execute("""
            SELECT u.id, u.name, u.student_code, c.career_name as career_goal
            FROM users u
            JOIN careers c ON u.id = c.user_id
            WHERE c.career_name = ? AND c.is_selected = 1 AND u.id != ?
            ORDER BY u.id DESC
            LIMIT 5
        """, (my_career_name, user_id))
        rows = cur.fetchall()
        
    # Fallback to random peers if no career selected OR no exact matches found
    if not rows:
        cur.execute("""
            SELECT u.id, u.name, u.student_code, p.career_goal
            FROM users u
            LEFT JOIN student_profiles p ON u.id = p.user_id
            WHERE u.id != ?
            ORDER BY RANDOM()
            LIMIT 5
        """, (user_id,))
        rows = cur.fetchall()

    conn.close()

    peers = []
    for row in rows:
        peers.append(PeerRecommendationItem(
            user_id=row["id"],
            name=row["name"],
            student_code=row["student_code"] or "",
            career_goal=row["career_goal"] or "Undecided",
            phase_name="" # Not explicitly storing phase for now, just matching on career
        ))

    return PeerRecommendationResponse(peers=peers)


class AddFriendRequest(BaseModel):
    friend_username: str

@app.post("/api/friends/add", tags=["Gamification"])
def add_friend(req: AddFriendRequest, user_id: int = Depends(get_current_user_id)):
    """Add a friend by their exact name/username."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE name = ?", (req.friend_username,))
    friend = cur.fetchone()
    if not friend:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")
        
    friend_id = friend["id"]
    if friend_id == user_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot add yourself.")
        
    try:
        cur.execute("INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, 'accepted')", (user_id, friend_id))
        cur.execute("INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, 'accepted')", (friend_id, user_id))
        conn.commit()
    except Exception:
        # Already friends
        pass
    finally:
        conn.close()
        
    return {"message": "Friend added successfully!"}

@app.get("/api/friends/activity", tags=["Gamification"])
def get_friend_activity(user_id: int = Depends(get_current_user_id)):
    """Get recent badges/achievements from friends to populate activity feed."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT u.name, b.badge_name, b.awarded_at 
        FROM badges b 
        JOIN users u ON b.user_id = u.id 
        JOIN friends f ON f.friend_id = b.user_id 
        WHERE f.user_id = ?
        ORDER BY b.awarded_at DESC LIMIT 20
    """, (user_id,))
    
    activities = cur.fetchall()
    conn.close()
    
    return {"activities": [dict(a) for a in activities]}


# =========================================================================
# STATIC FRONTEND (serves the ../frontend folder)
# =========================================================================

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")

    @app.get("/", tags=["Frontend"])
    def serve_home():
        return FileResponse(os.path.join(FRONTEND_DIR, "pages", "index.html"))

    @app.get("/{page_name}.html", tags=["Frontend"])
    def serve_page(page_name: str):
        file_path = os.path.join(FRONTEND_DIR, "pages", f"{page_name}.html")
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="Page not found.")
