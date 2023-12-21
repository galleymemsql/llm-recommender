import os
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION_URL = os.environ.get('DB_CONNECTION_URL')
DB_NAME = os.environ.get('DB_NAME')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
HF_TOKEN = os.getenv('HF_TOKEN')
