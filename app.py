import os
import uuid
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Query, Request, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
import uvicorn
from chatbot import Chatbot
from database import (
    create_user, get_user_by_email, async_insert_chat_message,
    get_chat_history, insert_video_analysis, get_video_analysis_history
)
from redis_config import cache_get, cache_set, write_through_cache, CHAT_SESSION_TTL

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Set up session middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY"))

# Initialize chatbot
chatbot = Chatbot()

# User authentication
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.on_event("startup")
async def startup_event():
    # Initialize Redis connection
    from redis_config import test_redis_connection
    if test_redis_connection():
        logger.info("Redis client initialized successfully")
        logger.info("Redis connection test passed")
    else:
        logger.error("Failed to initialize Redis client or connection test failed")

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
async def signup(request: Request):
    form_data = await request.form()
    email = form_data.get("email")
    password = form_data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    try:
        user = await create_user(email)
        request.session["user"] = user
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
        raise HTTPException(status_code=500, detail="Error during signup")

@app.post("/login")
async def login(request: Request):
    form_data = await request.form()
    email = form_data.get("email")
    password = form_data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    try:
        user = await get_user_by_email(email)
        if user:
            request.session["user"] = user
            return JSONResponse(content={"success": True})
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(status_code=500, detail="Error during login")

@app.post("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return JSONResponse(content={"success": True})

@app.get("/auth_status")
async def auth_status(request: Request):
    user = request.session.get("user")
    return JSONResponse(content={"authenticated": bool(user)})

@app.post("/send_message")
async def send_message(request: Request):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    form_data = await request.form()
    message = form_data.get("message")
    video_file = form_data.get("video")

    try:
        if video_file:
            # Handle video analysis
            contents = await video_file.read()
            filename = video_file.filename
            response = chatbot.analyze_video(contents, filename)
            await insert_video_analysis(user_id, filename, response)
        else:
            # Handle text message
            response = chatbot.send_message(message)
            
        # Use write-through cache for chat messages
        cache_key = f"chat_history:{user_id}"
        new_message = {
            "user_id": str(user_id),
            "message": message,
            "chat_type": "user",
            "TIMESTAMP": "CURRENT_TIMESTAMP"
        }
        await write_through_cache(cache_key, new_message, lambda x: async_insert_chat_message(user_id, x['message'], x['chat_type']))
        
        new_response = {
            "user_id": str(user_id),
            "message": response,
            "chat_type": "bot",
            "TIMESTAMP": "CURRENT_TIMESTAMP"
        }
        await write_through_cache(cache_key, new_response, lambda x: async_insert_chat_message(user_id, x['message'], x['chat_type']))

        return JSONResponse(content={"response": response})
    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/chat_history")
async def chat_history(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None)
):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    try:
        cache_key = f"chat_history:{user_id}"
        cached_history = await cache_get(cache_key)
        
        if cached_history:
            logger.info(f"Retrieved chat history for user {user_id} from Redis cache")
            start_index = 0 if cursor is None else int(cursor)
            end_index = start_index + limit
            history = cached_history[start_index:end_index]
            next_cursor = str(end_index) if end_index < len(cached_history) else None
            return {
                "history": history,
                "next_cursor": next_cursor
            }
        
        history, next_cursor = await get_chat_history(user_id, limit, cursor)
        
        # Update Redis cache
        await cache_set(cache_key, history, CHAT_SESSION_TTL)
        
        return {
            "history": history,
            "next_cursor": next_cursor
        }
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/video_analysis_history")
async def video_analysis_history(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    cursor: Optional[str] = Query(None)
):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    try:
        cache_key = f"video_analysis_history:{user_id}"
        cached_history = await cache_get(cache_key)
        
        if cached_history:
            logger.info(f"Retrieved video analysis history for user {user_id} from Redis cache")
            start_index = 0 if cursor is None else int(cursor)
            end_index = start_index + limit
            history = cached_history[start_index:end_index]
            next_cursor = str(end_index) if end_index < len(cached_history) else None
            return {
                "history": history,
                "next_cursor": next_cursor
            }
        
        history, next_cursor = await get_video_analysis_history(user_id, limit, cursor)
        
        # Update Redis cache
        await cache_set(cache_key, history, CHAT_SESSION_TTL)
        
        return {
            "history": history,
            "next_cursor": next_cursor
        }
    except Exception as e:
        logger.error(f"Error fetching video analysis history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
