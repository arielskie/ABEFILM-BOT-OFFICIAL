import collections
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest
from telegram.constants import ChatType
import config

# --- Setup Logging ---
logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def check_bot_permissions(context: ContextTypes.DEFAULT_TYPE, chat_id):
    try:
        chat = await context.bot.get_chat(chat_id)
        bot_id = context.bot.id
        member = await context.bot.get_chat_member(chat_id, bot_id)

        if member.status != 'administrator':
            return False, "I am not an admin in the target chat."

        if chat.type == ChatType.CHANNEL:
            if member.can_post_messages:
                return True, None
            else:
                return False, "I am an admin in the channel, but I don't have the 'Post Messages' permission."

        elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return True, None
            
        return False, f"Broadcasting to this chat type ({chat.type}) is not supported."

    except BadRequest as e:
        if "chat not found" in e.message.lower():
            return False, "I could not find the chat. Make sure the ID/username is correct and I have been added."
        return False, f"A Telegram error occurred: {e.message}"
    except Exception as e:
        logger.error(f"Unexpected error in check_bot_permissions for chat {chat_id}: {e}")
        return False, f"An unexpected error occurred: {e}"

def build_keyboard(doc):
    final_keyboard = []
    
    # 1. Add Reactions Row
    reaction_keyboard = []
    reaction_emojis = doc.get("reaction_emojis", [])
    if reaction_emojis:
        reactions = doc.get("reactions", {})
        counts = collections.Counter(reactions.values())
        for emoji in reaction_emojis:
            count = counts.get(emoji, 0)
            callback_data = f"react_{doc['_id']}_{emoji}"
            reaction_keyboard.append(InlineKeyboardButton(f"{emoji} {count}", callback_data=callback_data))
    if reaction_keyboard:
        final_keyboard.append(reaction_keyboard)
        
    # 2. Add URL Buttons Row(s)
    buttons_raw = doc.get("buttons_raw", "")
    if buttons_raw and buttons_raw.lower().strip() != 'none':
        # Split into rows by newline
        rows = buttons_raw.strip().split('\n')
        for row_str in rows:
            button_row = []
            # Split buttons in the same row by '|'
            button_parts = row_str.split('|')
            
            for part in button_parts:
                name = None
                link = None
                part = part.strip()
                
                # Check for "Name - Link" format
                if ' - ' in part:
                    split_data = part.split(' - ', 1)
                    name = split_data[0].strip()
                    link = split_data[1].strip()
                # Check for "Name: Link" format
                elif ': ' in part:
                    split_data = part.split(': ', 1)
                    name = split_data[0].strip()
                    link = split_data[1].strip()
                
                # Validation
                if name and link:
                    button_row.append(InlineKeyboardButton(name, url=link))
            
            if button_row:
                final_keyboard.append(button_row)
                
    return final_keyboard

# --- Broadcast Handlers ---

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("This command can only be used in a private chat with me.")
        return ConversationHandler.END
    await update.message.reply_text("Starting a new broadcast...\n\nStep 1: Please send the <b>thumbnail</b> for the post.", parse_mode="HTML")
    return config.GET_THUMBNAIL

async def get_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return config.GET_THUMBNAIL
    context.user_data['broadcast_photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Step 2: Send the <b>title</b>.", parse_mode="HTML")
    return config.GET_TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_title'] = update.message.text
    await update.message.reply_text("Step 3: Send the <b>description</b>. HTML is supported.", parse_mode="HTML")
    return config.GET_DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_description'] = update.message.text_html
    await update.message.reply_text(
        "Step 4: Send the <b>URL buttons</b>.\n\n"
        "<i>Use a new line for each row, and `|` to separate buttons on the same row.</i>\n\n"
        "<u>Supported Formats:</u>\n"
        "1. <code>Button Name - https://link.com</code>\n"
        "2. <code>Button Name: https://link.com</code>\n\n"
        "Type <code>none</code> to skip.",
        parse_mode="HTML", disable_web_page_preview=True
    )
    return config.GET_BUTTONS

async def get_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_buttons_raw'] = update.message.text
    await update.message.reply_text("Step 5: Send up to 3 <b>reaction emojis</b>, separated by spaces (e.g., 👍 ❤️ 😂). Or type <code>none</code> to skip.", parse_mode="HTML")
    return config.GET_REACTIONS

async def get_reactions_and_choose_target(update: Update, context: ContextTypes.DEFAULT_TYPE, user_collection):
    context.user_data['broadcast_reactions_raw'] = update.message.text
    user_db_data = user_collection.find_one({"user_id": update.effective_user.id})
    saved_groups = user_db_data.get("broadcast_groups", []) if user_db_data else []
    
    keyboard = []
    for g in saved_groups:
        title = g['title']
        if g.get('thread_id'):
            title += f" [Topic: {g.get('thread_id')}]"
        
        t_id_safe = g.get('thread_id') if g.get('thread_id') else 0
        callback_data = f"bcast_{g['id']}_{t_id_safe}"
        keyboard.append([InlineKeyboardButton(title, callback_data=callback_data)])
        
    keyboard.append([InlineKeyboardButton("➡️ Send to a different ID", callback_data="bcast_new")])
    
    await update.message.reply_text("Final Step: Choose a target:", reply_markup=InlineKeyboardMarkup(keyboard))
    return config.CHOOSE_TARGET

async def handle_target_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, user_collection, broadcasts_collection):
    query = update.callback_query
    message = update.message
    target_chat_id = None
    target_thread_id = None
    
    if query:
        await query.answer()
        if query.data == "bcast_new":
            await query.edit_message_text("Please send the new Chat ID (e.g., -100xxx_TopicID).")
            return config.CHOOSE_TARGET
        else:
            # FIX: Extract ID and Thread from the button data
            # Format: bcast_-100123_4493
            parts = query.data.split("_")
            
            target_chat_id = parts[1]
            t_id = int(parts[2])
            target_thread_id = t_id if t_id != 0 else None
            
            await query.edit_message_text(f"Sending to <code>{target_chat_id}</code> (Topic: {target_thread_id})...", parse_mode="HTML")
            
    elif message:
        raw_text = message.text.strip()
        # Handle manual entry: -100123456_4493
        if "_" in raw_text:
            try:
                parts = raw_text.split("_")
                target_chat_id = parts[0]
                target_thread_id = int(parts[1])
            except ValueError:
                await message.reply_text("Invalid format. Use ChatID_TopicID")
                return config.CHOOSE_TARGET
        else:
            target_chat_id = raw_text
            
        await message.reply_text(f"Sending to <code>{target_chat_id}</code>...", parse_mode="HTML")

    if target_chat_id:
        await send_broadcast(update, context, target_chat_id, user_collection, broadcasts_collection, target_thread_id)
        return ConversationHandler.END
        
    return config.CHOOSE_TARGET

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, target_chat_id, user_collection, broadcasts_collection, message_thread_id=None):
    effective_chat_id = update.effective_chat.id
    
    is_ok, error_message = await check_bot_permissions(context, target_chat_id)
    if not is_ok:
        await context.bot.send_message(effective_chat_id, f"❌ Broadcast failed: {error_message}")
        context.user_data.clear()
        return ConversationHandler.END
        
    try:
        reactions_raw = context.user_data.get('broadcast_reactions_raw', '')
        reaction_emojis = reactions_raw.strip().split()[:3] if reactions_raw.lower().strip() != 'none' else []
        
        broadcast_doc = {
            "author_user_id": update.effective_user.id,
            "reactions": {},
            "reaction_emojis": reaction_emojis,
            "target_chat_id": target_chat_id,
            "target_thread_id": message_thread_id,
            "title": context.user_data.get('broadcast_title'),
            "description": context.user_data.get('broadcast_description'),
            "photo": context.user_data.get('broadcast_photo'),
            "buttons_raw": context.user_data.get('broadcast_buttons_raw')
        }
        
        insert_result = broadcasts_collection.insert_one(broadcast_doc)
        broadcast_id = insert_result.inserted_id
        
        doc_with_id = broadcasts_collection.find_one({"_id": broadcast_id})
        final_keyboard_list = build_keyboard(doc_with_id)
        reply_markup = InlineKeyboardMarkup(final_keyboard_list) if final_keyboard_list else None
        
        caption = f"<b>{broadcast_doc['title']}</b>\n\n{broadcast_doc['description']}"
        
        sent_message = await context.bot.send_photo(
            chat_id=target_chat_id,
            message_thread_id=message_thread_id, 
            photo=broadcast_doc['photo'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        broadcasts_collection.update_one({"_id": broadcast_id}, {"$set": {"telegram_message_id": sent_message.message_id}})
        
        location_msg = f" (Topic ID: {message_thread_id})" if message_thread_id else ""
        await context.bot.send_message(effective_chat_id, f"✅ Broadcast sent!{location_msg}")
    
    except Exception as e:
        logger.error(f"Error in send_broadcast for chat {target_chat_id}: {e}")
        await context.bot.send_message(effective_chat_id, f"❌ Broadcast failed: {e}")
    
    finally:
        context.user_data.clear()
        return ConversationHandler.END
