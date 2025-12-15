import logging
import asyncio 
from datetime import datetime
import re
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import ContextTypes, ConversationHandler
import config

# --- Setup Logging ---
logger = logging.getLogger(__name__)

# --- Helper: Auto Delete Task ---
async def delete_message_delayed(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 60):
    """Waits for 'delay' seconds and then deletes the message."""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

# --- Helper function to check for admin status ---
async def is_user_chat_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Checks if a user is an administrator in a given chat."""
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return user_id in [admin.user.id for admin in admins]
    except Exception as e:
        logger.error(f"Could not check admin status in chat {chat_id}: {e}")
        return False # Fail safely

# --- Helper to create buttons ---
def get_initial_buttons(request_id, is_concern=False):
    """Generates the initial set of admin buttons for a new request."""
    keyboard = [[InlineKeyboardButton("⏳ Pending", callback_data=f"req_track|pending|{request_id}")]]
    return InlineKeyboardMarkup(keyboard)

# --- Request Conversation Handlers (User-facing) ---

async def request_command_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    group_id = update.message.chat.id
    config_doc = group_configs_collection.find_one({"_id": group_id})
    
    bot_username = (await context.bot.get_me()).username

    # 1. Delete the user's "/request" command immediately to keep chat clean
    try:
        await update.message.delete()
    except Exception:
        pass # Bot might not have delete permissions, ignore.

    # Case 1: Group is NOT configured yet
    if not config_doc:
        safe_title = update.message.chat.title.replace(' ', '-')
        deep_link = f"https://t.me/{bot_username}?start=configure_group_{group_id}_{safe_title}"
        
        keyboard = [[InlineKeyboardButton("⚙️ Configure Group (Admin Only)", url=deep_link)]]
        
        # FIX: Use send_message instead of reply_text
        msg = await context.bot.send_message(
            chat_id=group_id,
            text="⚠️ This group is not configured for requests yet.\nAdmins, please click the button below to set up the request destination.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Auto-delete warning after 2 minutes (120s)
        context.application.create_task(delete_message_delayed(context, group_id, msg.message_id, 120))
        return

    # Case 2: Group IS configured
    deep_link = f"https://t.me/{bot_username}?start=request_{group_id}"
    keyboard = [[InlineKeyboardButton("✅ Start a Request", url=deep_link)]]
    
    # FIX: Use send_message instead of reply_text because the original message is gone
    sent_msg = await context.bot.send_message(
        chat_id=group_id,
        text="Please click the button below to start your request in a private chat with me. This message will vanish in 1 minute!", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Auto-delete the bot's button message after 60 seconds
    context.application.create_task(delete_message_delayed(context, group_id, sent_msg.message_id, 60))

async def start_request_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'source_group_id' not in context.user_data:
        await update.message.reply_text(
            "It looks like this request session has expired or was started incorrectly.\n\n"
            "Please go back to the group and use the /request command to start a new request."
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🎬 New Movie/TV Request", callback_data="req_media")],
        [InlineKeyboardButton("❓ New Concern/Question", callback_data="req_concern")]
    ]
    await update.message.reply_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard))
    return config.REQ_CHOOSE_TYPE

async def choose_request_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    choice = query.data
    if choice == "req_media":
        context.user_data['is_concern'] = False
        await query.edit_message_text("Great! Please send me the poster/image for your request, or just type the title.")
        return config.REQ_GET_POSTER
    elif choice == "req_concern":
        context.user_data['is_concern'] = True
        await query.edit_message_text("Okay, please state the subject of your concern (e.g., 'Download Link').")
        return config.REQ_GET_CONCERN_SUBJECT

async def get_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['request_poster'] = update.message.photo[-1].file_id
        await update.message.reply_text("Thanks for the poster! Now, what is the title?")
        return config.REQ_GET_TITLE
    else:
        context.user_data['request_poster'] = None
        context.user_data['request_title'] = update.message.text
        await update.message.reply_text("Got it. Is it a Movie or a TV Show?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Movie", callback_data="type_movie"), InlineKeyboardButton("TV Show", callback_data="type_tv")]
        ]))
        return config.REQ_GET_MEDIA_TYPE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['request_title'] = update.message.text
    await update.message.reply_text("Thanks. Is it a Movie or a TV Show?", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Movie", callback_data="type_movie"), InlineKeyboardButton("TV Show", callback_data="type_tv")]
    ]))
    return config.REQ_GET_MEDIA_TYPE

async def get_media_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['request_media_type'] = query.data.split('_')[1]
    await query.edit_message_text("What is the release year? (e.g., 2023)")
    return config.REQ_GET_YEAR

async def get_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['request_year'] = update.message.text
    await update.message.reply_text("What is the country of origin? (e.g., USA, South Korea)")
    return config.REQ_GET_COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['request_country'] = update.message.text
    await update.message.reply_text("Any additional notes? (or type 'none')")
    return config.REQ_GET_NOTE

async def get_concern_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['concern_subject'] = update.message.text
    await update.message.reply_text("Thank you. Please send a screenshot of the issue. You can also type 'skip' if not applicable.")
    return config.REQ_GET_CONCERN_IMAGE

async def get_concern_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['request_poster'] = update.message.photo[-1].file_id
        await update.message.reply_text("Image received.")
    else:
        context.user_data['request_poster'] = None
        await update.message.reply_text("No image provided.")
    
    await update.message.reply_text("Now, please provide a detailed description of the problem.")
    return config.REQ_GET_CONCERN_DETAIL

async def get_final_detail_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    user_data = context.user_data; user = update.effective_user
    date_requested = datetime.now().strftime("%B %d, %Y")
    is_concern = user_data.get('is_concern', False)

    if not is_concern:
        user_data['request_notes'] = update.message.text
        message_text = (f"🎬 <b>New Movie/TV Request</b>\n\n"
                        f"<b>Title:</b> {user_data.get('request_title', 'N/A')}\n"
                        f"<b>Type:</b> {user_data.get('request_media_type', 'N/A').capitalize()}\n"
                        f"<b>Year:</b> {user_data.get('request_year', 'N/A')}\n"
                        f"<b>Country:</b> {user_data.get('request_country', 'N/A')}\n"
                        f"<b>Notes:</b> {user_data.get('request_notes', 'N/A')}\n\n"
                        f"<b>Requested By:</b> {user.mention_html()}\n"
                        f"<b>Date Requested:</b> {date_requested}\n"
                        f"---\n"
                        f"<b>Status:</b> ⏳ Pending")
        poster_id = user_data.get('request_poster') or random.choice(config.DEFAULT_MOVIE_THUMBNAILS)
    else:
        user_data['concern_details'] = update.message.text
        message_text = (f"❓ <b>New Concern/Question</b>\n\n"
                        f"<b>Subject:</b> {user_data.get('concern_subject', 'N/A')}\n"
                        f"<b>Details:</b> {user_data.get('concern_details', 'N/A')}\n\n"
                        f"<b>Requested By:</b> {user.mention_html()}\n"
                        f"<b>Date Requested:</b> {date_requested}\n"
                        f"---\n"
                        f"<b>Status:</b> ⏳ Pending")
        poster_id = user_data.get('request_poster') or random.choice(config.DEFAULT_CONCERN_THUMBNAILS)

    source_group_id = user_data.get('source_group_id')
    config_doc = group_configs_collection.find_one({"_id": source_group_id})
    
    if not config_doc or 'request_group_id' not in config_doc:
        await update.message.reply_text("Error: Destination channel not found for this group. Please contact an admin.")
        user_data.clear()
        return ConversationHandler.END
        
    dest_chat_id = config_doc['request_group_id']
    dest_thread_id = config_doc.get('request_thread_id')
    
    request_id = f"req_{user.id}_{update.message.message_id}"
    reply_markup = get_initial_buttons(request_id, is_concern)

    try:
        await context.bot.send_photo(
            chat_id=dest_chat_id, 
            message_thread_id=dest_thread_id, 
            photo=poster_id, 
            caption=message_text, 
            parse_mode="HTML", 
            reply_markup=reply_markup
        )
        await update.message.reply_text("✅ Your request has been successfully submitted!")
    except Exception as e:
        logger.error(f"Failed to send request to {dest_chat_id}: {e}")
        await update.message.reply_text("❌ There was an error sending your request.")
    
    user_data.clear()
    return ConversationHandler.END

# --- Admin Reply Handlers ---

async def handle_request_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not await is_user_chat_admin(context, query.message.chat_id, query.from_user.id):
        await query.answer("This action is for admins only.", show_alert=True)
        return
        
    await query.answer()
    
    _, status, request_id = query.data.split('|')
    admin_user = query.from_user
    original_caption = query.message.caption_html
    base_text = re.split(r'\n---\n', original_caption)[0]

    is_concern = "❓ <b>New Concern/Question</b>" in original_caption
    
    if status == 'pending':
        new_text = base_text + f"\n---\n<b>Status:</b> ⏳ Processed by {admin_user.mention_html()}"
        
        if is_concern:
            new_keyboard = [[
                InlineKeyboardButton("✅ Mark as Resolved", callback_data=f"req_remark|resolved|{request_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"req_remark|rejected|{request_id}")
            ]]
        else:
            new_keyboard = [[
                InlineKeyboardButton("📤 Uploading", callback_data=f"req_track|uploading|{request_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"req_remark|rejected|{request_id}")
            ]]
        
        await query.edit_message_caption(caption=new_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(new_keyboard))
    
    elif status == 'uploading' and not is_concern:
        new_text = base_text + f"\n---\n<b>Status:</b> 📤 Uploading by {admin_user.mention_html()}"
        new_keyboard = [[InlineKeyboardButton("📤 Uploading...", callback_data=f"req_track|upload_confirm|{request_id}")]]
        await query.edit_message_caption(caption=new_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(new_keyboard))
    
    elif status == 'upload_confirm' and not is_concern:
        new_text = base_text + f"\n---\n<b>Status:</b> 📤 Uploading by {admin_user.mention_html()}"
        new_keyboard = [[InlineKeyboardButton("✅ Mark as Uploaded", callback_data=f"req_remark|uploaded|{request_id}")]]
        await query.edit_message_caption(caption=new_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(new_keyboard))

# --- Admin Remark Conversation ---

async def start_remark_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await is_user_chat_admin(context, query.message.chat_id, query.from_user.id):
        await query.answer("This action is for admins only.", show_alert=True)
        return
        
    _, action, request_id = query.data.split('|')
    context.user_data.update({
        'remark_message_id': query.message.message_id,
        'remark_chat_id': query.message.chat_id,
        'remark_action': action,
        'request_id': request_id
    })
    
    prompt = (f"Please provide your remarks for the request.\n\n"
              f"<b>Format with Link:</b>\n<code>Remarks text | Button Text | https://link.com</code>\n\n"
              f"<b>Format without Link:</b>\n<code>Your remarks here</code>\n\n"
              f"Send /cancel to abort.")
    
    try:
        await query.answer("Check your private messages to add remarks.", show_alert=True)
        await context.bot.send_message(chat_id=query.from_user.id, text=prompt, parse_mode="HTML")
    except error.Forbidden:
        await query.answer("Could not send you a PM. Please start a chat with me first and try again.", show_alert=True)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error starting remark conversation for admin {query.from_user.id}: {e}")
        await query.answer("An error occurred. Could not start remark process.", show_alert=True)
        return ConversationHandler.END
        
    return config.AWAITING_REMARK

async def handle_admin_remark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remark_input = update.message.text
    admin_user = update.effective_user
    chat_id = context.user_data['remark_chat_id']
    message_id = context.user_data['remark_message_id']
    action = context.user_data['remark_action']
    
    remark_parts = [part.strip() for part in remark_input.split('|')]
    remark_text = remark_parts[0]
    new_button = None
    if len(remark_parts) == 3:
        new_button = InlineKeyboardButton(remark_parts[1], url=remark_parts[2])

    try:
        original_message = await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        original_caption = original_message.caption_html
        base_text = re.split(r'\n---\n', original_caption)[0]
        date_resolved = datetime.now().strftime("%B %d, %Y")

        status_icons = {"uploaded": "✅", "resolved": "✅", "rejected": "❌", "exists": "🤔"}
        status_text = f"{status_icons.get(action, '')} {action.capitalize()} by {admin_user.mention_html()}"
        
        date_label = "Date Resolved"
        if action == 'uploaded':
            date_label = "Date Uploaded"
        
        new_caption = (f"{base_text}\n---\n"
                       f"<b>Status:</b> {status_text}\n"
                       f"<b>{date_label}:</b> {date_resolved}\n\n"
                       f"<b>Remarks:</b>\n<i>{remark_text}</i>")
        
        final_buttons_row = [InlineKeyboardButton(f"{status_icons.get(action, '')} {action.capitalize()}", callback_data="ignore")]
        if new_button:
            final_buttons_row.append(new_button)
        reply_markup = InlineKeyboardMarkup([final_buttons_row])

        await context.bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=new_caption, parse_mode="HTML", reply_markup=reply_markup)
            
        await update.message.reply_text("✅ Remark added and request updated successfully.")
        
        try:
            user_id = int(context.user_data['request_id'].split('_')[1])

            title_match = re.search(r"<b>Title:</b>\s*(.*?)\n", original_caption, re.IGNORECASE)
            subject_match = re.search(r"<b>Subject:</b>\s*(.*?)\n", original_caption, re.IGNORECASE)
            request_item = ""
            if title_match:
                request_item = f'"{title_match.group(1)}"'
            elif subject_match:
                request_item = f'"{subject_match.group(1)}"'
            else:
                request_item = "your request"

            notification_text = ""
            if action == 'uploaded':
                notification_text = f'🎉 Good news! Your request for {request_item} has been fulfilled.\n\n'
            elif action == 'resolved':
                notification_text = f'✅ Your concern regarding {request_item} has been resolved.\n\n'
            elif action == 'rejected':
                notification_text = f'ℹ️ An update on your request for {request_item}: it has been rejected.\n\n'

            notification_text += f"<b>Admin Remarks:</b>\n<i>{remark_text}</i>"
            notification_reply_markup = None
            if new_button:
                notification_text += "\n\nFollow the link below."
                notification_reply_markup = InlineKeyboardMarkup([[new_button]])
            
            await context.bot.send_message(
                chat_id=user_id, 
                text=notification_text,
                parse_mode="HTML",
                reply_markup=notification_reply_markup
            )
        except Exception as e:
            logger.warning(f"Could not notify user about request update: {e}")

    except Exception as e:
        logger.error(f"Error adding remark: {e}")
        await update.message.reply_text("❌ Could not add remark.")
        
    context.user_data.clear()
    return ConversationHandler.END
