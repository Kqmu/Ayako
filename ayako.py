import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Spotify setup
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# Get YouTube audio stream
def get_youtube_url(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch',
        'extract_flat': 'in_playlist',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

        # Handle ytsearch results
        if 'entries' in info and len(info['entries']) > 0:
            first = info['entries'][0]
            # If it's already a full URL, return it
            if 'url' in first and first['url'].startswith('http'):
                return first['url']
            elif 'id' in first:
                return f"https://www.youtube.com/watch?v={first['id']}"
            else:
                raise Exception("No valid video found in search.")
        
        # Handle direct video links
        elif 'id' in info:
            return f"https://www.youtube.com/watch?v={info['id']}"

        raise Exception("No valid YouTube result found.")



async def play_audio(source, url):
    # Determine voice client from type
    if isinstance(source, discord.Interaction):
        voice_client = source.guild.voice_client
        author_voice = source.user.voice
        send = source.followup.send
    else:  # assuming commands.Context
        voice_client = source.voice_client
        author_voice = source.author.voice
        send = source.send

    if voice_client is None:
        if author_voice:
            vc = await author_voice.channel.connect()
        else:
            await send("You're not in a voice channel.")
            return
    else:
        vc = voice_client

    if not vc.is_playing():
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']

        vc.play(discord.FFmpegPCMAudio(audio_url), after=lambda e: print("Playback finished"))

        await send(f"Now playing: **{info.get('title', 'Unknown Title')}**")
    else:
        await send("Already playing audio.")


# --- Slash Command Version ---
@tree.command(name="play", description="Play a song from YouTube or Spotify")
@app_commands.describe(query="Song name or Spotify/YouTube link")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if "spotify.com" in query:
        track = sp.track(query)
        query = f"{track['name']} {track['artists'][0]['name']}"
    yt_url = get_youtube_url(query)
    await play_audio(interaction, yt_url)

# --- Prefix Version ---
@bot.command(name="play")
async def play_command(ctx, *, query: str):
    if "spotify.com" in query:
        track = sp.track(query)
        query = f"{track['name']} {track['artists'][0]['name']}"
    yt_url = get_youtube_url(query)
    await play_audio(ctx, yt_url)

@bot.command(name="stop")
async def stop_command(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user.name}")

bot.run(TOKEN)
