import pymongo
import logging
from functools import partial
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    PicklePersistence,
)
from telegram.error import BadRequest
from telegram.constants import ChatType

import config
import request
import broadcast
import admin
import themes
import licenses

# --- Setup Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
PRIVATE_CHAT_ONLY_MESSAGE = "This command can only be used in a private chat with me."
NOT_ADMIN_MESSAGE = "⛔ You are not authorized to use this command."

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

# --- HELPER: Checks if a user is an admin in a chat ---
async def is_user_chat_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return user_id in [admin.user.id for admin in admins]
    except Exception:
        return False

# --- HELPER: Check Bot Owner ---
def is_bot_owner(user_id):
    # Ensure config.ADMIN_ID is treated as an integer for comparison
    return user_id == int(config.ADMIN_ID)

# --- Helper: Delete Command Message ---
async def delete_command_message(update: Update):
    """Deletes the command message sent by the user to keep chat clean (Groups Only)."""
    if update.effective_chat.type == ChatType.PRIVATE: return
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass 

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    
    # 1. Handle Request Deep Link
    if context.args and context.args[0].startswith("request_"):
        try:
            source_group_id = int(context.args[0].split('_')[1])
            context.user_data['source_group_id'] = source_group_id
            return await request.start_request_conversation(update, context)
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid request link.")
            return ConversationHandler.END
            
    # 2. Handle Admin Configuration Deep Link
    if context.args and context.args[0].startswith("configure_group_"):
        return await admin.start_proactive_configuration(update, context, group_configs_collection)
    
    # 3. Standard Welcome Message
    start_caption = """👋 <b>Welcome to the ABEFILM BOT OFFICIAL!</b>

<b>Features available:</b>
● <b>/request</b>: Request content (in groups).
● <b>/theme</b>: Browse & Buy Premium Themes.
● <b>/register</b>: Activate your Theme License.
● <b>/check</b>: Check License Status.
● <b>/removedomain</b>: Remove/Reset License Domain.

<b>Admin Tools:</b>
● /broadcast, /addgroup, /mygroups
● /createlicense, /addtheme, /deletetheme
"""
    keyboard = [[InlineKeyboardButton("🚀 Telegram Group", url="https://t.me/abeflixgroupchat")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=config.DEFAULT_THUMBNAIL, 
            caption=start_caption, 
            parse_mode="HTML", 
            reply_markup=reply_markup
        )
    except Exception:
        await update.message.reply_text(start_caption, parse_mode="HTML", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if update.message.chat.type != 'private':
        try:
            await context.bot.send_message(update.effective_user.id, "Please use /help in a private chat.")
        except:
            pass
        return

    user_guide = """
    👋 <b>Bot Command Guide</b>
    
    <b><u>👤 User Commands</u></b>
    ● <b>/request</b> - Start a request (inside groups).
    ● <b>/theme</b> - Browse and buy themes.
    ● <b>/register &lt;KEY&gt; &lt;DOMAIN&gt;</b> - Activate license.
    ● <b>/check &lt;KEY&gt;</b> - Check license status.
    ● <b>/removedomain &lt;KEY&gt;</b> - Reset domain.

    <b><u>👮‍♂️ Admin Only</u></b>
    ● <b>/broadcast</b> - Send a post to channels.
    ● <b>/addgroup</b> - Register groups.
    ● <b>/mygroups</b> - List groups.
    ● <b>/addtheme</b> - Add new theme.
    ● <b>/deletetheme</b> - Remove theme.
    ● <b>/createlicense</b> - Generate key.
    """
    await update.message.reply_text(user_guide, parse_mode="HTML", disable_web_page_preview=True)

async def request_in_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    await update.message.reply_text("To make a request, please use the /request command inside a configured group.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ALLOW EVERYONE TO USE THIS COMMAND SO YOU CAN FIND YOUR ID
    message = update.effective_message
    if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        title = message.forward_from_chat.title
        await message.reply_text(f"Forward from: <b>{title}</b>\nID: <code>{chat_id}</code>", parse_mode="HTML")
    else:
        chat_id = update.effective_chat.id
        await message.reply_text(f"This chat's ID is: <code>{chat_id}</code>", parse_mode="HTML")

# --- GROUP MANAGEMENT ---
async def add_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END
        
    if update.message.chat.type != 'private': 
        await update.message.reply_text(PRIVATE_CHAT_ONLY_MESSAGE)
        return ConversationHandler.END
        
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
        text_input = message.text.strip()
        if "_" in text_input:
            try: chat_id = int(text_input.split("_")[0]) 
            except ValueError: await message.reply_text("Invalid ID format."); return None, None
        else:
            try: chat_id = int(text_input)
            except (ValueError, BadRequest): await message.reply_text("That is not a valid numeric ID."); return None, None
        
        try:
            chat = await context.bot.get_chat(chat_id)
            chat_title = chat.title
        except Exception:
            await message.reply_text(f"Could not access chat {chat_id}. Make sure I am an Admin there first!")
            return None, None
            
    return chat_id, chat_title

async def save_broadcast_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, chat_title = await get_chat_info(update, context)
    if not chat_id: return config.ADD_BROADCAST_GROUP_ID
    
    thread_id = None
    if update.message.text and "_" in update.message.text:
        try:
            parts = update.message.text.strip().split("_")
            if len(parts) == 2 and parts[1].isdigit():
                thread_id = int(parts[1])
        except Exception:
            pass

    group_data = {"id": str(chat_id), "title": chat_title, "thread_id": thread_id}
    user_collection.update_one({"user_id": update.effective_user.id}, {"$pull": {"broadcast_groups": {"id": str(chat_id), "thread_id": thread_id}}})
    user_collection.update_one({"user_id": update.effective_user.id}, {"$addToSet": {"broadcast_groups": group_data}}, upsert=True)
    
    topic_msg = f" (Topic: {thread_id})" if thread_id else ""
    await update.message.reply_text(f"✅ Success! You can now broadcast to **{chat_title}**{topic_msg}.", parse_mode="HTML")
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
    source_group_id = context.user_data.get('source_group_id_to_set')
    source_group_title = context.user_data.get('source_group_title_to_set')
    
    if not source_group_id: 
        await update.message.reply_text("Error. Please start over.")
        return ConversationHandler.END
        
    dest_chat_id, dest_chat_title = await get_chat_info(update, context)
    if not dest_chat_id: return config.AWAITING_DEST_GROUP_FORWARD

    try:
        full_chat = await context.bot.get_chat(dest_chat_id)
        if full_chat.is_forum:
            context.user_data['dest_group_id_pending'] = dest_chat_id
            context.user_data['dest_group_title_pending'] = dest_chat_title
            await update.message.reply_text(
                f"⚠️ **Topic Detected in {dest_chat_title}**\n\n"
                "Please send me the **Topic ID** (Thread ID) where requests should be sent.\n"
                "• Send <code>4493</code> for your Request Sub-topic.\n"
                "• Send <code>0</code> for General.",
                parse_mode="HTML"
            )
            return config.AWAITING_DEST_TOPIC_ID
    except Exception as e:
        logger.error(f"Forum check error: {e}")

    group_configs_collection.update_one(
        {"_id": source_group_id}, 
        {"$set": {"request_group_id": dest_chat_id, "request_group_title": dest_chat_title, "request_thread_id": None, "admin_id": update.effective_user.id}}, 
        upsert=True
    )
    await update.message.reply_text(f"✅ **Success!** Requests from **{source_group_title}** will go to **{dest_chat_title}**.", parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

async def handle_dest_topic_selection_manual(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    topic_input = update.message.text.strip()
    source_group_id = context.user_data.get('source_group_id_to_set')
    source_group_title = context.user_data.get('source_group_title_to_set')
    dest_chat_id = context.user_data.get('dest_group_id_pending')
    dest_chat_title = context.user_data.get('dest_group_title_pending')

    if not topic_input.isdigit():
        await update.message.reply_text("Please send a numeric Topic ID (e.g., 4493).")
        return config.AWAITING_DEST_TOPIC_ID
        
    thread_id = int(topic_input)
    if thread_id == 0: thread_id = None

    group_configs_collection.update_one(
        {"_id": source_group_id}, 
        {"$set": {"request_group_id": dest_chat_id, "request_group_title": dest_chat_title, "request_thread_id": thread_id, "admin_id": update.effective_user.id}}, 
        upsert=True
    )
    
    topic_label = f" (Topic: {thread_id})" if thread_id else " (General)"
    await update.message.reply_text(f"✅ **Success!** Requests from **{source_group_title}** will go to **{dest_chat_title}**{topic_label}.", parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

async def my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return

    user_id = update.effective_user.id; message_parts = []
    user_data = user_collection.find_one({"user_id": user_id})
    broadcast_groups = user_data.get("broadcast_groups", []) if user_data else []
    
    if broadcast_groups: 
        message_parts.append("<b>📢 Your Personal Broadcast Groups:</b>")
        for g in broadcast_groups:
            title = g['title']
            g_id = g['id']
            if g.get('thread_id'):
                title += f" [Topic: {g['thread_id']}]"
            message_parts.append(f"- {title} (ID: <code>{g_id}</code>)")

    request_configs = group_configs_collection.find({"admin_id": user_id}); request_group_list = list(request_configs)
    if request_group_list:
        if message_parts: message_parts.append("")
        message_parts.append("<b>📝 Request Groups You've Configured:</b>")
        for config_doc in request_group_list:
            source_title = "Unknown Group";
            try: source_chat = await context.bot.get_chat(config_doc['_id']); source_title = source_chat.title
            except Exception: pass
            dest_title = config_doc.get('request_group_title', 'Unknown')
            thread_id = config_doc.get('request_thread_id')
            topic_str = f" (Topic: {thread_id})" if thread_id else ""
            message_parts.append(f"• In <b>{source_title}</b> → requests go to <b>{dest_title}</b>{topic_str}")
    if not message_parts: await update.message.reply_text("You have not registered any groups.")
    else: await update.message.reply_text("\n".join(message_parts), parse_mode="HTML")

async def delete_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END

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

# --- BROADCAST WRAPPER (RESTRICTION) ---
async def start_broadcast_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END
    return await broadcast.start_broadcast(update, context)

# --- AUTO DELETE CLEANER ---
async def auto_delete_cleaner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; message = update.effective_message; user = update.effective_user
    if chat.type != ChatType.SUPERGROUP: return
    config_doc = group_configs_collection.find_one({"request_group_id": chat.id})
    if not config_doc: return
    protected_thread = config_doc.get("request_thread_id")
    if not protected_thread or message.message_thread_id != protected_thread: return
    if await is_user_chat_admin(context, chat.id, user.id): return
    try: await message.delete()
    except Exception as e:
        logger.warning(f"Failed to auto-delete message in topic: {e}")

# --- OTHER HANDLERS ---

# --- NEW REACTION HANDLER ---
async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, broadcast_id_str, emoji = query.data.split('_', 2)
        broadcast_id = ObjectId(broadcast_id_str)
        user_id = str(query.from_user.id)
    except (ValueError, IndexError):
        await query.answer("Invalid reaction data.", show_alert=True)
        return

    broadcast_doc = broadcasts_collection.find_one({"_id": broadcast_id})
    if not broadcast_doc:
        await query.answer("This post is no longer available for reactions.", show_alert=True)
        return

    reactions = broadcast_doc.get("reactions", {})
    user_reaction_key = f"reactions.{user_id}"

    if reactions.get(user_id) == emoji:
        broadcasts_collection.update_one({"_id": broadcast_id}, {"$unset": {user_reaction_key: ""}})
        await query.answer("Reaction removed.")
    else:
        broadcasts_collection.update_one({"_id": broadcast_id}, {"$set": {user_reaction_key: emoji}})
        await query.answer("Reaction added!")

    updated_doc = broadcasts_collection.find_one({"_id": broadcast_id})
    new_keyboard_list = broadcast.build_keyboard(updated_doc)
    reply_markup = InlineKeyboardMarkup(new_keyboard_list) if new_keyboard_list else None
    
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest:
        pass

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

# --- ADMIN WRAPPERS ---
async def add_theme_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END
    return await themes.add_theme_start(update, context)

async def del_theme_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END
    return await themes.delete_theme_start(update, context)

async def gen_license_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_message(update)
    if not is_bot_owner(update.effective_user.id):
        await update.message.reply_text(NOT_ADMIN_MESSAGE)
        return ConversationHandler.END
    return await licenses.start_gen_license(update, context)

def main():
    persistence = PicklePersistence(filepath="bot_persistence")
    app = ApplicationBuilder().token(config.BOT_TOKEN).persistence(persistence).build()
    cancel_handler = CommandHandler("cancel", cancel)
    
    # 1. Admin Config
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start, filters=filters.Regex(r'\/start configure_group_'))],
        states={
            config.AWAITING_DEST_GROUP_FOR_CONFIG: [
                MessageHandler(filters.FORWARDED, partial(admin.handle_dest_group_and_save_config, group_configs_collection=group_configs_collection))
            ],
            config.AWAITING_DEST_TOPIC_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, partial(admin.handle_dest_topic_selection, group_configs_collection=group_configs_collection))
            ]
        },
        fallbacks=[cancel_handler],
        name="admin_config_conversation",
        persistent=True
    ))

    # 2. Add Theme Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addtheme", add_theme_wrapper)],
        states={
            config.THEME_GET_NAME: [MessageHandler(filters.TEXT, themes.get_name)],
            config.THEME_GET_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT, themes.get_image)],
            config.THEME_GET_DESC: [MessageHandler(filters.TEXT, themes.get_desc)],
            config.THEME_GET_DEMO: [MessageHandler(filters.TEXT, themes.get_demo)],
            config.THEME_GET_DOCS: [MessageHandler(filters.TEXT, themes.get_docs)],
            config.THEME_GET_BUY: [MessageHandler(filters.TEXT, themes.save_theme)],
        },
        fallbacks=[CommandHandler("cancel", themes.cancel)],
        name="add_theme"
    ))

    # 3. Delete Theme Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("deletetheme", del_theme_wrapper)],
        states={
            config.THEME_DELETE_CHOICE: [CallbackQueryHandler(themes.handle_delete_theme, pattern=r"^del_theme_|cancel_del")]
        },
        fallbacks=[CommandHandler("cancel", themes.cancel)],
        name="del_theme"
    ))

    # 4. Broadcast
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast_wrapper)],
        states={
            config.GET_THUMBNAIL: [MessageHandler(filters.PHOTO, broadcast.get_thumbnail)],
            config.GET_TITLE: [MessageHandler(filters.TEXT, broadcast.get_title)],
            config.GET_DESCRIPTION: [MessageHandler(filters.TEXT, broadcast.get_description)],
            config.GET_BUTTONS: [MessageHandler(filters.TEXT, broadcast.get_buttons)],
            config.GET_REACTIONS: [MessageHandler(filters.TEXT, partial(broadcast.get_reactions_and_choose_target, user_collection=user_collection))],
            config.CHOOSE_TARGET: [
                CallbackQueryHandler(partial(broadcast.handle_target_choice, user_collection=user_collection, broadcasts_collection=broadcasts_collection), pattern=r"^bcast_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, partial(broadcast.handle_target_choice, user_collection=user_collection, broadcasts_collection=broadcasts_collection))
            ]
        },
        fallbacks=[cancel_handler],
        name="broadcast_conversation",
        persistent=True,
        conversation_timeout=600
    ))

    # 5. Add Group
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addgroup", add_group_start)],
        states={
            config.CHOOSE_GROUP_TYPE: [CallbackQueryHandler(handle_group_type_choice, pattern=r"^add_")],
            config.AWAITING_SOURCE_GROUP_FORWARD: [MessageHandler(filters.FORWARDED | filters.TEXT, handle_source_group_forward)],
            config.AWAITING_DEST_GROUP_FORWARD: [MessageHandler(filters.FORWARDED | filters.TEXT, partial(handle_dest_group_and_save_config, group_configs_collection=group_configs_collection))],
            config.AWAITING_DEST_TOPIC_ID: [MessageHandler(filters.TEXT, partial(handle_dest_topic_selection_manual, group_configs_collection=group_configs_collection))],
            config.ADD_BROADCAST_GROUP_ID: [MessageHandler((filters.FORWARDED|filters.TEXT)&~filters.COMMAND, save_broadcast_group)]
        },
        fallbacks=[cancel_handler],
        name="unified_add_group_conversation",
        persistent=True,
        conversation_timeout=300
    ))

    # 6. Request
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start, filters=filters.Regex(r'\/start request_'))],
        states={
            config.REQ_GET_CONCERN_SUBJECT: [MessageHandler(filters.TEXT, request.get_concern_subject)],
            config.REQ_GET_CONCERN_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT, request.get_concern_image)],
            config.REQ_GET_CONCERN_DETAIL: [MessageHandler(filters.TEXT, partial(request.get_final_detail_and_send, group_configs_collection=group_configs_collection))]
        },
        fallbacks=[cancel_handler],
        name="request_conversation",
        persistent=True,
        allow_reentry=True,
        conversation_timeout=300
    ))
    
    # 7. Remarks
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(request.start_remark_conversation, pattern=r"^req_remark\|")],
        states={config.AWAITING_REMARK: [MessageHandler(filters.TEXT&~filters.COMMAND, request.handle_admin_remark)]},
        fallbacks=[cancel_handler],
        name="admin_remark_conversation",
        persistent=True,
        per_user=True,
        per_chat=False,
        allow_reentry=True,  
        conversation_timeout=300  
    ))

    # 8. Delete Group
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("deletegroup", delete_group_start)],
        states={config.DELETING_GROUP: [CallbackQueryHandler(handle_delete_group_selection, pattern=r"^del_")]},
        fallbacks=[cancel_handler],
        name="delete_group_conversation",
        persistent=True,
        conversation_timeout=300
    ))

    # 9. License Gen (Admin)
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("genlicense", gen_license_wrapper),
            CommandHandler("createlicense", gen_license_wrapper)
        ],
        states={
            config.LIC_GET_THEME: [CallbackQueryHandler(licenses.handle_theme_selection, pattern=r"^lic_theme_")],
            config.LIC_GET_DURATION: [CallbackQueryHandler(licenses.handle_duration_selection, pattern=r"^lic_dur_")]
        },
        fallbacks=[CommandHandler("cancel", licenses.cancel)],
        name="lic_gen"
    ))

    # Theme View Handlers
    app.add_handler(CommandHandler("theme", themes.theme_command))
    app.add_handler(CallbackQueryHandler(themes.handle_theme_callback, pattern=r"^theme_"))

    # License User Commands
    app.add_handler(CommandHandler("register", licenses.register_license))
    app.add_handler(CommandHandler("check", licenses.check_license))
    app.add_handler(CommandHandler("removedomain", licenses.remove_domain))
    app.add_handler(CommandHandler("resetlicense", licenses.remove_domain))

    app.add_handler(CallbackQueryHandler(request.handle_request_tracking, pattern=r"^req_track\|"))
    app.add_handler(CallbackQueryHandler(handle_reaction, pattern=r"^react_"))
    
    app.add_handler(CommandHandler("request", partial(request.request_command_in_group, group_configs_collection=group_configs_collection), filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("request", request_in_private, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("start", start, filters=~filters.Regex(r'\/start request_')))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mygroups", my_groups))
    app.add_handler(CommandHandler("getid", get_id))
    
    app.add_handler(CallbackQueryHandler(unified_callback_query_handler))

    # --- AUTO-DELETE HANDLER ---
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, auto_delete_cleaner))

    print("🚀 Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
