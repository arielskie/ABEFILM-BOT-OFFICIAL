import random
import string
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from supabase import create_client, Client
import config

# --- Connect to Supabase ---
try:
    supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
except Exception as e:
    print(f"Error connecting to Supabase: {e}")

# --- HELPER: Generate Random Key ---
def generate_key():
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"LIC-{part1}-{part2}"

# --- ADMIN: GENERATE LICENSE CONVERSATION ---

async def start_gen_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Hardcoded theme list
    keyboard = [
        [InlineKeyboardButton("Abeflix", callback_data="lic_theme_Abeflix")],
        [InlineKeyboardButton("Moviebox", callback_data="lic_theme_Moviebox")],
        [InlineKeyboardButton("IQone", callback_data="lic_theme_IQone")],
        [InlineKeyboardButton("IQplay", callback_data="lic_theme_IQplay")],
        [InlineKeyboardButton("Abefilm v4", callback_data="lic_theme_Abefilmv4")]
    ]
    await update.message.reply_text("🔑 <b>License Generator</b>\n\nSelect the Theme:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return config.LIC_GET_THEME

async def handle_theme_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    theme_name = query.data.split("lic_theme_")[1]
    context.user_data['lic_theme'] = theme_name
    
    keyboard = [
        [InlineKeyboardButton("Forever", callback_data="lic_dur_forever")],
        [InlineKeyboardButton("1 Year", callback_data="lic_dur_365")],
        [InlineKeyboardButton("1 Month", callback_data="lic_dur_30")],
        [InlineKeyboardButton("7 Days Trial", callback_data="lic_dur_7")]
    ]
    await query.edit_message_text(f"Theme: <b>{theme_name}</b>\n\nSelect Duration:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return config.LIC_GET_DURATION

async def handle_duration_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    duration_code = query.data.split("lic_dur_")[1]
    theme_name = context.user_data.get('lic_theme', 'Unknown Theme')
    
    expiry_date = "2099-12-31" 
    status_val = "forever"
    
    if duration_code != "forever":
        days = int(duration_code)
        expire_dt = datetime.datetime.now() + datetime.timedelta(days=days)
        expiry_date = expire_dt.strftime("%Y-%m-%d")
        status_val = "trial" if days < 30 else "active"

    license_key = generate_key()
    
    data = {
        "license_key": license_key,
        "theme_name": theme_name,
        "expiry_date": expiry_date,
        "status": status_val
    }
    
    try:
        supabase.table("licenses").insert(data).execute()
        
        msg = (
            f"✅ <b>License Created Successfully!</b>\n\n"
            f"🔑 <b>Key:</b> <code>{license_key}</code>\n"
            f"🎨 <b>Theme:</b> {theme_name}\n"
            f"⏳ <b>Expires:</b> {expiry_date}\n\n"
            f"<i>Click the key to copy.</i>"
        )
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception as e:
        await query.edit_message_text(f"❌ Error saving to Supabase: {e}")

    context.user_data.clear()
    return ConversationHandler.END

# --- USER COMMANDS ---

async def register_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Deletes the user command to keep chat clean
    try: await update.message.delete()
    except: pass

    args = context.args
    if len(args) != 2:
        await context.bot.send_message(update.effective_user.id, "⚠️ Usage: `/register <LICENSE_KEY> <DOMAIN>`", parse_mode="Markdown")
        return

    key = args[0].strip()
    domain = args[1].strip().replace("https://", "").replace("http://", "").replace("/", "")

    try:
        response = supabase.table("licenses").select("*").eq("license_key", key).execute()
        if not response.data:
            await context.bot.send_message(update.effective_user.id, "❌ License not found.")
            return
            
        lic_data = response.data[0]

        if lic_data.get("domain"):
            if lic_data["domain"] == domain:
                 await context.bot.send_message(update.effective_user.id, f"✅ Already registered to {domain}.")
                 return
            else:
                 await context.bot.send_message(update.effective_user.id, f"❌ License active on: {lic_data['domain']}")
                 return

        supabase.table("licenses").update({"domain": domain}).eq("license_key", key).execute()
        await context.bot.send_message(update.effective_user.id, f"✅ <b>Success!</b>\nDomain: <code>{domain}</code>\nTheme: {lic_data['theme_name']}", parse_mode="HTML")
        
    except Exception as e:
        await context.bot.send_message(update.effective_user.id, f"❌ Database Error: {e}")

async def check_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

    if not context.args:
        await context.bot.send_message(update.effective_user.id, "Usage: `/check <LICENSE_KEY>`", parse_mode="Markdown")
        return
        
    key = context.args[0].strip()
    
    try:
        response = supabase.table("licenses").select("*").eq("license_key", key).execute()
        
        if not response.data:
            await context.bot.send_message(update.effective_user.id, "❌ License not found.")
            return
            
        lic_data = response.data[0]
        
        msg = (
            f"🔍 <b>License Details</b>\n\n"
            f"<b>Theme:</b> {lic_data['theme_name']}\n"
            f"<b>Domain:</b> {lic_data.get('domain') or 'Not Registered'}\n"
            f"<b>Expires:</b> {lic_data.get('expiry_date')}\n"
            f"<b>Status:</b> {lic_data.get('status')}"
        )
        await context.bot.send_message(update.effective_user.id, msg, parse_mode="HTML")
        
    except Exception as e:
        await context.bot.send_message(update.effective_user.id, f"Error: {e}")

async def remove_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

    if not context.args:
        await context.bot.send_message(update.effective_user.id, "Usage: `/removedomain <LICENSE_KEY>`", parse_mode="Markdown")
        return
        
    key = context.args[0].strip()
    
    try:
        response = supabase.table("licenses").select("*").eq("license_key", key).execute()
        if not response.data:
            await context.bot.send_message(update.effective_user.id, "❌ License not found.")
            return
        
        lic_data = response.data[0]
        if not lic_data.get("domain"):
             await context.bot.send_message(update.effective_user.id, "ℹ️ No domain registered yet.")
             return

        supabase.table("licenses").update({"domain": None}).eq("license_key", key).execute()
        
        await context.bot.send_message(update.effective_user.id, "✅ Domain removed. You can register a new one now.")
        
    except Exception as e:
         await context.bot.send_message(update.effective_user.id, f"Error: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action canceled.")
    return ConversationHandler.END
