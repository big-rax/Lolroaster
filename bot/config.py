import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
WORDLE_BOT_ID = 1211781489931452447
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
