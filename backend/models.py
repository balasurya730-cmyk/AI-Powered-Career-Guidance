"""
models.py
---------
Pydantic schemas used to validate incoming requests and shape outgoing
responses. Keeping these separate from database.py keeps validation logic
(what a valid request looks like) apart from storage logic (how it's saved).
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


# ---------------- AUTH ----------------

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    # Only populated when email sending isn't configured (local/dev use), so the
    # reset flow still works without an SMTP provider set up. Never sent once
    # EMAIL_ALERTS_ENABLED is true - see main.py.
    reset_link: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    email: str


# ---------------- STUDENT PROFILE ----------------

class ProfileRequest(BaseModel):
    name: str
    education: str
    department: str
    college: str
    current_year: str
    skills: str            # comma separated string, e.g. "Python, HTML, CSS"
    interests: str          # comma separated string, e.g. "Web Dev, AI, Robotics"
    daily_study_hours: float
    career_goal: Optional[str] = None   # optional - if empty, AI advisor kicks in


class ProfileResponse(ProfileRequest):
    user_id: int


# ---------------- NETWORKING & SEARCH ----------------

class UserSearchItem(BaseModel):
    user_id: int
    name: str
    student_code: str
    career_goal: Optional[str] = None

class UserSearchResponse(BaseModel):
    users: List[UserSearchItem]

class PeerRecommendationItem(BaseModel):
    user_id: int
    name: str
    student_code: str
    career_goal: str
    phase_name: str

class PeerRecommendationResponse(BaseModel):
    peers: List[PeerRecommendationItem]


# ---------------- CAREER ADVISOR ----------------

class CareerAdvisorQuestionsRequest(BaseModel):
    """Answers to the simple follow-up questions asked when career_goal is empty."""
    favorite_subjects: str
    strengths: str
    preferred_work_style: str   # e.g. "team-based", "independent", "research", "hands-on"


class CareerOption(BaseModel):
    career_name: str
    description: str
    required_skills: List[str]
    future_scope: str
    reason: str


class CareerRecommendationResponse(BaseModel):
    careers: List[CareerOption]


class SelectCareerRequest(BaseModel):
    career_id: int


class DirectoryCareerItem(BaseModel):
    id: int
    career_name: str
    description: str
    required_skills: List[str]
    future_scope: str


class DirectoryResponse(BaseModel):
    careers: List[DirectoryCareerItem]


class SelectDirectoryCareerRequest(BaseModel):
    global_career_id: int


class GenerateDirectoryCareerRequest(BaseModel):
    career_name: str


class MatchScoreRequest(BaseModel):
    career_name: str


class MatchScoreResponse(BaseModel):
    score: int
    reason: str


# ---------------- SKILL GAP ANALYSIS + COURSE RECOMMENDATIONS ----------------

class SkillGapAnalyzeRequest(BaseModel):
    # Optional: analyze against a specific recommended career instead of the
    # currently-selected one (e.g. comparing before choosing).
    career_id: Optional[int] = None

class MissingSkillItem(BaseModel):
    skill: str
    priority: int = 5
    reasoning: str = ""

class SkillGapResponse(BaseModel):
    id: int
    career_name: str
    matched_skills: List[str]
    missing_skills: List[MissingSkillItem]
    summary: str
    created_at: str


class CourseRecommendationRequest(BaseModel):
    skill_gap_id: Optional[int] = None   # defaults to the most recent analysis


class CourseRecommendationItem(BaseModel):
    id: int
    skill_name: str
    title: str
    provider: str
    resource_type: str   # course | tutorial | certification
    url: str
    description: str


class CourseRecommendationResponse(BaseModel):
    skill_gap_id: int
    courses: List[CourseRecommendationItem]


# ---------------- LEARNING PLAN ----------------

class GeneratePlanRequest(BaseModel):
    career_id: Optional[int] = None
    career_name: Optional[str] = None   # allow generating directly from a known career goal


class LearningPlanResponse(BaseModel):
    id: int
    career_name: str
    daily_plan: List[str]
    weekly_plan: List[str]
    monthly_roadmap: List[str]
    skills_to_learn: List[str]
    resources: List[str]
    practice_project: str


# ---------------- PROGRESS ----------------

class UpdateProgressRequest(BaseModel):
    progress_id: int
    is_completed: bool


class ProgressItem(BaseModel):
    id: int
    task_name: str
    task_type: str
    is_completed: bool


# ---------------- DASHBOARD ----------------

class BadgeResponseItem(BaseModel):
    badge_code: str
    badge_name: str
    description: str
    awarded_at: str


class DashboardResponse(BaseModel):
    profile: Optional[dict]
    selected_career: Optional[dict]
    learning_plan: Optional[dict]
    progress: List[ProgressItem]
    progress_percentage: float
    has_phases: bool = False
    current_streak: int = 0
    longest_streak: int = 0
    badges: List[BadgeResponseItem] = Field(default_factory=list)
    student_code: str = ""
    time_to_job_weeks: Optional[int] = None
    off_track_alerts: List[str] = Field(default_factory=list)


# ---------------- ANALYTICS ----------------

class TrendData(BaseModel):
    labels: List[str]
    data: List[int]

class ProgressData(BaseModel):
    completed: int
    remaining: int

class SkillData(BaseModel):
    labels: List[str]
    mastery: List[int]
    required: List[int]

class AnalyticsResponse(BaseModel):
    has_plan: bool
    trends: Optional[TrendData] = None
    progress: Optional[ProgressData] = None
    skills: Optional[SkillData] = None


# ---------------- PHASED ROADMAP ----------------

class GeneratePhasesRequest(BaseModel):
    learning_plan_id: int


class PhaseTask(BaseModel):
    id: int
    task_name: str
    is_completed: bool
    due_date: Optional[str] = None


class PhaseResponse(BaseModel):
    id: int
    phase_order: int
    phase_name: str
    description: str
    duration_weeks: int
    focus_skills: List[str]
    project_brief: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    tasks: List[PhaseTask] = Field(default_factory=list)
    task_progress_percentage: float = 0.0


# ---------------- PROJECT SUBMISSION & REVIEW ----------------

class ProjectSubmitRequest(BaseModel):
    phase_id: int
    submission_type: str = Field(..., pattern="^(code|link)$")
    content: str = Field(..., min_length=1, max_length=20000)


class ProjectError(BaseModel):
    issue: str
    why: str
    fix: str


class ProjectSubmissionResponse(BaseModel):
    id: int
    phase_id: int
    status: str
    ai_summary: str
    ai_errors: List[ProjectError]
    ai_score: int
    submitted_at: str
    file_name: Optional[str] = None


# ---------------- PROCTORED PHASE TEST ----------------

class TestStartRequest(BaseModel):
    phase_id: int


class TestQuestionForStudent(BaseModel):
    index: int
    question: str
    options: List[str]


class TestStartResponse(BaseModel):
    attempt_id: int
    phase_name: str
    total_marks: int
    questions: List[TestQuestionForStudent]
    instructions: List[str]


class TestAnswer(BaseModel):
    index: int
    selected_option: int


class TestViolationRequest(BaseModel):
    attempt_id: int
    reason: str = "tab_switch_or_minimize"
    # The student's currently-selected answers at the moment of the violation.
    # Sent so that if this violation triggers an auto-submit, grading reflects
    # what was actually answered instead of being forced to zero.
    answers: List[TestAnswer] = Field(default_factory=list)


class TestSubmitRequest(BaseModel):
    attempt_id: int
    answers: List[TestAnswer]


class TestResultResponse(BaseModel):
    attempt_id: int
    score: int
    total_marks: int
    passed: bool
    violations: int
    status: str
    next_phase_unlocked: bool


# ---------------- NOTIFICATIONS ----------------

class NotificationItem(BaseModel):
    id: int
    type: str
    message: str
    is_read: bool
    created_at: str


class DistractionPingRequest(BaseModel):
    site: str = Field(..., max_length=100)


# ---------------- AI CHAT ----------------

class ChatMessage(BaseModel):
    role: str    # "user" or "assistant"
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


# ---------------- CERTIFICATE ----------------

class CertificateResponse(BaseModel):
    student_name: str
    career_name: str
    completed_at: str
    certificate_code: str


# ---------------- LEADERBOARD ----------------

class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    current_streak: int
    longest_streak: int
    badge_count: int
    phases_completed: int
    points: int
    is_you: bool = False


class LeaderboardResponse(BaseModel):
    entries: List[LeaderboardEntry]


# ---------------- MOCK INTERVIEW ----------------

class InterviewQuestionForStudent(BaseModel):
    index: int
    question: str
    type: str                 # "behavioral" | "technical"
    time_limit_seconds: int


class InterviewStartResponse(BaseModel):
    session_id: int
    career_name: str
    questions: List[InterviewQuestionForStudent]


class InterviewAnswerRequest(BaseModel):
    session_id: int
    index: int
    answer: str = Field(..., max_length=4000)
    time_taken_seconds: int = 0


class InterviewAnswerFeedback(BaseModel):
    index: int
    score: int                # 0-10 for this answer
    feedback: str
    strengths: List[str]
    improvements: List[str]


class InterviewFinishRequest(BaseModel):
    session_id: int


class InterviewSummary(BaseModel):
    summary: str
    strengths: List[str]
    improvements: List[str]


class InterviewFinishResponse(BaseModel):
    session_id: int
    overall_score: int        # 0-100 readiness score
    answered_count: int
    total_questions: int
    per_question_feedback: List[InterviewAnswerFeedback]
    overall_feedback: InterviewSummary


class InterviewHistoryItem(BaseModel):
    session_id: int
    career_name: str
    status: str
    overall_score: Optional[int] = None
    created_at: str
    completed_at: Optional[str] = None


class InterviewHistoryResponse(BaseModel):
    sessions: List[InterviewHistoryItem]


class InterviewDetailResponse(BaseModel):
    session_id: int
    career_name: str
    status: str
    questions: List[InterviewQuestionForStudent]
    answers: List[InterviewAnswerRequest] = Field(default_factory=list)
    per_question_feedback: List[InterviewAnswerFeedback] = Field(default_factory=list)
    overall_score: Optional[int] = None
    overall_feedback: Optional[InterviewSummary] = None
    created_at: str
    completed_at: Optional[str] = None


# ---------------- GROUPS & CHAT ----------------

class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None

class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: str

class GroupMessageResponse(BaseModel):
    id: int
    group_id: int
    user_id: Optional[int] = None  # None means AI or system message
    sender_name: str
    message: str
    created_at: str

class SummarizeMeetRequest(BaseModel):
    content: str
