import os
from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2AuthorizationCodeBearer
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from chatbot import Chatbot
from database import create_user, get_user_by_email, insert_chat_message, get_chat_history, insert_video_analysis, get_video_analysis_history, check_user_exists
from dotenv import load_dotenv
import uvicorn
from supabase.client import create_client, Client
import uuid
import json
from redis_config import get_redis_client, test_redis_connection
import redis

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

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_ANON_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

# Initialize Redis client
try:
    redis_client = get_redis_client()
    print("Redis client initialized successfully" if redis_client else "Failed to initialize Redis client")
except (ValueError, redis.exceptions.ConnectionError) as e:
    print(f"Failed to initialize Redis client: {str(e)}")
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
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = response.user
        if user and user.email:
            db_user = get_user_by_email(user.email)
            request.session['user'] = {
                'id': str(db_user['id']),
                'email': user.email,
            }
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
    video: UploadFile = File(None)
):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    if not check_user_exists(user_id):
        raise HTTPException(status_code=400, detail="User does not exist")
    
    if video:
        video_path = os.path.join('temp', video.filename)
        os.makedirs('temp', exist_ok=True)
        with open(video_path, "wb") as buffer:
            content = await video.read()
            buffer.write(content)
        
        analysis_result = chatbot.analyze_video(video_path, message)
        os.remove(video_path)
        
        insert_video_analysis(user_id, video.filename, analysis_result)
        # Invalidate video analysis cache
        if redis_client:
            try:
                redis_client.delete(f"video_analysis_history:{user_id}")
            except redis.exceptions.ConnectionError:
                print("Failed to invalidate video analysis cache due to Redis connection error")
        return {"response": analysis_result}
    else:
        response = chatbot.send_message(message)
        insert_chat_message(user_id, message, 'text')
        insert_chat_message(user_id, response, 'bot')
        # Invalidate chat history cache
        if redis_client:
            try:
                redis_client.delete(f"chat_history:{user_id}")
            except redis.exceptions.ConnectionError:
                print("Failed to invalidate chat history cache due to Redis connection error")
        return {"response": response}

@app.get("/chat_history")
async def chat_history(request: Request):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    if redis_client:
        try:
            # Try to get chat history from Redis cache
            cached_history = redis_client.get(f"chat_history:{user_id}")
            if cached_history:
                try:
                    history = json.loads(cached_history)
                    print(f"Retrieved chat history for user {user_id} from Redis cache")
                    return {"history": history}
                except json.JSONDecodeError:
                    print(f"Error decoding cached chat history for user {user_id}")
        except redis.exceptions.ConnectionError:
            print("Failed to get chat history from Redis cache due to connection error")
        except redis.exceptions.ResponseError as e:
            print(f"Redis error: {str(e)}. Falling back to database.")
    
    # If not in cache, Redis is unavailable, or there was an error, fetch from database
    history = get_chat_history(user_id)
    print(f"Retrieved chat history for user {user_id} from database")
    
    if redis_client:
        try:
            # Cache the result if Redis is available
            redis_client.setex(f"chat_history:{user_id}", 300, json.dumps(history))  # Cache for 5 minutes
        except (redis.exceptions.ConnectionError, redis.exceptions.ResponseError) as e:
            print(f"Failed to cache chat history: {str(e)}")
    
    return {"history": history}

@app.get("/video_analysis_history")
async def video_analysis_history(request: Request):
    current_user = get_current_user(request)
    user_id = uuid.UUID(current_user['id'])
    
    if redis_client:
        try:
            # Try to get video analysis history from Redis cache
            cached_history = redis_client.get(f"video_analysis_history:{user_id}")
            if cached_history:
                try:
                    history = json.loads(cached_history)
                    print(f"Retrieved video analysis history for user {user_id} from Redis cache")
                    return {"history": history}
                except json.JSONDecodeError:
                    print(f"Error decoding cached video analysis history for user {user_id}")
        except redis.exceptions.ConnectionError:
            print("Failed to get video analysis history from Redis cache due to connection error")
        except redis.exceptions.ResponseError as e:
            print(f"Redis error: {str(e)}. Falling back to database.")
    
    # If not in cache, Redis is unavailable, or there was an error, fetch from database
    history = get_video_analysis_history(user_id)
    print(f"Retrieved video analysis history for user {user_id} from database")
    
    if redis_client:
        try:
            # Cache the result if Redis is available
            redis_client.setex(f"video_analysis_history:{user_id}", 300, json.dumps(history))  # Cache for 5 minutes
        except (redis.exceptions.ConnectionError, redis.exceptions.ResponseError) as e:
            print(f"Failed to cache video analysis history: {str(e)}")
    
    return {"history": history}

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
