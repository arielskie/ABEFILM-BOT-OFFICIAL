# config.py

# --- Telegram Bot Configuration ---
BOT_TOKEN = '8068977426:AAHc9P8o_dd99l2e798D4XDpNsN1KeaDxo8'
ADMIN_ID = 1945159045

# --- Bot Settings ---
DEFAULT_THUMBNAIL = "https://i.postimg.cc/zDKwbb3g/image.png"

DEFAULT_MOVIE_THUMBNAILS = [
    "https://i.postimg.cc/tCGCPFz0/image.png",
    "https://i.postimg.cc/y89dtvYz/Gk-E4Ap6.jpg",
    "https://i.postimg.cc/K8XcPBrG/image.png"
]
DEFAULT_CONCERN_THUMBNAILS = [
    "https://i.postimg.cc/d0fJ0C1t/image.png",
    "https://i.postimg.cc/DycFXHZJ/image.png",
    "https://i.postimg.cc/XqbSZk6c/image.png"
]

# --- Supabase Configuration ---
SUPABASE_URL = "https://pvefdmvjveyoeltewmli.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB2ZWZkbXZqdmV5b2VsdGV3bWxpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTg0NDE0OCwiZXhwIjoyMDcxNDIwMTQ4fQ.gDSaX4MqeaH4_DYxPA-9pHCCPOdqX6grpY9qkE1LPhw" # Not the ANON key

# --- MongoDB Configuration ---
MONGO_URI = "mongodb+srv://abefilm:makeitreal1@abefilmtmdb.azh1fvb.mongodb.net/?retryWrites=true&w=majority&appName=ABEFILMTMDB"
DB_NAME = "telegram_bot_db"
USERS_COLLECTION_NAME = "users"
BROADCASTS_COLLECTION_NAME = "broadcasts"
SETTINGS_COLLECTION_NAME = "settings"
GROUP_CONFIGS_COLLECTION_NAME = "group_configs"



# --- Conversation Handler States ---

# Broadcasting
(
    GET_THUMBNAIL, GET_TITLE, GET_DESCRIPTION,
    GET_BUTTONS, GET_REACTIONS, CHOOSE_TARGET
) = range(6)

# Source Management
(
    GET_SOURCE_NAME, GET_MOVIE_URL, GET_TV_URL
) = range(6, 9)

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
