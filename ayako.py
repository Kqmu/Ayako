import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import defaultdict, deque

# Per-guild music queues
music_queues = defaultdict(deque)


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
        'cookiefile': 'youtube_cookies.txt',
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

import asyncio

async def start_idle_timer(vc: discord.VoiceClient, source):
    await asyncio.sleep(300)  # 5 minutes
    if not vc.is_playing():
        try:
            await vc.disconnect()
            if isinstance(source, discord.Interaction):
                await source.followup.send("Disconnected due to inactivity.")
            else:
                await source.send("Disconnected due to inactivity.")
        except Exception as e:
            print(f"Error during auto-disconnect: {e}")


async def play_audio(source, url):
    if isinstance(source, discord.Interaction):
        guild_id = source.guild.id
        voice_client = source.guild.voice_client
        author_voice = source.user.voice
        send = source.followup.send
    else:
        guild_id = source.guild.id
        voice_client = source.voice_client
        author_voice = source.author.voice
        send = source.send

    # Join voice if not already connected
    if voice_client is None:
        if author_voice:
            vc = await author_voice.channel.connect()
        else:
            await send("You're not in a voice channel.")
            return
    else:
        vc = voice_client

    # Add to queue
    music_queues[guild_id].append(url)

    # If nothing is playing, start the player
    if not vc.is_playing():
        await play_next_in_queue(vc, source)
    else:
        await send("Added to the queue!")

async def play_next_in_queue(vc: discord.VoiceClient, source):
    guild_id = source.guild.id

    if not music_queues[guild_id]:
        await asyncio.sleep(300)  # 5 minute auto-leave
        if not vc.is_playing():
            await vc.disconnect()
        return

    next_url = music_queues[guild_id].popleft()

    ydl_opts = {'format': 'bestaudio', 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(next_url, download=False)
        audio_url = info['url']
        title = info.get('title', 'Unknown Title')

    vc.play(discord.FFmpegPCMAudio(audio_url), after=lambda e: asyncio.run_coroutine_threadsafe(play_next_in_queue(vc, source), bot.loop))

    if isinstance(source, discord.Interaction):
        await source.followup.send(f"Now playing: **{title}**")
    else:
        await source.send(f"Now playing: **{title}**")



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
@tree.command(name="stop", description="Stop playing music and disconnect from voice channel")
async def slash_stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        await interaction.response.send_message("I'm not connected to a voice channel.", ephemeral=True)
        return

    await voice_client.disconnect()
    await interaction.response.send_message("Disconnected from the voice channel.")
@tree.command(name="pause", description="Pause the current track")
async def slash_pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("Playback paused.")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)

@tree.command(name="resume", description="Resume paused music")
async def slash_resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("Resumed playback.")
    else:
        await interaction.response.send_message("Nothing is paused.", ephemeral=True)
@tree.command(name="queue", description="Show the current music queue")
async def slash_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = list(music_queues[guild_id])
    if not queue:
        await interaction.response.send_message("The queue is empty.", ephemeral=True)
    else:
        formatted = "\n".join(f"{i+1}. {url}" for i, url in enumerate(queue))
        await interaction.response.send_message(f"**Current Queue:**\n{formatted}")





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
    print("successfully finished startup")

bot.run(TOKEN)
