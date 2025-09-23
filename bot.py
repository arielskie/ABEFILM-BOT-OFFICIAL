import pymongo
import io
import logging
import json
from bson.objectid import ObjectId
from datetime import datetime
from functools import partial
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    InlineQueryHandler,
    PicklePersistence,
)
from telegram.error import BadRequest
from telegram.constants import ChatType

import config
import search
import request
import broadcast # <-- ADDED IMPORT

# --- Setup Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
PRIVATE_CHAT_ONLY_MESSAGE = "This command can only be used in a private chat with me."
# States for the new unified server conversation
VIEWING_SERVERS, DELETING_SERVER_CHOICE = range(100, 102)


# --- MongoDB Client Initialization ---
try:
    mongo_client = pymongo.MongoClient(config.MONGO_URI)
    db = mongo_client[config.DB_NAME]
    user_collection = db[config.USERS_COLLECTION_NAME]
    broadcasts_collection = db[config.BROADCASTS_COLLECTION_NAME]
    settings_collection = db[config.SETTINGS_COLLECTION_NAME]
    group_configs_collection = db[config.GROUP_CONFIGS_COLLECTION_NAME]
    print("✅ MongoDB Connection Successful.")
except Exception as e:
    print(f"❌ FATAL: Could not connect to MongoDB: {e}")
    exit()

# --- Default Video Sources ---
DEFAULT_SOURCES = [
    {"name": "Vidsrc.to", "movie_url": "https://vidsrc.to/embed/movie/{tmdb_id}", "tv_url": "https://vidsrc.to/embed/tv/{tmdb_id}/{season}/{episode}"},
    {"name": "Vidsrc.co", "movie_url": "https://player.vidsrc.co/embed/movie/{tmdb_id}", "tv_url": "https://player.vidsrc.co/embed/tv/{tmdb_id}/{season}/{episode}"},
    {"name": "Vidsrc.vip", "movie_url": "https://vidsrc.vip/embed/movie/{tmdb_id}", "tv_url": "https://vidsrc.vip/embed/tv/{tmdb_id}/{season}/{episode}"},
    {"name": "Vidlink.pro", "movie_url": "https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}", "tv_url": "https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}"},
    {"name": "Autoembed.pro", "movie_url": "https://autoembed.pro/embed/movie/{tmdb_id}", "tv_url": "https://autoembed.pro/embed/tv/{tmdb_id}/{season}/{episode}"},
    {"name": "Vidapi.xyz", "movie_url": "https://vidapi.xyz/embed/movie/{tmdb_id}", "tv_url": "https://vidapi.xyz/embed/tv/{tmdb_id}&s={season}&e={episode}"},
    {"name": "Vidpop.xyz", "movie_url": "https://www.vidpop.xyz/embed/?id={tmdb_id}", "tv_url": "https://www.vidpop.xyz/embed/?id={tmdb_id}&season={season}&episode={episode}"}
]

# --- HELPER: Checks if a user is an admin in a chat ---
async def is_user_chat_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return user_id in [admin.user.id for admin in admins]
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("request_"):
        try:
            source_group_id = int(context.args[0].split('_')[1])
            context.user_data['source_group_id'] = source_group_id
            return await request.start_request_conversation(update, context)
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid request link.")
            return ConversationHandler.END
    
    start_caption = """👋 <b>Welcome to the ABEFILM BOT OFFICIAL!</b>

1️⃣ <b>Group Features</b>
● /search &lt;title&gt;: Find movie/TV info.
● /request: Start a movie request (in configured groups).
● Or use inline: @abefilmofficialbot &lt;title&gt;

2️⃣ <b>Broadcast Features (Private)</b>
● /broadcast: Create and send a post to a channel.
● /addgroup: Register a group for broadcasting or requests.
● /mygroups: View your registered groups.
● /deletegroup: Delete a registered group or configuration.

3️⃣ <b>Post Code Generator (Private)</b>
● /myserver: Manage your video sources (servers) in an interactive menu.

4️⃣ <b>Other Commands</b>
● /start: Shows this message.
● /cancel: Cancels the current operation.
● /help: Shows the detailed command guide.
● /getid: Get the current chat's ID, or the ID from a forwarded message.
"""
    keyboard = [[InlineKeyboardButton("🚀 Telegram Group", url="https://t.me/abeflixgroupchat")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(photo=config.DEFAULT_THUMBNAIL, caption=start_caption, parse_mode="HTML", reply_markup=reply_markup)

# --- REPLACED HELP COMMAND ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("Please use the /help command in a private chat with me for a full guide.")
        return

    user_guide = """
    👋 <b>Bot Command Guide</b>

    Here is a detailed guide on how to use my features. Commands marked with (Admin) require you to be an admin in the relevant group.

    <b><u>🔎 General Commands</u></b>
    ● /search <code>&lt;title&gt;</code>
      - Finds movies or TV shows.
      - <i>Example:</i> <code>/search The Matrix</code>

    ● /request
      - Starts a request for a movie or TV show. Must be used inside a configured group, which will then send you a private message to continue.

    <b><u>📢 Broadcasting Features (Private)</u></b>
    ● /broadcast
      - Starts a step-by-step process to create and send a formatted post to a channel.
      - <i>Flow: Thumbnail → Title → Description → Buttons → Reactions.</i>
    
    ● /addgroup
      - (Admin) Links groups/channels to the bot for broadcasting or user requests.
      - You will be asked if it's for broadcasting or for requests.

    ● /mygroups
      - (Admin) Lists all the groups and request configurations you have set up.

    ● /deletegroup
      - (Admin) Removes a group or a request configuration you previously set up.

    <b><u>⚙️ Post Code & Server Management (Private)</u></b>
    ● /myserver
      - Manage your custom video sources (servers) used for the 'Generate Post Code' feature. You can add, delete, and toggle sources.
    
    <b><u>🛠️ Utility Commands</u></b>
    ● /start
      - Shows the main welcome message.

    ● /getid
      - Replies with the current chat's ID. If you reply to a forwarded message, it gives the ID of the original channel/group.

    ● /cancel
      - Stops any active multi-step command you are in (like /addgroup or /broadcast).
    """
    await update.message.reply_text(user_guide, parse_mode="HTML", disable_web_page_preview=True)


async def request_in_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("To make a request, please use the /request command inside a configured group.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the chat ID of the current chat OR the forwarded chat."""
    message = update.effective_message
    
    forward_chat = None
    if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
        forward_chat = message.forward_from_chat
    elif message.forward_origin and hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
         forward_chat = message.forward_origin.chat

    if forward_chat:
        chat_id = forward_chat.id
        chat_title = forward_chat.title
        await message.reply_text(
            f"The forwarded message is from:\n"
            f"<b>{chat_title}</b>\n"
            f"ID: <code>{chat_id}</code>",
            parse_mode="HTML"
        )
    else:
        chat_id = update.effective_chat.id
        await message.reply_text(f"This chat's ID is: <code>{chat_id}</code>", parse_mode="HTML")

# --- UNIFIED GROUP MANAGEMENT ---
async def add_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private': await update.message.reply_text(PRIVATE_CHAT_ONLY_MESSAGE); return ConversationHandler.END
    keyboard = [[InlineKeyboardButton("📢 For My Broadcasts", callback_data="add_broadcast")], [InlineKeyboardButton("📝 For User Requests", callback_data="add_request")]]
    await update.message.reply_text("What is the purpose of the group you want to add?", reply_markup=InlineKeyboardMarkup(keyboard))
    return config.CHOOSE_GROUP_TYPE

async def handle_group_type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); choice = query.data
    if choice == "add_broadcast":
        await query.edit_message_text("To add a broadcast group, please **forward a message** from that channel, **or send me its Chat ID**.")
        return config.ADD_BROADCAST_GROUP_ID
    elif choice == "add_request":
        await query.edit_message_text("Alright, let's set up the request system.\n\n1️⃣ First, please **forward a message** from the group where users will type /request, **or send me its Chat ID**.")
        return config.AWAITING_SOURCE_GROUP_FORWARD

async def get_chat_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int | None, str | None]:
    chat_id = None
    chat_title = None
    message = update.message
    
    forward_chat = None
    if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
        forward_chat = message.forward_from_chat
    elif message.forward_origin and hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
        forward_chat = message.forward_origin.chat
    
    if forward_chat:
        chat_id = forward_chat.id
        chat_title = forward_chat.title
    elif message.text:
        try:
            chat_id = int(message.text.strip())
            chat = await context.bot.get_chat(chat_id)
            chat_title = chat.title
        except ValueError:
            await message.reply_text("That is not a valid numeric ID.")
            return None, None
        except Exception as e:
            await message.reply_text(f"Could not get info for that ID. Error: {e}")
            return None, None
            
    return chat_id, chat_title


async def save_broadcast_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, chat_title = await get_chat_info(update, context)
    if not chat_id: return config.ADD_BROADCAST_GROUP_ID
    user_collection.update_one({"user_id": update.effective_user.id}, {"$addToSet": {"broadcast_groups": {"id": str(chat_id), "title": chat_title}}}, upsert=True)
    await update.message.reply_text(f"✅ Success! You can now broadcast to **{chat_title}**.", parse_mode="HTML")
    return ConversationHandler.END

async def handle_source_group_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, chat_title = await get_chat_info(update, context)
    if not chat_id or not chat_title: return config.AWAITING_SOURCE_GROUP_FORWARD
    if not await is_user_chat_admin(context, chat_id, update.effective_user.id):
        await update.message.reply_text(f"❌ You are not an administrator in **{chat_title}**. Action canceled.", parse_mode="HTML"); return ConversationHandler.END
    context.user_data['source_group_id_to_set'] = chat_id; context.user_data['source_group_title_to_set'] = chat_title
    await update.message.reply_text(f"✅ Great, you've selected **{chat_title}**.\n\n2️⃣ Now, please **forward a message** from the request channel, **or send me its Chat ID**.", parse_mode="HTML")
    return config.AWAITING_DEST_GROUP_FORWARD

async def handle_dest_group_and_save_config(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    source_group_id = context.user_data.get('source_group_id_to_set'); source_group_title = context.user_data.get('source_group_title_to_set')
    if not source_group_id: await update.message.reply_text("Error. Please start over."); return ConversationHandler.END
    dest_chat_id, dest_chat_title = await get_chat_info(update, context)
    if not dest_chat_id: return config.AWAITING_DEST_GROUP_FORWARD
    group_configs_collection.update_one({"_id": source_group_id}, {"$set": {"request_group_id": dest_chat_id, "request_group_title": dest_chat_title, "admin_id": update.effective_user.id}}, upsert=True)
    await update.message.reply_text(f"✅ **Success!** Requests from **{source_group_title}** will now be sent to **{dest_chat_title}**.", parse_mode="HTML")
    context.user_data.clear(); return ConversationHandler.END

async def my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; message_parts = []
    user_data = user_collection.find_one({"user_id": user_id}); broadcast_groups = user_data.get("broadcast_groups", []) if user_data else []
    if broadcast_groups: message_parts.append("<b>📢 Your Personal Broadcast Groups:</b>"); [message_parts.append(f"- {g['title']} (ID: <code>{g['id']}</code>)") for g in broadcast_groups]
    request_configs = group_configs_collection.find({"admin_id": user_id}); request_group_list = list(request_configs)
    if request_group_list:
        if message_parts: message_parts.append("")
        message_parts.append("<b>📝 Request Groups You've Configured:</b>")
        for config_doc in request_group_list:
            source_title = "Unknown Group";
            try: source_chat = await context.bot.get_chat(config_doc['_id']); source_title = source_chat.title
            except Exception: pass
            dest_title = config_doc.get('request_group_title', 'Unknown')
            message_parts.append(f"• In <b>{source_title}</b> → requests go to <b>{dest_title}</b>")
    if not message_parts: await update.message.reply_text("You have not registered any groups.")
    else: await update.message.reply_text("\n".join(message_parts), parse_mode="HTML")

async def delete_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private': await update.message.reply_text(PRIVATE_CHAT_ONLY_MESSAGE); return ConversationHandler.END
    user_id = update.effective_user.id; buttons = []
    user_data = user_collection.find_one({"user_id": user_id}); broadcast_groups = user_data.get("broadcast_groups", []) if user_data else []
    for g in broadcast_groups: buttons.append([InlineKeyboardButton(f"📢 Broadcast: {g['title']}", callback_data=f"del_broadcast_{g['id']}")])
    request_configs = group_configs_collection.find({"admin_id": user_id})
    for config_doc in request_configs:
        source_id = config_doc['_id']; source_title = "Group"
        try: chat = await context.bot.get_chat(source_id); source_title = chat.title
        except: pass
        buttons.append([InlineKeyboardButton(f"📝 Request: {source_title}", callback_data=f"del_request_{source_id}")])
    if not buttons: await update.message.reply_text("You have no groups or configurations to delete."); return ConversationHandler.END
    await update.message.reply_text("Which group or configuration would you like to delete?", reply_markup=InlineKeyboardMarkup(buttons))
    return config.DELETING_GROUP

async def handle_delete_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    parts = query.data.split('_', 2); group_type, group_id = parts[1], parts[2]
    user_id = query.from_user.id
    if group_type == "broadcast":
        user_collection.update_one({"user_id": user_id}, {"$pull": {"broadcast_groups": {"id": group_id}}})
        await query.edit_message_text("✅ Broadcast group has been deleted.")
    elif group_type == "request":
        group_configs_collection.delete_one({"_id": int(group_id), "admin_id": user_id})
        await query.edit_message_text("✅ Request configuration has been deleted.")
    else: await query.edit_message_text("An unknown error occurred.")
    return ConversationHandler.END

# --- NEW UNIFIED SOURCE MANAGEMENT ---
async def _get_server_management_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Helper function to generate the server management keyboard."""
    user_doc = user_collection.find_one({"user_id": user_id})
    custom_sources = user_doc.get("sources", []) if user_doc else []
    disabled_sources = user_doc.get("disabled_sources", []) if user_doc else []
    all_sources = DEFAULT_SOURCES + custom_sources
    
    keyboard = []
    row = []
    for source in all_sources:
        name = source['name']
        status_icon = "❌" if name in disabled_sources else "✅"
        button = InlineKeyboardButton(f"{status_icon} {name}", callback_data=f"server_toggle_{name}")
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([
        InlineKeyboardButton("➕ Add", callback_data="server_add"),
        InlineKeyboardButton("➖ Delete", callback_data="server_delete"),
        InlineKeyboardButton("🔄 Reset", callback_data="server_reset")
    ])
    keyboard.append([InlineKeyboardButton("Done", callback_data="server_done")])
    
    return InlineKeyboardMarkup(keyboard)

async def my_server_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.chat.type != 'private':
        await update.message.reply_text(PRIVATE_CHAT_ONLY_MESSAGE)
        return ConversationHandler.END
        
    user_id = update.effective_user.id
    keyboard = await _get_server_management_keyboard(user_id)
    await update.message.reply_text(
        "⚙️ **Server Management**\n\n"
        "Click on a server to toggle it (✅ Enabled / ❌ Disabled).\n"
        "Use the buttons below to manage your custom servers.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return VIEWING_SERVERS

async def my_server_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    action = query.data.split('_', 1)[1]

    if query.data.startswith("server_toggle_"):
        source_name = action.split('_', 1)[1]
        user_doc = user_collection.find_one({"user_id": user_id})
        disabled_sources = user_doc.get("disabled_sources", []) if user_doc else []
        
        if source_name in disabled_sources:
            user_collection.update_one({"user_id": user_id}, {"$pull": {"disabled_sources": source_name}})
        else:
            user_collection.update_one({"user_id": user_id}, {"$addToSet": {"disabled_sources": source_name}}, upsert=True)
            
        keyboard = await _get_server_management_keyboard(user_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return VIEWING_SERVERS

    if action == "add":
        await query.edit_message_text("Enter the name for the new source (e.g., 'MyServer').")
        return config.GET_SOURCE_NAME
        
    elif action == "delete":
        user_doc = user_collection.find_one({"user_id": user_id})
        custom_sources = user_doc.get("sources", []) if user_doc else []
        if not custom_sources:
            await query.answer("You have no custom sources to delete.", show_alert=True)
            return VIEWING_SERVERS
        
        buttons = [[InlineKeyboardButton(f"❌ {source['name']}", callback_data=f"delsrc_{source['name']}")] for source in custom_sources]
        buttons.append([InlineKeyboardButton("« Back", callback_data="server_back")])
        await query.edit_message_text("Select a custom source to delete:", reply_markup=InlineKeyboardMarkup(buttons))
        return DELETING_SERVER_CHOICE

    elif action == "reset":
        user_collection.update_one({"user_id": user_id}, {"$set": {"sources": [], "disabled_sources": []}}, upsert=True)
        keyboard = await _get_server_management_keyboard(user_id)
        await query.edit_message_text(
            "✅ All custom sources removed and defaults re-enabled.\n\n"
            "⚙️ **Server Management**",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return VIEWING_SERVERS
        
    elif action == "done":
        await query.edit_message_text("✅ Your server settings have been saved.")
        return ConversationHandler.END

    return VIEWING_SERVERS

async def my_server_delete_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "server_back":
        keyboard = await _get_server_management_keyboard(query.from_user.id)
        await query.edit_message_text(
            "⚙️ **Server Management**",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return VIEWING_SERVERS
    
    source_name = query.data.split("_", 1)[1]
    user_collection.update_one(
        {"user_id": query.from_user.id},
        {"$pull": {"sources": {"name": source_name}}}
    )
    
    await query.answer(f"✅ Source '{source_name}' deleted.", show_alert=True)
    
    keyboard = await _get_server_management_keyboard(query.from_user.id)
    await query.edit_message_text(
        "⚙️ **Server Management**",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return VIEWING_SERVERS

async def my_server_get_source_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_source_name'] = update.message.text.strip()
    await update.message.reply_text("Great. Now, enter the URL for MOVIES.\nUse `{tmdb_id}` as a placeholder for the TMDB ID.")
    return config.GET_MOVIE_URL

async def my_server_get_movie_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_movie_url'] = update.message.text.strip()
    await update.message.reply_text("Finally, enter the URL for TV SHOWS.\nUse `{tmdb_id}`, `{season}`, and `{episode}` as placeholders.")
    return config.GET_TV_URL

async def my_server_save_tv_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_source = {
        "name": context.user_data['new_source_name'],
        "movie_url": context.user_data['new_movie_url'],
        "tv_url": update.message.text.strip()
    }
    user_collection.update_one(
        {"user_id": update.effective_user.id},
        {"$addToSet": {"sources": new_source}},
        upsert=True
    )
    await update.message.reply_text(f"✅ Source '{new_source['name']}' added successfully!")
    context.user_data.clear()

    keyboard = await _get_server_management_keyboard(update.effective_user.id)
    await update.message.reply_text(
        "⚙️ **Server Management**",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return VIEWING_SERVERS

# --- GENCODE ---
async def gencode_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Please check your private messages with me to continue.", show_alert=True)
    try: await query.message.delete()
    except Exception: pass
    try:
        parts = query.data.split("_")
        tmdb_id, media_type = parts[1], parts[2]
        if len(parts) == 4 and media_type == 'tv':
            season_number = int(parts[3])
            await gencode_generate_and_send(update, context, tmdb_id, media_type, season_number)
            return ConversationHandler.END
        elif media_type == 'movie':
            await gencode_generate_and_send(update, context, tmdb_id, media_type)
            return ConversationHandler.END
        else:
            context.user_data['gencode_info'] = {"tmdb_id": tmdb_id, "media_type": media_type}
            await context.bot.send_message(chat_id=query.from_user.id, text="Generating code for a TV show.\nPlease enter the Season Number (press Enter for default: 1).")
            return config.AWAITING_SEASON_CHOICE
    except BadRequest:
        await context.bot.send_message(chat_id=query.message.chat.id, text=f"{query.from_user.mention_html()}, I can't send you a private message. Please start a chat with me first and try again.", parse_mode="HTML"); return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in gencode_start: {e}"); return ConversationHandler.END

async def gencode_handle_season_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    season_input = update.message.text.strip()
    season = 1
    if season_input:
        try: season = int(season_input)
        except ValueError: await update.message.reply_text("Invalid number. Using default Season 1."); season = 1
    gencode_info = context.user_data.get('gencode_info', {})
    if not gencode_info:
        await update.message.reply_text("An error occurred. Please try generating the code again.")
        return ConversationHandler.END
    await gencode_generate_and_send(update, context, gencode_info['tmdb_id'], gencode_info['media_type'], season)
    return ConversationHandler.END

async def gencode_generate_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, tmdb_id: str, media_type: str, season: int = 1):
    user_id = update.effective_user.id
    await context.bot.send_message(chat_id=user_id, text="⏳ Generating code, please wait...")
    details, credits = search.get_details(tmdb_id, media_type)
    extra_details = search.get_extra_details_for_labels(tmdb_id, media_type)
    year = (details.get('release_date') or details.get('first_air_date') or '')[:4]
    season_details = {}
    if media_type == 'tv':
        media_type_label = 'TV Series'; season_details = search.get_season_details(tmdb_id, season)
        if season_details.get('air_date'): year = season_details['air_date'][:4]
    else: media_type_label = 'Movie'
    labels = [media_type_label]
    labels.extend([g['name'] for g in details.get('genres', [])])
    if extra_details.get('rating'): labels.append(f"z{extra_details['rating']}")
    if year: labels.append(f"zYear:{year}")
    if media_type == 'movie' and details.get('runtime'): labels.append(f"zDuration:{details.get('runtime')}min")
    elif media_type == 'tv' and details.get('episode_run_time'):
        if details.get('episode_run_time'): labels.append(f"zDuration:{details['episode_run_time'][0]}min")
    if details.get('status') == 'Returning Series': labels.append('zOngoing')
    elif details.get('status') == 'Ended': labels.append('zEnded')
    if details.get("production_countries"): labels.append(f"zCountry:{details.get('production_countries')[0]['iso_3166_1']}")
    labels_text = ",".join(labels)
    user_sources_doc = user_collection.find_one({"user_id": user_id})
    all_possible_sources = list(DEFAULT_SOURCES)
    if user_sources_doc and "sources" in user_sources_doc:
        all_possible_sources.extend(user_sources_doc.get("sources", []))
    disabled_source_names = user_sources_doc.get("disabled_sources", []) if user_sources_doc else []
    sources_to_use = [source for source in all_possible_sources if source.get("name") not in disabled_source_names]
    post_id = "5083835698040575230"; poster_url = f"https://image.tmdb.org/t/p/w500{details.get('poster_path', '')}"; overview = details.get('overview', ''); default_thumbnail = f"https://image.tmdb.org/t/p/original{details.get('backdrop_path', '')}"
    celebrities = [{"name": c.get('name'), "photo": f"https://image.tmdb.org/t/p/w185{c.get('profile_path')}" if c.get('profile_path') else "", "title": c.get('character')} for c in credits.get('cast', [])[:10]]
    episodes_list, downloads_list = [], []
    if media_type == 'tv':
        episodes_data = season_details.get('episodes', [])
        if not episodes_data:
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ Could not find any episodes for Season {season}. Please check the season number on TMDB and try again."); context.user_data.clear(); return
        for ep_data in episodes_data:
            ep_num = ep_data['episode_number']
            episodes_list.append({"episode": f"{ep_num:02d}", "thumb": "", "videos": {s['name']: s['tv_url'].format(tmdb_id=tmdb_id, season=season, episode=ep_num) for s in sources_to_use}})
            downloads_list.append({"source": f"Vidsrc.vip Ep{ep_num}", "quality": "Multiquality", "size": "-", "url": f"https://dl.vidsrc.vip/tv/{tmdb_id}/{season}/{ep_num}"})
    else: # Movie
        episodes_list.append({"episode": "01", "thumb": "", "videos": {s['name']: s['movie_url'].format(tmdb_id=tmdb_id) for s in sources_to_use}})
        downloads_list.append({"source": "Vidsrc.vip Movie", "quality": "Multiquality", "size": "-", "url": f"https://dl.vidsrc.vip/movie/{tmdb_id}"})
    script_content = f"const defaultThumbnail = '{default_thumbnail}';\nconst episodes = {json.dumps(episodes_list, indent=2)};\nconst downloads = {json.dumps(downloads_list, indent=2)};\nconst celebrities = {json.dumps(celebrities, indent=2)};"
    html_content = f'<div>\n <span id="post-id" data-post-id="{post_id}"></span>\n  <img alt="poster" src="{poster_url}" />\n  <iframe class="lazyloaded" data-src="/" src="/"></iframe>\n  <p>{overview}</p>\n  <script>\n    {script_content}\n  </script>\n</div>'
    with io.BytesIO(html_content.encode('utf-8')) as f: f.name = 'post_code.txt'; await context.bot.send_document(chat_id=user_id, document=f)
    with io.BytesIO(labels_text.encode('utf-8')) as f: f.name = 'labels.txt'; await context.bot.send_document(chat_id=user_id, document=f)
    context.user_data.clear()

async def search_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); data = query.data
    if data == "next_page":
        context.user_data["search_page"] += 1; await search.send_search_page(update, context, edit=True)
    elif data == "prev_page":
        context.user_data["search_page"] -= 1; await search.send_search_page(update, context, edit=True)
    elif data.startswith("select_"):
        parts = data.split("_")
        tmdb_id, media_type = parts[1], parts[2]
        if media_type == 'tv' and len(parts) == 4:
            season_number = int(parts[3])
            await search.send_details_display_new(update, context, tmdb_id, media_type, season_number)
        else: await search.send_details_display_new(update, context, tmdb_id, media_type)

async def handle_season_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try:
        _, tmdb_id, season_number_str = query.data.split('_')
        season_number = int(season_number_str)
        await search.send_details_display_new(update, context, tmdb_id, 'tv', season_number)
    except Exception as e:
        logger.error(f"Error in handle_season_selection: {e}")
        try: await query.edit_message_text("An error occurred. Please try again.")
        except BadRequest: pass

async def handle_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, tmdb_id, media_type = query.data.split('_')
        trailer_url = search.get_trailer_link(tmdb_id, media_type)
        if trailer_url: await query.answer(url=trailer_url)
        else: await query.answer("No trailer found for this title.", show_alert=True)
    except Exception as e:
        logger.error(f"Error handling trailer button: {e}"); await query.answer("Could not fetch trailer.", show_alert=True)

async def handle_copy_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    caption_text = query.message.caption
    if caption_text: await query.answer(text=caption_text[:199], show_alert=True)
    else: await query.answer("No details to copy.", show_alert=True)

async def unified_callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == 'ignore':
        await query.answer("This is a status indicator.")
        return
    await query.answer("This button is for display or is handled elsewhere.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    await message.reply_text("Action canceled.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    persistence = PicklePersistence(filepath="bot_persistence")
    app = ApplicationBuilder().token(config.BOT_TOKEN).persistence(persistence).build()
    cancel_handler = CommandHandler("cancel", cancel)
    
    # --- Conversation Handlers ---
    
    # --- NEW BROADCAST CONVERSATION HANDLER ---
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast.start_broadcast)],
        states={
            config.GET_THUMBNAIL: [MessageHandler(filters.PHOTO, broadcast.get_thumbnail)],
            config.GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast.get_title)],
            config.GET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast.get_description)],
            config.GET_BUTTONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast.get_buttons)],
            config.GET_REACTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, partial(broadcast.get_reactions_and_choose_target, user_collection=user_collection))],
            config.CHOOSE_TARGET: [
                CallbackQueryHandler(partial(broadcast.handle_target_choice, user_collection=user_collection, broadcasts_collection=broadcasts_collection), pattern=r"^bcast_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, partial(broadcast.handle_target_choice, user_collection=user_collection, broadcasts_collection=broadcasts_collection))
            ]
        },
        fallbacks=[cancel_handler],
        name="broadcast_conversation",
        persistent=True,
        conversation_timeout=600  # 10 minutes
    )

    add_group_conv = ConversationHandler(
        entry_points=[CommandHandler("addgroup", add_group_start)],
        states={
            config.CHOOSE_GROUP_TYPE: [CallbackQueryHandler(handle_group_type_choice, pattern=r"^add_")],
            config.AWAITING_SOURCE_GROUP_FORWARD: [MessageHandler(filters.FORWARDED | filters.TEXT & ~filters.COMMAND, handle_source_group_forward)],
            config.AWAITING_DEST_GROUP_FORWARD: [MessageHandler(filters.FORWARDED | filters.TEXT & ~filters.COMMAND, partial(handle_dest_group_and_save_config, group_configs_collection=group_configs_collection))],
            config.ADD_BROADCAST_GROUP_ID: [MessageHandler((filters.FORWARDED|filters.TEXT)&~filters.COMMAND, save_broadcast_group)]
        },
        fallbacks=[cancel_handler],
        name="unified_add_group_conversation",
        persistent=True,
        conversation_timeout=300
    )
    
    request_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start, filters=filters.Regex(r'\/start request_'))],
        states={
            config.REQ_CHOOSE_TYPE: [CallbackQueryHandler(request.choose_request_type, pattern="^req_")],
            config.REQ_GET_POSTER: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, request.get_poster)],
            config.REQ_GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, request.get_title)],
            config.REQ_GET_MEDIA_TYPE: [CallbackQueryHandler(request.get_media_type, pattern="^type_")],
            config.REQ_GET_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, request.get_year)],
            config.REQ_GET_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, request.get_country)],
            config.REQ_GET_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, partial(request.get_final_detail_and_send, group_configs_collection=group_configs_collection))],
            config.REQ_GET_CONCERN_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, request.get_concern_subject)],
            config.REQ_GET_CONCERN_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, request.get_concern_image)],
            config.REQ_GET_CONCERN_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, partial(request.get_final_detail_and_send, group_configs_collection=group_configs_collection))]
        },
        fallbacks=[cancel_handler],
        name="request_conversation",
        persistent=True,
        allow_reentry=True,
        conversation_timeout=300
    )
    
    admin_remark_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(request.start_remark_conversation, pattern=r"^req_remark\|")],
        states={config.AWAITING_REMARK: [MessageHandler(filters.TEXT&~filters.COMMAND, request.handle_admin_remark)]},
        fallbacks=[cancel_handler],
        name="admin_remark_conversation",
        persistent=True,
        per_user=True,
        per_chat=False,
        allow_reentry=True,  
        conversation_timeout=300  
    )

    delete_group_conv = ConversationHandler(
        entry_points=[CommandHandler("deletegroup", delete_group_start)],
        states={config.DELETING_GROUP: [CallbackQueryHandler(handle_delete_group_selection, pattern=r"^del_")]},
        fallbacks=[cancel_handler],
        name="delete_group_conversation",
        persistent=True,
        conversation_timeout=300
    )

    gencode_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(gencode_start, pattern=r"^gencode_")],
        states={config.AWAITING_SEASON_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, gencode_handle_season_choice)]},
        fallbacks=[cancel_handler],
        name="gencode_conversation",
        persistent=True,
        per_user=True,
        per_chat=False,
        conversation_timeout=300
    )

    my_server_conv = ConversationHandler(
        entry_points=[CommandHandler("myserver", my_server_start)],
        states={
            VIEWING_SERVERS: [CallbackQueryHandler(my_server_actions, pattern=r"^server_")],
            DELETING_SERVER_CHOICE: [CallbackQueryHandler(my_server_delete_source, pattern=r"^(delsrc_|server_back)")],
            config.GET_SOURCE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, my_server_get_source_name)],
            config.GET_MOVIE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, my_server_get_movie_url)],
            config.GET_TV_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, my_server_save_tv_url)],
        },
        fallbacks=[cancel_handler],
        name="my_server_conversation",
        persistent=True,
        conversation_timeout=300
    )

    # --- Register Handlers ---
    app.add_handler(broadcast_conv)
    app.add_handler(add_group_conv)
    app.add_handler(request_conv)
    app.add_handler(admin_remark_conv)
    app.add_handler(delete_group_conv)
    app.add_handler(gencode_conv)
    app.add_handler(my_server_conv)

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(search_button_handler, pattern=r"^(select_|next_page|prev_page)")); 
    app.add_handler(CallbackQueryHandler(handle_season_selection, pattern=r"^seasonselect_")); 
    app.add_handler(CallbackQueryHandler(handle_trailer, pattern=r"^trailer_")); 
    app.add_handler(CallbackQueryHandler(handle_copy_details, pattern=r"^copy_details_")); 
    app.add_handler(CallbackQueryHandler(request.handle_request_tracking, pattern=r"^req_track\|")); 
    app.add_handler(CallbackQueryHandler(unified_callback_query_handler, pattern=r"^react_"))
    
    # Command Handlers
    app.add_handler(CommandHandler("request", partial(request.request_command_in_group, group_configs_collection=group_configs_collection), filters=filters.ChatType.GROUPS));
    app.add_handler(CommandHandler("request", request_in_private, filters=filters.ChatType.PRIVATE));
    app.add_handler(CommandHandler("start", start, filters=~filters.Regex(r'\/start request_'))); 
    app.add_handler(CommandHandler("help", help_command)); 
    app.add_handler(CommandHandler("search", search.search_command)); 
    app.add_handler(CommandHandler("mygroups", my_groups)); 
    app.add_handler(CommandHandler("getid", get_id))
    
    # Other Handlers
    app.add_handler(InlineQueryHandler(search.inline_query_handler)); 
    app.add_handler(MessageHandler(filters.Regex(r'^\/show_'), search.show_from_inline))
    
    # Generic callback handler (must be last)
    app.add_handler(CallbackQueryHandler(unified_callback_query_handler))

    print("🚀 Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
