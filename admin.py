# admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import broadcast
import config

# --- HELPER: Checks if a user is an admin in a chat ---
async def is_user_chat_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return user_id in [admin.user.id for admin in admins]
    except Exception as e:
        print(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

# --- PROACTIVE CONFIGURATION CONVERSATION ---

async def start_proactive_configuration(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    """
    This is triggered when an admin clicks the 'Configure' button from a group.
    The source group info is passed via the /start command's arguments.
    """
    user = update.effective_user
    
    # Extract group info from the deep link (e.g., /start configure_group_-12345_Group_Title)
    try:
        parts = context.args[0].split('_', 2)
        source_group_id = int(parts[1])
        source_group_title = parts[2].replace('-', ' ') # Restore spaces in title
    except (IndexError, ValueError):
        await update.message.reply_text("This configuration link seems to be invalid. Please try again from your group.")
        return ConversationHandler.END

    # Security Check: Verify the user clicking the link is ACTUALLY an admin of that group
    if not await is_user_chat_admin(context, source_group_id, user.id):
        await update.message.reply_text(f"You must be an admin of **{source_group_title}** to configure it.", parse_mode="HTML")
        return ConversationHandler.END

    # Store the validated information
    context.user_data['source_group_id_to_set'] = source_group_id
    context.user_data['source_group_title_to_set'] = source_group_title

    await update.message.reply_text(
        f"Okay, we are setting up the request system for **{source_group_title}**.\n\n"
        "Now, please **forward any message from the channel where the formatted requests should be sent**.\n\n"
        "Remember to add me as an admin there first!",
        parse_mode="HTML"
    )
    return config.AWAITING_DEST_GROUP_FOR_CONFIG

async def handle_dest_group_and_save_config(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    """
    Receives the forwarded message from the destination channel and saves the complete configuration.
    """
    source_group_id = context.user_data.get('source_group_id_to_set')
    source_group_title = context.user_data.get('source_group_title_to_set')
    
    if not source_group_id:
        await update.message.reply_text("An error occurred. Please restart the configuration from your group.")
        return ConversationHandler.END

    if not update.message.forward_origin:
        await update.message.reply_text("That is not a forwarded message. Please forward a message from your request channel, or send /cancel.")
        return config.AWAITING_DEST_GROUP_FOR_CONFIG

    dest_chat = update.message.forward_origin.chat
    dest_group_id = dest_chat.id
    dest_group_title = dest_chat.title

    # Verify the bot has permissions in the destination channel
    is_ok, error_message = await broadcast.check_bot_permissions(context, dest_group_id)
    if not is_ok:
        await update.message.reply_text(f"❌ <b>Permission Error in {dest_group_title}:</b> {error_message}\n\nPlease fix the permissions and try again.", parse_mode="HTML")
        return config.AWAITING_DEST_GROUP_FOR_CONFIG
        
    # All checks passed, save the mapping
    group_configs_collection.update_one(
        {"_id": source_group_id},
        {
            "$set": {
                "request_group_id": dest_group_id,
                "request_group_title": dest_group_title,
                "admin_id": update.effective_user.id
            }
        },
        upsert=True
    )

    await update.message.reply_text(
        f"✅ **Success!**\n\n"
        f"Requests from **{source_group_title}** will now be sent to **{dest_group_title}**.",
        parse_mode="HTML"
    )
    
    # Notify the original group that setup is complete
    try:
        await context.bot.send_message(
            chat_id=source_group_id,
            text=f"✅ The request system has been successfully configured for this group by {update.effective_user.mention_html()}.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Could not send confirmation message to group {source_group_id}: {e}")

    context.user_data.clear()
    return ConversationHandler.END
