import os
import time
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get the API key
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("No GEMINI_API_KEY found in environment variables. Please set it in your .env file.")

# Configure the generative AI
genai.configure(api_key=api_key)

class Chatbot:
    def __init__(self):
        self.generation_config = {
            "temperature": 0.9,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
        }
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-latest",
            generation_config=self.generation_config,
        )
        self.chat_session = self.model.start_chat(
            history=[
                {
                    "role": "user",
                    "parts": ["You are a world-class video ads and creative analyzer. You can analyze both text and video content."],
                },
                {
                    "role": "model",
                    "parts": ["Understood. As a world-class video ads and creative analyzer, I'm ready to provide expert insights on both text and video content. My analysis will cover various aspects such as audience engagement, messaging effectiveness, visual and audio elements, brand consistency, and platform optimization. Whether you have a specific question about an ad or need a comprehensive analysis of a video, I'm here to help. What would you like me to analyze today?"],
                },
            ]
        )

    def send_message(self, message):
        try:
            response = self.chat_session.send_message(message)
            return response.text
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return "I apologize, but there was an error processing your request. Please try again."

    def analyze_video(self, video_path, prompt=''):
        try:
            logger.info(f"Uploading video file: {video_path}")
            video_file = genai.upload_file(video_path)
            
            logger.info("Waiting for video processing...")
            while video_file.state.name == "PROCESSING":
                time.sleep(5)
                video_file = genai.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                raise ValueError(f"Video processing failed: {video_file.state.name}")

            logger.info("Video processing complete. Generating analysis...")
            default_prompt = "Analyze this video advertisement. Provide insights on its effectiveness, target audience, key messages, and areas for improvement. Include a comprehensive analysis of audience engagement, messaging & storytelling, visual & audio elements, brand consistency, and platform optimization."
            
            full_prompt = f"{default_prompt}\n\nAdditional instructions: {prompt}" if prompt else default_prompt
            
            response = self.model.generate_content([video_file, full_prompt], request_options={"timeout": 300})
            return response.text
        except Exception as e:
            logger.error(f"Error analyzing video: {str(e)}")
            return f"An error occurred during video analysis: {str(e)}"
