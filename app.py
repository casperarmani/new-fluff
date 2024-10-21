import os
from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2AuthorizationCodeBearer
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from chatbot import Chatbot
from database import create_user, get_user_by_email, async_insert_chat_message, get_chat_history, insert_video_analysis, get_video_analysis_history, check_user_exists, write_messages_to_db
from dotenv import load_dotenv
import uvicorn
from supabase.client import create_client, Client
import uuid
import json
from redis_config import get_redis_client, test_redis_connection, CHAT_SESSION_TTL
import redis
import logging
import traceback
import time
import asyncio
from fastapi_utils.tasks import repeat_every

load_dotenv()

app = FastAPI()
chatbot = Chatbot()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_ANON_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

redis_client = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    try:
        redis_client = get_redis_client()
        if redis_client:
            logger.info("Redis client initialized successfully")
            if test_redis_connection():
                logger.info("Redis connection test passed")
            else:
                logger.warning("Redis connection test failed")
        else:
            logger.warning("Failed to initialize Redis client")
    except Exception as e:
        logger.error(f"Error during Redis initialization: {str(e)}")

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
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = response.user
        if user and user.email:
            db_user = get_user_by_email(user.email)
            request.session['user'] = {
                'id': str(db_user['id']),
                'email': user.email,
            }
            
            # Load chat history and video analysis history into Redis
            user_id = uuid.UUID(db_user['id'])
            chat_history = get_chat_history(user_id)
            video_history = get_video_analysis_history(user_id)
            
            if redis_client:
                try:
                    redis_client.setex(f"chat_history:{user_id}", CHAT_SESSION_TTL, json.dumps(chat_history))
                    redis_client.setex(f"video_analysis_history:{user_id}", CHAT_SESSION_TTL, json.dumps(video_history))
                except redis.exceptions.ConnectionError:
                    logger.error("Failed to cache user history due to Redis connection error")
            
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
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)

@app.get('/signup', response_class=HTMLResponse)
async def signup_page(request: Request):
    with open("templates/signup.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post('/signup')
async def signup_post(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        user = response.user
        if user and user.email:
            db_user = create_user(user.email)
            request.session['user'] = {
                'id': str(db_user['id']),
                'email': user.email,
            }
            return JSONResponse({"success": True, "message": "Signup successful"})
        else:
            return JSONResponse({"success": False, "message": "Signup failed"}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)

@app.post('/logout')
async def logout(request: Request):
    request.session.pop('user', None)
    return JSONResponse({"success": True, "message": "Logout successful"})

@app.get("/auth_status")
async def auth_status(request: Request):
    user = request.session.get('user')
    return {"authenticated": user is not None}

@app.post("/send_message")
async def send_message(
    request: Request,
    message: str = Form(""),
    video: UploadFile = File(None),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    if not check_user_exists(user_id):
        raise HTTPException(status_code=400, detail="User does not exist")
    
    cache_key = f"chat_history:{user_id}"
    
    if video:
        video_path = os.path.join('temp', video.filename)
        os.makedirs('temp', exist_ok=True)
        with open(video_path, "wb") as buffer:
            content = await video.read()
            buffer.write(content)
        
        analysis_result = chatbot.analyze_video(video_path, message)
        os.remove(video_path)
        
        insert_video_analysis(user_id, video.filename, analysis_result)
        if redis_client:
            try:
                redis_client.delete(f"video_analysis_history:{user_id}")
            except redis.exceptions.ConnectionError:
                logger.error("Failed to invalidate video analysis cache due to Redis connection error")
        return {"response": analysis_result}
    else:
        # Check Redis for an active chat session
        cached_history = redis_client.get(cache_key)
        if cached_history:
            history = json.loads(cached_history)
        else:
            history = get_chat_history(user_id)
        
        # Add the new message to the history
        user_message = await async_insert_chat_message(user_id, message, 'text')
        history.insert(0, user_message)
        
        # Process the message with the chatbot
        response = chatbot.send_message(message)
        
        # Add the bot's response to the history
        bot_message = await async_insert_chat_message(user_id, response, 'bot')
        history.insert(0, bot_message)
        
        # Update Redis cache
        redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history[:50]))
        
        # Schedule background task to write cached data to Supabase
        background_tasks.add_task(write_cache_to_database, user_id)
        
        return {"response": response}

@app.get("/chat_history")
async def chat_history(request: Request):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    cache_key = f"chat_history:{user_id}"
    
    # Try to get from Redis cache first
    try:
        cached_history = redis_client.get(cache_key)
        if cached_history:
            history = json.loads(cached_history)
            logger.info(f"Retrieved chat history for user {user_id} from Redis cache")
            return {"history": history}
    except Exception as e:
        logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    history = get_chat_history(user_id)
    
    # Update Redis cache
    try:
        redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history))
    except Exception as e:
        logger.error(f"Error updating Redis cache: {str(e)}")
    
    return {"history": history}

@app.get("/video_analysis_history")
async def video_analysis_history(request: Request):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    cache_key = f"video_analysis_history:{user_id}"
    
    # Try to get from Redis cache first
    try:
        cached_history = redis_client.get(cache_key)
        if cached_history:
            history = json.loads(cached_history)
            logger.info(f"Retrieved video analysis history for user {user_id} from Redis cache")
            return {"history": history}
    except Exception as e:
        logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    history = get_video_analysis_history(user_id)
    
    # Update Redis cache
    try:
        redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history))
    except Exception as e:
        logger.error(f"Error updating Redis cache: {str(e)}")
    
    return {"history": history}

async def write_cache_to_database(user_id: uuid.UUID):
    cache_key = f"chat_history:{user_id}"
    try:
        cached_history = redis_client.get(cache_key)
        if cached_history:
            history = json.loads(cached_history)
            await write_messages_to_db(user_id, history)
    except Exception as e:
        logger.error(f"Error writing cache to database: {str(e)}")

@app.on_event("startup")
@repeat_every(seconds=300)  # Run every 5 minutes
async def periodic_cache_write():
    try:
        for key in redis_client.keys("chat_history:*"):
            user_id = uuid.UUID(key.decode().split(":")[1])
            await write_cache_to_database(user_id)
    except Exception as e:
        logger.error(f"Error in periodic cache write: {str(e)}")

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
