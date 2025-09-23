import collections
import io
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest

import config
from search import get_details, get_best_backdrop_path

# --- Helper Functions ---

def get_content_rating(tmdb_id, media_type):
    import requests
    try:
        if media_type == 'movie':
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/release_dates"
            response = requests.get(url, params={"api_key": config.TMDB_API_KEY}).json()
            for result in response.get("results", []):
                if result.get("iso_3166_1") == "US": return result.get("release_dates", [{}])[0].get("certification")
        elif media_type == 'tv':
            url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/content_ratings"
            response = requests.get(url, params={"api_key": config.TMDB_API_KEY}).json()
            for result in response.get("results", []):
                if result.get("iso_3166_1") == "US": return result.get("rating")
    except Exception as e: print(f"Error fetching content rating: {e}")
    return None

def generate_post_code(user_id, tmdb_id, media_type, user_collection, default_sources, season=1, num_episodes=8):
    user_data = user_collection.find_one({"user_id": user_id})
    user_sources = user_data.get("video_sources", []) if user_data else []
    all_sources = default_sources + user_sources
    toggled_sources = user_data.get("toggled_sources", {}) if user_data else {}
    active_sources = [s for s in all_sources if toggled_sources.get(s['name'], True)]
    details, credits = get_details(tmdb_id, media_type)
    labels = ["TV Series" if media_type == 'tv' else "Movie"]
    if details.get("genres"): labels.extend([genre['name'] for genre in details["genres"]])
    rating = get_content_rating(tmdb_id, media_type)
    if rating: labels.append(f"z{rating}")
    year = (details.get('release_date') or details.get('first_air_date') or '')[:4]
    if year: labels.append(f"zYear:{year}")
    if media_type == 'movie' and details.get("runtime"): labels.append(f"zDuration:{details['runtime']}min")
    if details.get("status"): labels.append(f"z{details['status']}")
    country = (details["production_countries"][0].get("iso_3166_1") if media_type == 'movie' and details.get("production_countries") else (details["origin_country"][0] if media_type == 'tv' and details.get("origin_country") else None))
    if country: labels.append(f"zCountry:{country}")
    label_string = ",".join(labels) + ","
    poster = f"https://image.tmdb.org/t/p/w500{details.get('poster_path') or ''}"
    backdrop_path = get_best_backdrop_path(tmdb_id, media_type) or details.get('backdrop_path')
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else ""
    overview = details.get("overview", "No overview available."); post_id = details.get("id")
    cast = credits.get("cast", [])[:8]
    celebrities = [{"name": c.get("name"), "photo": f"https://image.tmdb.org/t/p/w185{c['profile_path']}", "title": c.get("character", "")} for c in cast if c.get("profile_path")]
    if media_type == 'movie':
        videos_dict = {source['name']: source['movie_url'].format(tmdb_id=tmdb_id) for source in active_sources}
        episodes = [{"episode": "01", "thumb": "", "videos": videos_dict}]
        downloads = [{"source": "Vidsrc.vip", "quality": "Auto", "size": "-", "url": f"https://dl.vidsrc.vip/movie/{tmdb_id}"}]
    else:
        episodes = []
        for ep in range(1, num_episodes + 1):
            videos_dict = {source['name']: source['tv_url'].format(tmdb_id=tmdb_id, season=season, episode=ep) for source in active_sources}
            episodes.append({"episode": f"{ep:02}", "thumb": "", "videos": videos_dict})
        downloads = [{"source": f"Vidsrc.vip Ep{ep}", "quality": "Multiquality", "size": "-", "url": f"https://dl.vidsrc.vip/tv/{tmdb_id}/{season}/{ep}"} for ep in range(1, num_episodes + 1)]
    episodes_json, downloads_json, celebrities_json = (json.dumps(d, indent=2, ensure_ascii=False) for d in [episodes, downloads, celebrities])
    html_code = (f'<div>\n  <span id="post-id" data-post-id="{post_id}"></span>\n  <img alt="poster" src="{poster}" />\n'
               f'  <iframe class="lazyloaded" data-src="/" src="/" allowfullscreen="true"></iframe>\n  <p>{overview}</p>\n'
               f'  <script>\n    const defaultThumbnail = \'{backdrop_url}\';\n    const episodes = {episodes_json};\n'
               f'    const downloads = {downloads_json};\n    const celebrities = {celebrities_json};\n  </script>\n</div>')
    return html_code, label_string

def generate_copyable_description(tmdb_id, media_type):
    details, _ = get_details(tmdb_id, media_type); lines = []
    status = details.get("status"); media_tag = "Movie" if media_type == 'movie' else "TVSeries"
    lines.append(f"<b>#{media_tag} #{status.replace(' ', '')}</b>" if status else f"<b>#{media_tag}</b>"); lines.append("")
    if details.get("genres"): lines.append(f'🔸 <b>Genre:</b> {", ".join([g["name"] for g in details["genres"]])}')
    rating = get_content_rating(tmdb_id, media_type)
    if rating: lines.append(f"🔸 <b>Rated:</b> {rating}")
    country = (details["production_countries"][0].get("iso_3166_1") if media_type == 'movie' and details.get("production_countries") else (details["origin_country"][0] if media_type == 'tv' and details.get("origin_country") else None))
    if country: lines.append(f"🔸 <b>Country:</b> {country}")
    if details.get("vote_average") and details["vote_average"] > 0: lines.append(f'🔸 <b>Rating:</b> {round(details["vote_average"], 1)}/10')
    lines.append("")
    if details.get("overview"): lines.append("<b>Overview:</b>"); lines.append(f'<blockquote>{details["overview"]}</blockquote>')
    return "\n".join(lines)

async def check_bot_permissions(context: ContextTypes.DEFAULT_TYPE, chat_id):
    try:
        bot_id = context.bot.id
        member = await context.bot.get_chat_member(chat_id, bot_id)
        if member.status == 'administrator' and member.can_post_messages:
            return True, None
        elif member.status != 'administrator':
            return False, "I am not an admin in the target channel."
        else:
            return False, "I am an admin, but I don't have permission to post messages."
    except BadRequest as e:
        if "chat not found" in e.message.lower():
            return False, "I could not find the channel. Make sure I have been added to it."
        return False, f"A Telegram error occurred: {e.message}"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"

def build_keyboard(doc):
    final_keyboard = []; reaction_keyboard = []
    reaction_emojis = doc.get("reaction_emojis", [])
    if reaction_emojis:
        reactions = doc.get("reactions", {}); counts = collections.Counter(reactions.values())
        for emoji in reaction_emojis:
            count = counts.get(emoji, 0); callback_data = f"react_{doc['_id']}_{emoji}"
            reaction_keyboard.append(InlineKeyboardButton(f"{emoji} {count}", callback_data=callback_data))
    if reaction_keyboard: final_keyboard.append(reaction_keyboard)
    buttons_raw = doc.get("buttons_raw", "none")
    if buttons_raw.lower().strip() != 'none':
        for line in buttons_raw.strip().split('\n'):
            button_row = []; button_parts = line.split('|')
            for part in button_parts:
                sub_parts = part.split(' - ')
                if len(sub_parts) == 2: button_row.append(InlineKeyboardButton(sub_parts[0].strip(), url=sub_parts[1].strip()))
            if button_row: final_keyboard.append(button_row)
    return final_keyboard

# --- Broadcast Handlers ---

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("This command can only be used in a private chat with me.")
        return ConversationHandler.END
    await update.message.reply_text("Starting a new broadcast...\n\nStep 1: Please send the <b>thumbnail</b> for the post.", parse_mode="HTML")
    return config.GET_THUMBNAIL

async def get_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Step 2: Send the <b>title</b>.", parse_mode="HTML")
    return config.GET_TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_title'] = update.message.text
    if 'copied_description' in context.user_data:
        context.user_data['broadcast_description'] = context.user_data.pop('copied_description')
        await update.message.reply_text(
            "✅ Using your copied description.\n\nStep 4: Send the <b>URL buttons</b>.\n\n"
            "<i>Use a new line for each row, and `|` to separate buttons on the same row.</i>\n\n"
            "<u>Example:</u>\n<code>Watch Now - https://... | Trailer - https://...</code>\n"
            "<code>Our Website - https://...</code>",
            parse_mode="HTML", disable_web_page_preview=True
        )
        return config.GET_BUTTONS
    else:
        await update.message.reply_text("Step 3: Send the <b>description</b>. HTML is supported.", parse_mode="HTML")
        return config.GET_DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_description'] = update.message.text
    await update.message.reply_text(
        "Step 4: Send the <b>URL buttons</b>.\n\n"
        "<i>Use a new line for each row, and `|` to separate buttons on the same row.</i>\n\n"
        "<u>Example:</u>\n<code>Watch Now - https://... | Trailer - https://...</code>\n"
        "<code>Our Website - https://...</code>",
        parse_mode="HTML", disable_web_page_preview=True
    )
    return config.GET_BUTTONS

async def get_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_buttons_raw'] = update.message.text
    await update.message.reply_text("Step 5: Send up to 3 <b>reaction emojis</b>, separated by spaces (e.g., 👍 ❤️ 😂). Or type 'none'.")
    return config.GET_REACTIONS

async def get_reactions_and_choose_target(update: Update, context: ContextTypes.DEFAULT_TYPE, user_collection):
    context.user_data['broadcast_reactions_raw'] = update.message.text
    user_db_data = user_collection.find_one({"user_id": update.effective_user.id})
    saved_groups = user_db_data.get("broadcast_groups", []) if user_db_data else []
    if not saved_groups:
        await update.message.reply_text("Final Step: Send the target Chat ID (e.g., @yourchannel or -100...).")
        return config.CHOOSE_TARGET
    keyboard = [[InlineKeyboardButton(g['title'], callback_data=f"bcast_{g['id']}")] for g in saved_groups] + [[InlineKeyboardButton("➡️ Send to a different ID", callback_data="bcast_new")]]
    await update.message.reply_text("Final Step: Choose a target:", reply_markup=InlineKeyboardMarkup(keyboard))
    return config.CHOOSE_TARGET

async def handle_target_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, user_collection, broadcasts_collection):
    query = update.callback_query
    message = update.message
    target_chat_id = None
    
    if query:
        await query.answer()
        if query.data == "bcast_new":
            await query.edit_message_text("Please send the new Chat ID (e.g., @yourchannel or -100...).")
            return config.CHOOSE_TARGET
        else:
            target_chat_id = query.data.split("_", 1)[1]
            await query.edit_message_text(f"Sending to `{target_chat_id}`...", parse_mode="MarkdownV2")
    elif message:
        target_chat_id = message.text.strip()
        await message.reply_text(f"Sending to `{target_chat_id}`...", parse_mode="MarkdownV2")

    if target_chat_id:
        await send_broadcast(update, context, target_chat_id, user_collection, broadcasts_collection)
        return ConversationHandler.END
        
    return config.CHOOSE_TARGET

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, target_chat_id, user_collection, broadcasts_collection):
    is_ok, error_message = await check_bot_permissions(context, target_chat_id)
    if not is_ok:
        await context.bot.send_message(update.effective_chat.id, f"❌ Broadcast failed: {error_message}")
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
            photo=broadcast_doc['photo'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        broadcasts_collection.update_one({"_id": broadcast_id}, {"$set": {"telegram_message_id": sent_message.message_id}})
        await context.bot.send_message(update.effective_chat.id, "✅ Broadcast sent!")
    
    except Exception as e:
        logger.error(f"Error in send_broadcast: {e}")
        await context.bot.send_message(update.effective_chat.id, f"❌ Broadcast failed with an unexpected error: {e}")
    
    finally:
        context.user_data.clear()
        return ConversationHandler.END
