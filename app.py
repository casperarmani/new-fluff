import os
import logging
import time
from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from chatbot import Chatbot
from dotenv import load_dotenv
import uvicorn
from supabase import create_client, Client
from datetime import datetime
import json
from gotrue.errors import AuthApiError
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
chatbot = Chatbot()

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

def initialize_supabase_client(max_retries=3, retry_delay=5):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_anon_key:
        raise ValueError("SUPABASE_URL or SUPABASE_ANON_KEY is missing")
    
    for attempt in range(max_retries):
        try:
            supabase: Client = create_client(supabase_url, supabase_anon_key)
            logger.info("Supabase client initialized successfully")
            return supabase
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed to initialize Supabase client: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Failed to initialize Supabase client.")
                return None

supabase = initialize_supabase_client()

def create_tables():
    if not supabase:
        logger.error("Supabase client not initialized. Cannot create tables.")
        return

    try:
        # Create chat_history table
        supabase.table("chat_history").create({
            "id": {"type": "uuid", "primary": True},
            "user_id": {"type": "uuid", "references": "auth.users.id"},
            "chat_content": {"type": "text"},
            "timestamp": {"type": "timestamptz", "default": "now()"}
        })
        logger.info("chat_history table created successfully")

        # Create video_analysis table
        supabase.table("video_analysis").create({
            "id": {"type": "uuid", "primary": True},
            "user_id": {"type": "uuid", "references": "auth.users.id"},
            "video_filename": {"type": "text"},
            "analysis_result": {"type": "text"},
            "timestamp": {"type": "timestamptz", "default": "now()"}
        })
        logger.info("video_analysis table created successfully")
    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")

# Call create_tables function when the app starts
create_tables()

def get_current_user(request: Request):
    session = request.session
    if "user" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session["user"]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with open("templates/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    with open("templates/login.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    with open("templates/signup.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/auth_status")
async def auth_status(request: Request):
    session = request.session
    return JSONResponse({"authenticated": "user" in session})

@app.post("/send_message")
async def send_message(
    request: Request,
    message: str = Form(""),
    video: UploadFile = File(None),
    user: dict = Depends(get_current_user)
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not initialized")

    user_id = user["id"]

    if video:
        # Save the uploaded file temporarily
        video_path = os.path.join('temp', video.filename)
        os.makedirs('temp', exist_ok=True)
        with open(video_path, "wb") as buffer:
            buffer.write(await video.read())
        
        # Analyze the video
        analysis_result = chatbot.analyze_video(video_path, message)
        
        # Store video analysis result in Supabase
        supabase.table("video_analysis").insert({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "video_filename": video.filename,
            "analysis_result": analysis_result
        }).execute()
        
        # Remove the temporary file
        os.remove(video_path)
        
        response = analysis_result
    else:
        # Handle text-only message
        response = chatbot.send_message(message)

    # Store chat message in Supabase
    supabase.table("chat_history").insert({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "chat_content": json.dumps({"user": message, "bot": response})
    }).execute()

    return {"response": response}

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not initialized")
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user_dict = response.user.dict()
        # Convert datetime objects to ISO format strings
        user_dict = json.loads(json.dumps(user_dict, cls=DateTimeEncoder))
        request.session["user"] = user_dict
        return JSONResponse({"success": True, "message": "Login successful"})
    except AuthApiError as e:
        logger.error(f"Login error: {str(e)}")
        error_message = "Incorrect email or password. Please try again or reset your password if you've forgotten it."
        return JSONResponse({"success": False, "message": error_message}, status_code=400)
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return JSONResponse({"success": False, "message": "An unexpected error occurred during login"}, status_code=500)

@app.post("/signup")
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not initialized")
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        user_dict = response.user.dict()
        # Convert datetime objects to ISO format strings
        user_dict = json.loads(json.dumps(user_dict, cls=DateTimeEncoder))
        request.session["user"] = user_dict
        return JSONResponse({"success": True, "message": "Signup successful"})
    except AuthApiError as e:
        logger.error(f"Signup error: {str(e)}")
        error_message = "An account with this email address already exists. Please use a different email or try logging in."
        return JSONResponse({"success": False, "message": error_message}, status_code=400)
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return JSONResponse({"success": False, "message": "An unexpected error occurred during signup"}, status_code=500)

@app.post("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return JSONResponse({"success": True, "message": "Logout successful"})

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
