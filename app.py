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

def create_tables_and_policies():
    if not supabase:
        raise ValueError("Supabase client not initialized")

    sql_commands = """
    -- Create chat_history table
    CREATE TABLE IF NOT EXISTS chat_history (
        id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
        user_id UUID NOT NULL,
        message TEXT NOT NULL,
        is_bot BOOLEAN NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (user_id) REFERENCES auth.users(id)
    );

    -- Create video_analysis_history table
    CREATE TABLE IF NOT EXISTS video_analysis_history (
        id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
        user_id UUID NOT NULL,
        video_filename TEXT NOT NULL,
        analysis_output TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (user_id) REFERENCES auth.users(id)
    );

    -- Enable Row Level Security (RLS) for both tables
    ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;
    ALTER TABLE video_analysis_history ENABLE ROW LEVEL SECURITY;

    -- Create policies for chat_history
    CREATE POLICY IF NOT EXISTS "Users can insert their own chat messages" 
    ON chat_history FOR INSERT WITH CHECK (auth.uid() = user_id);
    
    CREATE POLICY IF NOT EXISTS "Users can read their own chat messages" 
    ON chat_history FOR SELECT USING (auth.uid() = user_id);

    -- Create policies for video_analysis_history
    CREATE POLICY IF NOT EXISTS "Users can insert their own video analysis" 
    ON video_analysis_history FOR INSERT WITH CHECK (auth.uid() = user_id);
    
    CREATE POLICY IF NOT EXISTS "Users can read their own video analysis" 
    ON video_analysis_history FOR SELECT USING (auth.uid() = user_id);
    """

    try:
        supabase.query(sql_commands).execute()
        logger.info("Tables and policies created successfully")
    except Exception as e:
        logger.error(f"Error creating tables and policies: {str(e)}")
        raise

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

@app.get("/chat_history")
async def get_chat_history(user: dict = Depends(get_current_user)):
    try:
        response = supabase.table('chat_history').select('*').eq('user_id', user['id']).order('created_at').execute()
        return JSONResponse(response.data)
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching chat history")

@app.get("/video_analysis_history")
async def get_video_analysis_history(user: dict = Depends(get_current_user)):
    try:
        response = supabase.table('video_analysis_history').select('*').eq('user_id', user['id']).order('created_at', desc=True).execute()
        return JSONResponse(response.data)
    except Exception as e:
        logger.error(f"Error fetching video analysis history: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching video analysis history")

@app.post("/send_message")
async def send_message(
    request: Request,
    message: str = Form(""),
    video: UploadFile = File(None),
    user: dict = Depends(get_current_user)
):
    if video:
        # Save the uploaded file temporarily
        video_path = os.path.join('temp', video.filename)
        os.makedirs('temp', exist_ok=True)
        with open(video_path, "wb") as buffer:
            buffer.write(await video.read())
        
        # Analyze the video
        analysis_result = chatbot.analyze_video(video_path, message)
        
        # Store video analysis in the database
        try:
            supabase.table('video_analysis_history').insert({
                'user_id': user['id'],
                'video_filename': video.filename,
                'analysis_output': analysis_result
            }).execute()
        except Exception as e:
            logger.error(f"Error storing video analysis: {str(e)}")
        
        # Remove the temporary file
        os.remove(video_path)
        
        return {"response": analysis_result}
    else:
        # Handle text-only message
        response = chatbot.send_message(message)
        
        # Store chat message in the database
        try:
            supabase.table('chat_history').insert({
                'user_id': user['id'],
                'message': message,
                'is_bot': False
            }).execute()
            supabase.table('chat_history').insert({
                'user_id': user['id'],
                'message': response,
                'is_bot': True
            }).execute()
        except Exception as e:
            logger.error(f"Error storing chat message: {str(e)}")
        
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

@app.on_event("startup")
async def startup_event():
    try:
        create_tables_and_policies()
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
