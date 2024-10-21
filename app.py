import os
import time
import uuid
import json
import logging
import traceback
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, Depends, File, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from supabase import create_client, Client
from database import (
    get_user_by_email,
    insert_chat_message,
    get_chat_history,
    insert_video_analysis,
    get_video_analysis_history,
    create_user,
    get_recent_chat_context,
    update_chat_context
)
from chatbot import Chatbot
from redis_config import get_redis_client, test_redis_connection

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

# Initialize Redis client
redis_client = get_redis_client()
if redis_client:
    logger.info("Redis client initialized successfully")
    logger.info(f"Redis connection info: {redis_client.connection_pool.connection_kwargs}")
    logger.info("Testing Redis connection...")
    test_redis_connection()
else:
    logger.warning("Redis client not initialized")

# Initialize Chatbot
chatbot = Chatbot()

class LoginForm(BaseModel):
    email: str
    password: str

class SignupForm(BaseModel):
    email: str
    password: str

def get_current_user(request: Request):
    session = request.session
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": user_id}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(form_data: SignupForm):
    try:
        response = supabase.auth.sign_up({
            "email": form_data.email,
            "password": form_data.password
        })
        user = response.user
        if user:
            create_user(form_data.email)
            return JSONResponse(content={"success": True, "message": "Signup successful"}, status_code=200)
        else:
            return JSONResponse(content={"success": False, "message": "Signup failed"}, status_code=400)
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
        return JSONResponse(content={"success": False, "message": "An error occurred during signup"}, status_code=500)

@app.post("/login")
async def login(form_data: LoginForm, request: Request):
    try:
        start_time = time.time()
        response = supabase.auth.sign_in_with_password({
            "email": form_data.email,
            "password": form_data.password
        })
        session = response.session
        if session:
            # Store user ID in session
            request.session["user_id"] = str(session.user.id)
            end_time = time.time()
            logger.info(f"Login process time: {end_time - start_time:.2f} seconds")
            return JSONResponse(content={"success": True, "message": "Login successful"}, status_code=200)
        else:
            return JSONResponse(content={"success": False, "message": "Invalid credentials"}, status_code=401)
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content={"success": False, "message": "An error occurred during login"}, status_code=400)

@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"success": True}

@app.get("/auth_status")
async def auth_status(request: Request):
    user_id = request.session.get("user_id")
    return {"authenticated": user_id is not None}

@app.post("/send_message")
async def send_message(request: Request, message: str = Form(...), video: Optional[UploadFile] = File(None)):
    start_time = time.time()
    try:
        current_user = get_current_user(request)
        user_id = current_user["id"]

        if not await check_user_exists(user_id):
            logger.error(f"User with id {user_id} does not exist")
            return JSONResponse(content={"error": "User not found"}, status_code=404)

        if video:
            # Handle video upload and analysis
            file_location = f"temp/{video.filename}"
            with open(file_location, "wb+") as file_object:
                file_object.write(video.file.read())
            
            analysis_result = chatbot.analyze_video(file_location)
            insert_video_analysis(uuid.UUID(user_id), video.filename, analysis_result)
            os.remove(file_location)
            response = analysis_result
        else:
            # Handle text message
            response = chatbot.send_message(message, user_id)

        if response is None:
            logger.error("Chatbot response is None")
            return JSONResponse(content={"error": "Failed to generate response"}, status_code=500)

        # Insert user message and bot response into chat history
        insert_chat_message(uuid.UUID(user_id), message, 'user')
        insert_chat_message(uuid.UUID(user_id), response, 'bot')

        # Update chat context in Redis
        update_chat_context(uuid.UUID(user_id), {"role": "user", "message": message})
        update_chat_context(uuid.UUID(user_id), {"role": "model", "message": response})

        end_time = time.time()
        logger.info(f"Total send_message processing time: {end_time - start_time:.2f} seconds")
        
        return JSONResponse(content={"response": response}, status_code=200)
    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content={"error": "An error occurred while processing your request"}, status_code=500)

async def check_user_exists(user_id: str) -> bool:
    try:
        response = supabase.table("users").select("id").eq("id", user_id).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking user existence: {str(e)}")
        return False

@app.get("/chat_history")
async def chat_history(request: Request):
    start_time = time.time()
    try:
        current_user = get_current_user(request)
        user_id = current_user["id"]
        
        logger.info(f"Fetching chat history for user: {user_id}")
        
        if not isinstance(user_id, uuid.UUID):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                return JSONResponse({"error": "Invalid user ID format"}, status_code=400)
        
        try:
            history = get_chat_history(user_id)
            logger.info(f"Retrieved chat history for user {user_id}")
        except Exception as db_error:
            logger.error(f"Database error while fetching chat history: {str(db_error)}")
            logger.error(traceback.format_exc())
            return JSONResponse({"error": "Error fetching chat history from database"}, status_code=500)
        
        end_time = time.time()
        logger.info(f"Total chat history processing time: {end_time - start_time:.2f} seconds")
        return {"history": history}
    except HTTPException as he:
        logger.error(f"HTTP Exception in chat_history: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in chat_history endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        end_time = time.time()
        logger.error(f"Error occurred after {end_time - start_time:.2f} seconds")
        return JSONResponse({"error": "An unexpected error occurred", "details": str(e)}, status_code=500)

@app.get("/video_analysis_history")
async def video_analysis_history(request: Request):
    start_time = time.time()
    try:
        current_user = get_current_user(request)
        user_id = uuid.UUID(current_user["id"])
        
        history = get_video_analysis_history(user_id)
        logger.info(f"Retrieved video analysis history for user {user_id}")
        
        end_time = time.time()
        logger.info(f"Total video analysis history processing time: {end_time - start_time:.2f} seconds")
        return {"history": history}
    except Exception as e:
        logger.error(f"Error in video_analysis_history endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({"error": "Internal Server Error", "details": str(e)}, status_code=500)

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
