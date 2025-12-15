# themes.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, ConversationHandler
from bson.objectid import ObjectId
import config
import pymongo

# --- Connect to DB ---
try:
    mongo_client = pymongo.MongoClient(config.MONGO_URI)
    db = mongo_client[config.DB_NAME]
    themes_collection = db["themes"]
except Exception as e:
    print(f"Error connecting to DB in themes.py: {e}")

# --- HELPER: Validate URL ---
def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")

# --- USER SIDE: VIEW THEMES ---

async def theme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the list of available themes from DB."""
    try: await update.message.delete()
    except: pass

    themes = list(themes_collection.find())
    
    if not themes:
        await context.bot.send_message(update.effective_chat.id, "No themes available yet.")
        return

    keyboard = []
    row = []
    for theme in themes:
        btn_data = f"theme_view_{str(theme['_id'])}"
        row.append(InlineKeyboardButton(theme['name'], callback_data=btn_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="theme_close")])
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=config.DEFAULT_THUMBNAIL, 
        caption="🎨 <b>Theme Store</b>\n\nSelect a theme below to view details and demos.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_theme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "theme_close":
        await query.message.delete()
        return

    if data == "theme_back":
        themes = list(themes_collection.find())
        keyboard = []
        row = []
        for theme in themes:
            btn_data = f"theme_view_{str(theme['_id'])}"
            row.append(InlineKeyboardButton(theme['name'], callback_data=btn_data))
            if len(row) == 2:
                keyboard.append(row); row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="theme_close")])
        
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=config.DEFAULT_THUMBNAIL, caption="🎨 <b>Theme Store</b>\n\nSelect a theme below to view details.", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            await query.message.delete()
            await context.bot.send_photo(query.message.chat.id, config.DEFAULT_THUMBNAIL, caption="🎨 <b>Theme Store</b>", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("theme_view_"):
        theme_id = data.split("_")[2]
        try:
            theme_data = themes_collection.find_one({"_id": ObjectId(theme_id)})
        except:
            theme_data = None

        if not theme_data:
            await query.answer("Theme not found.", show_alert=True)
            return

        caption = f"{theme_data['description']}"
        
        # Get URLs (defaults to google if missing to prevent crash)
        demo_url = theme_data.get('demo_url', 'https://google.com')
        doc_url = theme_data.get('doc_url', 'https://google.com')
        buy_url = theme_data.get('buy_url', 'https://google.com')
        
        # Validate again just in case
        if not is_valid_url(demo_url): demo_url = "https://google.com"
        if not is_valid_url(doc_url): doc_url = "https://google.com"
        if not is_valid_url(buy_url): buy_url = "https://google.com"

        keyboard = [
            [InlineKeyboardButton("👀 See Demo", url=demo_url), InlineKeyboardButton("🛒 Buy Theme", url=buy_url)],
            [InlineKeyboardButton("📚 Documentation", url=doc_url)],
            [InlineKeyboardButton("🔙 Back to List", callback_data="theme_back")]
        ]

        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=theme_data['image'], caption=caption, parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            await query.message.delete()
            await context.bot.send_photo(query.message.chat.id, config.DEFAULT_THUMBNAIL, caption=f"⚠️ Image failed to load.\n\n{caption}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    await query.answer()

# --- ADMIN SIDE: ADD THEME ---

async def add_theme_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("Private chat only."); return ConversationHandler.END
    
    await update.message.reply_text("➕ <b>Add New Theme</b>\n\n1️⃣ Send the **Name** of the theme.", parse_mode="HTML")
    return config.THEME_GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['theme_name'] = update.message.text
    await update.message.reply_text("2️⃣ Send the **Image URL** (Direct link .jpg/.png) or upload a Photo.")
    return config.THEME_GET_IMAGE

async def get_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['theme_image'] = file_id
    else:
        url = update.message.text.strip()
        if not is_valid_url(url):
            await update.message.reply_text("❌ Invalid URL. Must start with http/https. Try again.")
            return config.THEME_GET_IMAGE
        context.user_data['theme_image'] = url
        
    await update.message.reply_text("3️⃣ Send the **Description** (HTML supported).")
    return config.THEME_GET_DESC

async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['theme_desc'] = update.message.text_html
    await update.message.reply_text("4️⃣ Send the **Demo URL**.")
    return config.THEME_GET_DEMO

async def get_demo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_valid_url(url):
        await update.message.reply_text("❌ Invalid URL. Try again.")
        return config.THEME_GET_DEMO
        
    context.user_data['theme_demo'] = url
    await update.message.reply_text("5️⃣ Send the **Documentation URL**.")
    return config.THEME_GET_DOCS

async def get_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_valid_url(url):
        await update.message.reply_text("❌ Invalid URL. Try again.")
        return config.THEME_GET_DOCS
        
    context.user_data['theme_docs'] = url
    await update.message.reply_text("6️⃣ Send the **Buy/Download URL**.")
    return config.THEME_GET_BUY

async def save_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buy_url = update.message.text.strip()
    if not is_valid_url(buy_url):
        await update.message.reply_text("❌ Invalid URL. Try again.")
        return config.THEME_GET_BUY
    
    theme_doc = {
        "name": context.user_data['theme_name'],
        "image": context.user_data['theme_image'],
        "description": context.user_data['theme_desc'],
        "demo_url": context.user_data['theme_demo'],
        "doc_url": context.user_data['theme_docs'], # Added Docs
        "buy_url": buy_url
    }
    
    themes_collection.insert_one(theme_doc)
    await update.message.reply_text(f"✅ Theme **{theme_doc['name']}** added!", parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

# --- ADMIN SIDE: DELETE THEME ---

async def delete_theme_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private': return
    
    themes = list(themes_collection.find())
    if not themes:
        await update.message.reply_text("No themes to delete.")
        return ConversationHandler.END

    keyboard = []
    for theme in themes:
        keyboard.append([InlineKeyboardButton(f"🗑 {theme['name']}", callback_data=f"del_theme_{str(theme['_id'])}")])
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel_del")])
    
    await update.message.reply_text("Select a theme to delete:", reply_markup=InlineKeyboardMarkup(keyboard))
    return config.THEME_DELETE_CHOICE

async def handle_delete_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "cancel_del":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
        
    theme_id = data.split("_")[2]
    themes_collection.delete_one({"_id": ObjectId(theme_id)})
    
    await query.edit_message_text("✅ Theme deleted.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action canceled.")
    context.user_data.clear()
    return ConversationHandler.END
