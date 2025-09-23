# config.py

# --- Telegram Bot Configuration ---
BOT_TOKEN = '8068977426:AAHc9P8o_dd99l2e798D4XDpNsN1KeaDxo8'

# --- TMDB API Configuration ---
TMDB_API_KEY = '8b23434c25286f8846655c6c6bfc7bf2'

# --- Bot Settings ---
DEFAULT_THUMBNAIL = "https://i.imgur.com/q8veKmY.png"

# --- Default Thumbnails for Request System ---
DEFAULT_MOVIE_THUMBNAILS = [
    "https://i.imgur.com/dX4FpNj.jpeg",
    "https://i.imgur.com/GpGcQqU.jpeg",
    "https://i.imgur.com/GkE4Ap6.jpeg"
]
DEFAULT_CONCERN_THUMBNAILS = [
    "https://i.imgur.com/FgryI9n.jpeg",
    "https://i.imgur.com/c6lLmB5.jpeg",
    "https://i.imgur.com/9ocFVJS.jpeg"
]

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
DELETING_SOURCE = 9
TOGGLE_SOURCE = 10

# --- Request Workflow States (CORRECTED SECTION) ---
(
    REQ_CHOOSE_TYPE,
    # Movie/TV Flow
    REQ_GET_POSTER,
    REQ_GET_TITLE,
    REQ_GET_MEDIA_TYPE,
    REQ_GET_YEAR,
    REQ_GET_COUNTRY,
    REQ_GET_NOTE,
    # Concern Flow (Renamed and reordered for logical flow)
    REQ_GET_CONCERN_SUBJECT,
    REQ_GET_CONCERN_IMAGE,      # <-- RENAMED from _SCREENSHOT and MOVED
    REQ_GET_CONCERN_DETAIL,
    # Admin Flow
    AWAITING_REMARK
) = range(11, 22)

# UNIFIED /addgroup States
(
    CHOOSE_GROUP_TYPE,
    ADD_BROADCAST_GROUP_ID,
    AWAITING_SOURCE_GROUP_FORWARD,
    AWAITING_DEST_GROUP_FORWARD
) = range(22, 26)

# States for /deletegroup
DELETING_GROUP = 26

# NEW: Simplified state for Generate Post Code (only for TV shows)
AWAITING_SEASON_CHOICE = 27
