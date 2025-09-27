# search.py

import requests
from uuid import uuid4

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InputMediaPhoto, 
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import config

# --- Helper Functions ---
def fetch_and_expand_tv_seasons(query):
    base_url = "https://api.themoviedb.org/3"
    params = {"api_key": config.TMDB_API_KEY, "query": query}
    movie_results = requests.get(f"{base_url}/search/movie", params=params).json().get("results", [])
    tv_results = requests.get(f"{base_url}/search/tv", params=params).json().get("results", [])
    initial_results = sorted(movie_results + tv_results, key=lambda x: x.get("popularity", 0), reverse=True)

    expanded_results = []
    for item in initial_results[:10]:
        media_type = 'movie' if 'title' in item else 'tv'
        if media_type == 'movie':
            expanded_results.append({
                "id": item["id"], "title": item.get('title'), "media_type": 'movie',
                "year": (item.get('release_date') or '')[:4], "poster_path": item.get("poster_path"),
                "popularity": item.get("popularity", 0)
            })
        elif media_type == 'tv':
            show_details_url = f"{base_url}/tv/{item['id']}"
            show_details_res = requests.get(show_details_url, params={"api_key": config.TMDB_API_KEY}).json()
            seasons = show_details_res.get('seasons', [])
            for season in seasons:
                if season.get('season_number') == 0: continue
                expanded_results.append({
                    "id": item["id"], "title": f"{item.get('name')} - Season {season.get('season_number')}",
                    "media_type": 'tv', "season_number": season.get('season_number'),
                    "year": (season.get('air_date') or '')[:4],
                    "poster_path": season.get('poster_path') or item.get('poster_path'),
                    "popularity": item.get("popularity", 0)
                })
    return sorted(expanded_results, key=lambda x: x["popularity"], reverse=True)

def get_details(tmdb_id, media_type):
    base_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
    params = {"api_key": config.TMDB_API_KEY}
    details = requests.get(base_url, params=params).json()
    credits = requests.get(f"{base_url}/credits", params=params).json()
    return details, credits

def get_extra_details_for_labels(tmdb_id, media_type):
    params = {"api_key": config.TMDB_API_KEY}
    extra_info = {}
    if media_type == 'movie':
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/release_dates"
        response = requests.get(url, params=params).json()
        for result in response.get('results', []):
            if result.get('iso_3166_1') == 'US':
                for release in result.get('release_dates', []):
                    if release.get('certification'):
                        extra_info['rating'] = release.get('certification'); break
                break
    else: # TV Show
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/content_ratings"
        response = requests.get(url, params=params).json()
        for result in response.get('results', []):
            if result.get('iso_3166_1') == 'US':
                extra_info['rating'] = result.get('rating'); break
    return extra_info

def get_season_details(tmdb_id, season_number):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season_number}"
    params = {"api_key": config.TMDB_API_KEY}
    try:
        response = requests.get(url, params=params); response.raise_for_status()
        return response.json()
    except requests.RequestException: return {}

def get_best_backdrop_path(tmdb_id, media_type):
    try:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images"; params = {"api_key": config.TMDB_API_KEY}
        response = requests.get(url, params=params).json()
        if response and "backdrops" in response and len(response["backdrops"]) > 0:
            return response["backdrops"][0].get("file_path")
    except Exception as e: print(f"Error fetching best backdrop: {e}")
    return None

def get_trailer_link(tmdb_id, media_type):
    api_key = config.TMDB_API_KEY; media_type_api = 'tv' if media_type == 'tv' else 'movie'
    url = f"https://api.themoviedb.org/3/{media_type_api}/{tmdb_id}/videos?api_key={api_key}&language=en-US"
    try:
        response = requests.get(url); response.raise_for_status()
        videos = response.json().get('results', [])
        for video in videos:
            if video['site'] == 'YouTube' and video['type'] == 'Trailer' and video.get('official', False):
                return f"https://www.youtube.com/watch?v={video['key']}"
        for video in videos:
            if video['site'] == 'YouTube' and video['type'] == 'Trailer':
                return f"https://www.youtube.com/watch?v={video['key']}"
        for video in videos:
            if video['site'] == 'YouTube': return f"https://www.youtube.com/watch?v={video['key']}"
    except requests.RequestException as e: print(f"Error fetching trailer from TMDB: {e}")
    return None

# --- Command and Query Handlers ---
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <title>"); return
    results = fetch_and_expand_tv_seasons(query)
    if not results:
        await update.message.reply_text("No results found."); return
    context.user_data.update({"search_results": results, "search_page": 0, "search_query": query})
    await send_search_page(update, context)

async def send_search_page(update, context, edit=False):
    results = context.user_data["search_results"]
    page = context.user_data["search_page"]
    query_text = context.user_data["search_query"]
    PAGE_SIZE = 5
    start = page * PAGE_SIZE
    page_data = results[start:start + PAGE_SIZE]
    
    buttons = []
    for r in page_data:
        if r['media_type'] == 'tv':
            callback_data = f"select_{r['id']}_tv_{r['season_number']}"
        else:
            callback_data = f"select_{r['id']}_movie"
        buttons.append([InlineKeyboardButton(f"{r['title']} ({r['year']})", callback_data=callback_data)])

    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅ Prev", callback_data="prev_page"))
    if (page + 1) * PAGE_SIZE < len(results): nav.append(InlineKeyboardButton("Next ➡", callback_data="next_page"))
    if nav: buttons.append(nav)
    
    caption = f"🎯 Results for: <b>{query_text}</b>\nPage {page+1}"
    if edit:
        await update.callback_query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_photo(photo=config.DEFAULT_THUMBNAIL, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query: return
    
    base_url = "https://api.themoviedb.org/3"
    params = {"api_key": config.TMDB_API_KEY, "query": query}
    movie_results = requests.get(f"{base_url}/search/movie", params=params).json().get("results", [])
    tv_results = requests.get(f"{base_url}/search/tv", params=params).json().get("results", [])
    results = sorted(movie_results + tv_results, key=lambda x: x.get("popularity", 0), reverse=True)
    
    articles = []
    for item in results[:20]:
        title = item.get('title') or item.get('name')
        year = (item.get('release_date') or item.get('first_air_date') or '')[:4]
        media_type = 'movie' if 'title' in item else 'tv'
        input_content = InputTextMessageContent(f"/show_{item['id']}_{media_type}")
        
        articles.append(InlineQueryResultArticle(
            id=str(uuid4()), 
            title=f"{title} ({year})",
            description=f"{media_type.capitalize()} • {year}",
            thumbnail_url=f"https://image.tmdb.org/t/p/w92{item.get('poster_path')}" if item.get("poster_path") else config.DEFAULT_THUMBNAIL,
            input_message_content=input_content
        ))
    await update.inline_query.answer(articles, cache_time=10)

### --- MODIFIED --- ###
# This function now checks where the inline result was clicked.
async def show_from_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- NEW PERMISSION CHECK ---
    # Only allow the result to be posted in the designated OWNER_GROUP
    if str(update.effective_chat.id) != config.OWNER_GROUP:
        try:
            # First, delete the triggering command message (/show_...)
            await update.message.delete()
            # Then, inform the user they are in the wrong chat
            await update.effective_chat.send_message(
                text="ℹ️ Please select inline results only from within the authorized group.",
            )
        except BadRequest:
            # Ignore if message is already gone or bot lacks delete permissions
            pass 
        return # Stop further execution of the function
    # --- END PERMISSION CHECK ---
    
    try:
        _, tmdb_id, media_type = update.message.text.split("_")
        try: 
            await update.message.delete()
        except BadRequest: 
            pass

        if media_type == 'tv':
            details, _ = get_details(tmdb_id, 'tv')
            seasons = details.get('seasons', [])
            
            buttons = []
            for season in seasons:
                if season.get('season_number') == 0: continue
                season_num = season.get('season_number')
                season_year = (season.get('air_date') or 'N/A')[:4]
                button_text = f"Season {season_num} ({season_year})"
                callback_data = f"seasonselect_{tmdb_id}_{season_num}"
                buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            if buttons:
                await update.effective_chat.send_message(
                    f"Please select a season for <b>{details.get('name')}</b>:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode="HTML"
                )
            else:
                await update.effective_chat.send_message("Sorry, no seasons found for this series.")
        else:
            await send_details_display_new(update, context, tmdb_id, media_type)
    except Exception as e:
        print(f"Error in show_from_inline: {e}")
### --- END MODIFIED SECTION --- ###

async def send_details_display_new(update, context, tmdb_id, media_type, season_number=1):
    details, _ = get_details(tmdb_id, media_type)
    title = details.get("title") or details.get("name")
    
    year = (details.get('release_date') or details.get('first_air_date') or '')[:4]
    
    if media_type == 'tv':
        season_details = get_season_details(tmdb_id, season_number)
        season_name = season_details.get("name", f"Season {season_number}")
        title = f"{title} - {season_name}"
        if season_details.get("air_date"):
            year = season_details.get("air_date")[:4]

    genres = ", ".join([g["name"] for g in details.get("genres", [])])
    rating = details.get("vote_average", 0)
    country = (details.get("production_countries")[0]['iso_3166_1'] if details.get("production_countries") else "N/A")
    status = details.get("status", "Unknown")
    overview = details.get("overview", "No overview.")
    backdrop_path = get_best_backdrop_path(tmdb_id, media_type) or details.get('backdrop_path')
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else config.DEFAULT_THUMBNAIL
    
    caption = (f"🎬 <b>{title}</b> ({year})\n"
               f"#{'Movie' if media_type == 'movie' else 'TVSeries'} #{status.replace(' ', '')}\n\n"
               f"🔸 <b>Genre</b>: {genres}\n🔸 <b>Rated</b>: N/A\n🔸 <b>Country</b>: {country}\n"
               f"🔸 <b>Rating</b>: {round(rating, 1)}/10\n\n📜 <b>Overview</b>:\n<blockquote>{overview}</blockquote>")

    gencode_callback = f"gencode_{tmdb_id}_{media_type}"
    if media_type == 'tv':
        gencode_callback += f"_{season_number}"

    buttons = [
        [
            InlineKeyboardButton("🎞️ Trailer", callback_data=f"trailer_{tmdb_id}_{media_type}"),
            InlineKeyboardButton("📋 Copy Details", callback_data=f"copy_details_{tmdb_id}")
        ],
        [
            InlineKeyboardButton("💾 Generate Post Code", callback_data=gencode_callback)
        ]
    ]
    
    if update.callback_query:
        # Check if the message to be edited has a photo
        if update.callback_query.message.photo:
             await update.callback_query.message.edit_media(
                media=InputMediaPhoto(media=backdrop_url, caption=caption, parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            # If the original message was text-only (like the season selector), delete it and send a new photo message
            await update.callback_query.message.delete()
            await update.effective_chat.send_photo(
                photo=backdrop_url, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        await update.effective_chat.send_photo(
            photo=backdrop_url, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
        )
