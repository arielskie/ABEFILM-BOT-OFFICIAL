# admin.py

from telegram import Update
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
    context.user_data['admin_id'] = user.id

    await update.message.reply_text(
        f"Okay, we are setting up the request system for **{source_group_title}**.\n\n"
        "Now, please **forward any message from the channel (or specific Group Topic) where the formatted requests should be sent**.\n\n"
        "Remember to add me as an admin there first!",
        parse_mode="HTML"
    )
    return config.AWAITING_DEST_GROUP_FOR_CONFIG

async def handle_dest_group_and_save_config(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    """
    Receives the forwarded message. Detects if it's a Forum/Topic group.
    """
    source_group_id = context.user_data.get('source_group_id_to_set')
    
    if not source_group_id:
        await update.message.reply_text("An error occurred. Please restart the configuration from your group.")
        return ConversationHandler.END

    if not update.message.forward_origin:
        await update.message.reply_text("That is not a forwarded message. Please forward a message from your request channel, or send /cancel.")
        return config.AWAITING_DEST_GROUP_FOR_CONFIG

    dest_chat = update.message.forward_origin.chat
    dest_group_id = dest_chat.id
    dest_group_title = dest_chat.title

    # 1. Verify the bot has permissions in the destination channel/group
    is_ok, error_message = await broadcast.check_bot_permissions(context, dest_group_id)
    if not is_ok:
        await update.message.reply_text(f"❌ <b>Permission Error in {dest_group_title}:</b> {error_message}\n\nPlease fix the permissions and try again.", parse_mode="HTML")
        return config.AWAITING_DEST_GROUP_FOR_CONFIG

    # 2. Check if the destination is a Forum (has Topics)
    try:
        full_chat = await context.bot.get_chat(dest_group_id)
        if full_chat.is_forum:
            # Save temporary data
            context.user_data['dest_group_id_pending'] = dest_group_id
            context.user_data['dest_group_title_pending'] = dest_group_title
            
            await update.message.reply_text(
                f"⚠️ **Topic Support Detected**\n\n"
                f"The group **{dest_group_title}** has Topics enabled.\n\n"
                "Please reply with the **Topic ID** (Thread ID) where you want requests to appear.\n"
                "• Send <code>0</code> for the 'General' topic.\n"
                "• <i>Tip: Copy the link to a message in the specific topic (e.g., t.me/c/xx/123). The ID is the last number (123).</i>",
                parse_mode="HTML"
            )
            return config.AWAITING_DEST_TOPIC_ID
    except Exception as e:
        print(f"Error checking forum status: {e}")

    # 3. If not a forum, save directly (Thread ID is None)
    save_configuration(context, group_configs_collection, source_group_id, dest_group_id, dest_group_title, None)

    await update.message.reply_text(
        f"✅ **Success!**\n\n"
        f"Requests from **{context.user_data.get('source_group_title_to_set')}** will now be sent to **{dest_group_title}**.",
        parse_mode="HTML"
    )
    
    await notify_source_group(context, source_group_id, update.effective_user)
    context.user_data.clear()
    return ConversationHandler.END

async def handle_dest_topic_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, group_configs_collection):
    """
    Handles the manual input of a Topic ID if the group is a Forum.
    """
    topic_input = update.message.text.strip()
    source_group_id = context.user_data.get('source_group_id_to_set')
    dest_group_id = context.user_data.get('dest_group_id_pending')
    dest_group_title = context.user_data.get('dest_group_title_pending')

    if not topic_input.isdigit():
        await update.message.reply_text("❌ Please enter a numeric Topic ID (e.g., 2, 53, or 0 for General).")
        return config.AWAITING_DEST_TOPIC_ID

    thread_id = int(topic_input)
    if thread_id == 0:
        thread_id = None  # 0 means General/Main thread

    # Save with the Thread ID
    save_configuration(context, group_configs_collection, source_group_id, dest_group_id, dest_group_title, thread_id)

    topic_info = f" (Topic ID: {thread_id})" if thread_id else " (General Topic)"
    await update.message.reply_text(
        f"✅ **Success!**\n\n"
        f"Requests from **{context.user_data.get('source_group_title_to_set')}** will now be sent to **{dest_group_title}**{topic_info}.",
        parse_mode="HTML"
    )

    await notify_source_group(context, source_group_id, update.effective_user)
    context.user_data.clear()
    return ConversationHandler.END

# --- HELPER FUNCTIONS ---

def save_configuration(context, collection, source_id, dest_id, dest_title, thread_id):
    """
    Saves the config to MongoDB.
    """
    update_data = {
        "request_group_id": dest_id,
        "request_group_title": dest_title,
        "admin_id": context.user_data.get('admin_id'),
        "request_thread_id": thread_id  # Crucial for Topics
    }
    
    collection.update_one(
        {"_id": source_id},
        {"$set": update_data},
        upsert=True
    )

async def notify_source_group(context, source_id, user):
    """
    Sends a confirmation message to the original group.
    """
    try:
        await context.bot.send_message(
            chat_id=source_id,
            text=f"✅ The request system has been successfully configured for this group by {user.mention_html()}.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Could not send confirmation message to group {source_id}: {e}")
