# config.py

# --- Telegram Bot Configuration ---
BOT_TOKEN = '8068977426:AAHc9P8o_dd99l2e798D4XDpNsN1KeaDxo8'
ADMIN_ID = 1945159045

# --- Bot Settings ---
DEFAULT_THUMBNAIL = "https://i.postimg.cc/zDKwbb3g/image.png"

# Default Thumbnails for Request System
DEFAULT_CONCERN_THUMBNAILS = [
    "https://i.postimg.cc/d0fJ0C1t/image.png",
    "https://i.postimg.cc/DycFXHZJ/image.png",
    "https://i.postimg.cc/XqbSZk6c/image.png"
]
# Kept for compatibility if request.py still references it, though unused for movies now
DEFAULT_MOVIE_THUMBNAILS = DEFAULT_CONCERN_THUMBNAILS 

# --- MongoDB Configuration ---
MONGO_URI = "mongodb+srv://abefilm:makeitreal1@abefilmtmdb.azh1fvb.mongodb.net/?retryWrites=true&w=majority&appName=ABEFILMTMDB"
DB_NAME = "telegram_bot_db"
USERS_COLLECTION_NAME = "users"
BROADCASTS_COLLECTION_NAME = "broadcasts"
SETTINGS_COLLECTION_NAME = "settings"
GROUP_CONFIGS_COLLECTION_NAME = "group_configs"

# --- SUPABASE PROJECT 1 (License System) ---
SUPABASE_URL = "https://pvefdmvjveyoeltewmli.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB2ZWZkbXZqdmV5b2VsdGV3bWxpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTg0NDE0OCwiZXhwIjoyMDcxNDIwMTQ4fQ.gDSaX4MqeaH4_DYxPA-9pHCCPOdqX6grpY9qkE1LPhw"

# --- SUPABASE PROJECT 2 (Rating System / allowed_sites) ---
SUPABASE_RATING_URL = "https://agfwyfwsnqnklgcgemnw.supabase.co"
SUPABASE_RATING_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFnZnd5ZndzbnFua2xnY2dlbW53Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NzIxNDcxNCwiZXhwIjoyMDcyNzkwNzE0fQ.m6cE-ZulAaf8hRMchOQLkNDNSGcr1DMMcEGBP0OObOU"

# --- Conversation Handler States ---

# Broadcasting
(
    GET_THUMBNAIL, GET_TITLE, GET_DESCRIPTION,
    GET_BUTTONS, GET_REACTIONS, CHOOSE_TARGET
) = range(6)

# Request Workflow
(
    REQ_GET_CONCERN_SUBJECT,
    REQ_GET_CONCERN_IMAGE,
    REQ_GET_CONCERN_DETAIL,
    AWAITING_REMARK
) = range(10, 14)

# Group Management
(
    CHOOSE_GROUP_TYPE, ADD_BROADCAST_GROUP_ID,
    AWAITING_SOURCE_GROUP_FORWARD, AWAITING_DEST_GROUP_FORWARD
) = range(14, 18)

# Other Admin Actions
DELETING_GROUP = 18
AWAITING_DEST_GROUP_FOR_CONFIG = 19
AWAITING_DEST_TOPIC_ID = 20

# Theme Management
(
    THEME_GET_NAME,
    THEME_GET_IMAGE,
    THEME_GET_DESC,
    THEME_GET_DEMO,
    THEME_GET_DOCS,
    THEME_GET_BUY
) = range(21, 27)

THEME_DELETE_CHOICE = 27

# License Management
(
    LIC_GET_THEME, LIC_GET_DURATION
) = range(28, 30)
