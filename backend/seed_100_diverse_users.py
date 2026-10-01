import random
import secrets
from database import init_db, get_connection
from auth_utils import hash_password

# A highly diverse set of professional and academic personas
PERSONAS = [
    {"dept": "Medicine", "skills": "Anatomy, Patient Care, Diagnostics", "interests": "Surgery, Public Health", "career": "Doctor"},
    {"dept": "Education", "skills": "Lesson Planning, Public Speaking, Patience", "interests": "Child Development, Pedagogy", "career": "Teacher"},
    {"dept": "Culinary Arts", "skills": "Cooking, Baking, Kitchen Management", "interests": "Fine Dining, Nutrition", "career": "Executive Chef"},
    {"dept": "Fine Arts", "skills": "Painting, Sculpting, Art History", "interests": "Exhibitions, Digital Art", "career": "Contemporary Artist"},
    {"dept": "Agriculture", "skills": "Crop Management, Soil Science, Machinery", "interests": "Sustainable Farming, Botany", "career": "Farmer"},
    {"dept": "Law", "skills": "Legal Research, Argumentation, Writing", "interests": "Corporate Law, Criminal Justice", "career": "Lawyer"},
    {"dept": "Construction", "skills": "Carpentry, Blueprint Reading, Safety Protocol", "interests": "Architecture, Real Estate", "career": "General Contractor"},
    {"dept": "Music", "skills": "Sight Reading, Composition, Performance", "interests": "Jazz, Orchestral Arrangement", "career": "Musician"},
    {"dept": "Veterinary", "skills": "Animal Handling, Biology, Surgery", "interests": "Wildlife Conservation, Zoology", "career": "Veterinarian"},
    {"dept": "Automotive", "skills": "Mechanics, Diagnostics, Repair", "interests": "Electric Vehicles, Racing", "career": "Mechanic"},
    {"dept": "Aviation", "skills": "Flight Navigation, Meteorology, Focus", "interests": "Aerospace, Travel", "career": "Pilot"},
    {"dept": "Journalism", "skills": "Investigative Reporting, Writing, Interviewing", "interests": "Politics, Current Events", "career": "Journalist"},
    {"dept": "Psychology", "skills": "Active Listening, Therapy, Empathy", "interests": "Mental Health, Cognitive Science", "career": "Psychologist"},
    {"dept": "Retail", "skills": "Customer Service, Inventory, Sales", "interests": "Fashion, Marketing", "career": "Store Manager"},
    {"dept": "Plumbing", "skills": "Pipe Fitting, Maintenance, Problem Solving", "interests": "Infrastructure, Contracting", "career": "Master Plumber"}
]

NAMES = ["Aarav", "Priya", "Vikram", "Neha", "Rohan", "Anjali", "Arjun", "Kavya", "Aditya", "Sneha", 
         "Liam", "Emma", "Noah", "Olivia", "William", "Ava", "James", "Isabella", "Oliver", "Sophia"]
LAST_NAMES = ["Patel", "Sharma", "Singh", "Kumar", "Gupta", "Desai", "Joshi", "Verma", 
              "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
COLLEGES = ["Global University", "City College", "State Institute", "National Academy", "Tech University"]

def seed_users(count=100):
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    
    password_hash = hash_password("test1234")
    
    users_inserted = 0
    
    for i in range(count):
        first = random.choice(NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"user_{secrets.token_hex(4)}@test.com"
        student_code = f"STU-{secrets.token_hex(4).upper()}"
        
        persona = random.choice(PERSONAS)
        
        try:
            # Insert User
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role, student_code) VALUES (?, ?, ?, ?, ?)",
                (name, email, password_hash, "student", student_code),
            )
            user_id = cur.lastrowid
            
            # Insert Profile
            cur.execute("""
                INSERT INTO student_profiles
                    (user_id, name, education, department, college, current_year,
                     skills, interests, daily_study_hours, career_goal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, name, "Bachelors", persona["dept"], 
                random.choice(COLLEGES), "4th Year",
                persona["skills"], persona["interests"], random.randint(1, 6),
                persona["career"]
            ))
            users_inserted += 1
        except Exception as e:
            print(f"Failed to insert user {name}: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"Successfully seeded {users_inserted} highly diverse users into the database.")

if __name__ == "__main__":
    seed_users(100)
