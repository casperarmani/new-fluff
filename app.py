import os
import time
from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2AuthorizationCodeBearer
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from chatbot import Chatbot
from database import create_user, get_user_by_email, insert_chat_message, get_chat_history as db_get_chat_history, insert_video_analysis, get_video_analysis_history, check_user_exists
from dotenv import load_dotenv
import uvicorn
from supabase.client import create_client, Client
import uuid
import json
from redis_config import get_redis_client, test_redis_connection, get_session_history, update_chat_history, clear_chat_history, cache_user, get_cached_user, cache_video_analysis, get_cached_video_analysis
import redis
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
chatbot = Chatbot()

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_ANON_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

try:
    redis_client = get_redis_client()
    logger.info("Redis client initialized successfully" if redis_client else "Failed to initialize Redis client")
except (ValueError, redis.exceptions.ConnectionError) as e:
    logger.error(f"Failed to initialize Redis client: {str(e)}")
    redis_client = None

@app.on_event("startup")
async def startup_event():
    test_redis_connection()

def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get('user')
    with open("templates/index.html", "r") as f:
        html_content = f.read()
    if user:
        html_content = html_content.replace("<!-- USER_INFO -->", f"<p>Welcome, {user['email']}! <a href='/logout'>Logout</a></p>")
    else:
        html_content = html_content.replace("<!-- USER_INFO -->", "<p><a href='/login'>Login</a> | <a href='/signup'>Sign Up</a></p>")
    return HTMLResponse(content=html_content)

@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    with open("templates/login.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post('/login')
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        start_time = time.time()
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = response.user
        if user and user.email:
            cached_user = get_cached_user(user.email)
            if cached_user:
                db_user = cached_user
                logger.info(f"User {user.email} retrieved from cache")
            else:
                db_user = get_user_by_email(user.email)
                cache_user(user.email, db_user)
                logger.info(f"User {user.email} cached")
            
            request.session['user'] = {
                'id': str(db_user['id']),
                'email': user.email,
            }
            end_time = time.time()
            logger.info(f"Login process time: {end_time - start_time:.2f} seconds")
            return JSONResponse({
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": str(db_user['id']),
                    "email": user.email
                }
            })
        else:
            raise ValueError("Invalid user data received from Supabase")
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)

@app.get('/signup', response_class=HTMLResponse)
async def signup_page(request: Request):
    with open("templates/signup.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post('/signup')
async def signup_post(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        start_time = time.time()
        response = supabase.auth.sign_up({"email": email, "password": password})
        user = response.user
        if user and user.email:
            db_user = create_user(user.email)
            cache_user(user.email, db_user)
            request.session['user'] = {
                'id': str(db_user['id']),
                'email': user.email,
            }
            end_time = time.time()
            logger.info(f"Signup process time: {end_time - start_time:.2f} seconds")
            return JSONResponse({"success": True, "message": "Signup successful"})
        else:
            return JSONResponse({"success": False, "message": "Signup failed"}, status_code=400)
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)

@app.post('/logout')
async def logout(request: Request):
    user_id = request.session.get('user', {}).get('id')
    request.session.pop('user', None)
    if user_id:
        clear_chat_history(user_id)
    return JSONResponse({"success": True, "message": "Logout successful"})

@app.get("/auth_status")
async def auth_status(request: Request):
    user = request.session.get('user')
    return {"authenticated": user is not None}

@app.post("/send_message")
async def send_message(
    request: Request,
    message: str = Form(""),
    video: UploadFile = File(None)
):
    start_time = time.time()
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    if not check_user_exists(user_id):
        raise HTTPException(status_code=400, detail="User does not exist")
    
    session_history = get_session_history(str(user_id))
    
    if video:
        video_path = os.path.join('temp', video.filename)
        os.makedirs('temp', exist_ok=True)
        with open(video_path, "wb") as buffer:
            content = await video.read()
            buffer.write(content)
        
        analysis_result = chatbot.analyze_video(video_path, message)
        os.remove(video_path)
        
        insert_video_analysis(user_id, video.filename, analysis_result)
        cache_video_analysis(str(user_id), [{"filename": video.filename, "analysis": analysis_result}])
        response = analysis_result
    else:
        response = chatbot.send_message(message, session_history)
        insert_chat_message(user_id, message, 'text')
        insert_chat_message(user_id, response, 'bot')
        update_chat_history(str(user_id), {'message': message, 'type': 'text'})
        update_chat_history(str(user_id), {'message': response, 'type': 'bot'})
    
    end_time = time.time()
    logger.info(f"Total send_message processing time: {end_time - start_time:.2f} seconds")
    return {"response": response}

@app.get("/chat_history")
async def chat_history(request: Request):
    start_time = time.time()
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    history = get_session_history(str(user_id))
    if not history:
        history = db_get_chat_history(user_id)
        for item in reversed(history):
            update_chat_history(str(user_id), item)
    logger.info(f"Retrieved chat history for user {user_id}")
    
    end_time = time.time()
    logger.info(f"Total chat history processing time: {end_time - start_time:.2f} seconds")
    return {"history": history}

@app.get("/video_analysis_history")
async def video_analysis_history(request: Request):
    start_time = time.time()
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    cached_history = get_cached_video_analysis(str(user_id))
    if cached_history:
        history = cached_history
        logger.info(f"Retrieved video analysis history for user {user_id} from cache")
    else:
        history = get_video_analysis_history(user_id)
        cache_video_analysis(str(user_id), history)
        logger.info(f"Retrieved video analysis history for user {user_id} from database and cached it")
    
    end_time = time.time()
    logger.info(f"Total video analysis history processing time: {end_time - start_time:.2f} seconds")
    return {"history": history}

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
