import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import discord
from discord.ext import tasks

from bot import bot
from config import (
    BATTLEMETRICS_TOKEN,
    BATTLEMETRICS_SERVER_ID,
    STATUS_CHANNEL_ID,
    PRIORITY_TAGS,
)


async def fetch_battlemetrics(endpoint: str):
    if bot.session is None:
        logging.error("Сессия aiohttp не инициализирована!")
        return None
    url = f"https://api.battlemetrics.com/{endpoint}"
    headers = {
        "Authorization": f"Bearer {BATTLEMETRICS_TOKEN}",
        "Accept": "application/json"
    }
    try:
        async with bot.session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                text = await resp.text()
                logging.error(f"BattleMetrics API error {resp.status}: {text[:200]}")
                return None
            return await resp.json()
    except asyncio.TimeoutError:
        logging.error("BattleMetrics API timeout")
        return None
    except Exception as e:
        logging.error(f"BattleMetrics request error: {e}")
        return None


async def get_server_status() -> Optional[Dict[str, Any]]:
    try:
        data = await fetch_battlemetrics(
            f"servers/{BATTLEMETRICS_SERVER_ID}?include=player,session"
        )
        if not data:
            return None

        attrs = data["data"]["attributes"]
        session_times = {}

        for item in data.get("included", []):
            if item.get("type") == "session":
                player_id = item["relationships"]["player"]["data"]["id"]
                start_str = item["attributes"].get("start")
                if start_str:
                    start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    duration = int((now - start_time).total_seconds())
                    session_times[player_id] = duration

        players = []
        for item in data.get("included", []):
            if item.get("type") == "player" and "attributes" in item:
                name = item["attributes"].get("name")
                player_id = item["id"]
                if name:
                    duration = session_times.get(player_id, 0)
                    players.append({"name": name, "duration": duration})

        def priority_key(p):
            name_upper = p["name"].upper()
            for idx, tag in enumerate(PRIORITY_TAGS):
                if tag.upper() in name_upper:
                    return (0, idx, name_upper)
            return (1, name_upper)

        players.sort(key=priority_key)

        status = {
            "name": attrs["name"],
            "map": attrs["details"].get("map", "Unknown"),
            "players_online": attrs["players"],
            "players_max": attrs["maxPlayers"],
            "players_list": players,
        }
        logging.info(f"Статус: {status['players_online']}/{status['players_max']} игроков, в списке: {len(players)}")
        return status
    except Exception as e:
        logging.error(f"Ошибка запроса: {e}")
        return None


def format_uptime(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0 or days > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    if hours > 0:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


def make_progress_bar(percent, length=15, filled="█", empty="░"):
    filled_count = round(length * percent / 100)
    return filled * filled_count + empty * (length - filled_count)


def create_status_embed(status_data):
    if status_data is None:
        return discord.Embed(
            title="🔴 СЕРВЕР НЕДОСТУПЕН",
            description="Не удаётся получить данные через BattleMetrics API.",
            color=discord.Color.red()
        )
    percent = round(status_data['players_online'] / status_data['players_max'] * 100)
    if percent >= 80:
        color = discord.Color.red()
        status_emoji = "🔴"
        status_text = "Высокая нагрузка"
    elif percent >= 40:
        color = discord.Color.orange()
        status_emoji = "🟠"
        status_text = "Средняя нагрузка"
    else:
        color = discord.Color.green()
        status_emoji = "🟢"
        status_text = "Низкая нагрузка"

    bar_precise = make_progress_bar(percent, 15)
    g4s_count = sum(1 for p in status_data['players_list'] if "[g4s]" in p["name"].lower())

    embed = discord.Embed(
        title=f"🖥️ **{status_data['name']}**",
        color=color,
        description=f"**{status_emoji} Состояние:** {status_text}"
    )
    embed.add_field(name="👥 Игроки", value=f"**{status_data['players_online']}** / {status_data['players_max']}", inline=True)
    embed.add_field(name="🗺️ Карта", value=f"**{status_data['map']}**", inline=True)
    embed.add_field(name="🎖️ Бойцы [G4S]", value=f"**{g4s_count}** игроков", inline=True)

    embed.add_field(name="📊 Загруженность сервера", value=f"{bar_precise} `{percent}%`", inline=True)
    if bot.server_online_since is not None:
        uptime_seconds = int((datetime.now(timezone.utc) - bot.server_online_since).total_seconds())
        uptime_str = format_uptime(uptime_seconds)
        embed.add_field(name="⏱️ Время работы", value=f"**{uptime_str}**", inline=True)
    else:
        embed.add_field(name="⏱️ Время работы", value="Неизвестно", inline=True)

    embed.set_footer(text="🔄 Обновление было")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def create_players_embed(players_list):
    if not players_list:
        return discord.Embed(
            title="🎮 Список игроков",
            description="На сервере сейчас никого нет.",
            color=discord.Color.blue()
        )

    temp_lines = []
    max_name_len = 0
    for p in players_list:
        name = p["name"]
        duration_sec = p["duration"]
        time_str = format_duration(duration_sec) if duration_sec > 0 else "только зашёл"
        temp_lines.append((name, time_str))
        max_name_len = max(max_name_len, len(name))

    lines = []
    for name, time_str in temp_lines:
        padded_name = name.ljust(max_name_len + 2)
        lines.append(f"{padded_name}   {time_str}")

    code_block = "```\n" + "\n".join(lines) + "\n```"
    embed = discord.Embed(
        title=f"🎮 Список игроков ({len(players_list)})",
        color=discord.Color.blue()
    )
    embed.description = code_block
    embed.set_footer(text="🔄 Обновление было")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


@tasks.loop(minutes=1)
async def auto_update():
    status_data = await get_server_status()

    if status_data is not None:
        if bot.server_online_since is None:
            bot.server_online_since = datetime.now(timezone.utc)
            logging.info("Сервер онлайн, uptime начат")
    else:
        if bot.server_online_since is not None:
            logging.info("Сервер не отвечает, uptime сброшен")
            bot.server_online_since = None

    if status_data:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{status_data['players_online']}/{status_data['players_max']} игроков"
        )
        await bot.change_presence(activity=activity)
    else:
        activity = discord.Activity(type=discord.ActivityType.watching, name="за сервером Arma 3...")
        await bot.change_presence(activity=activity)

    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel is None:
        logging.error(f"Канал {STATUS_CHANNEL_ID} не найден! Проверьте STATUS_CHANNEL_ID.")
        return

    embed_status = create_status_embed(status_data)
    if bot.status_message is None:
        async for msg in channel.history(limit=50):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title and "🖥️" in msg.embeds[0].title:
                bot.status_message = msg
                break
        if bot.status_message is None:
            bot.status_message = await channel.send(embed=embed_status)
            logging.info("Создано сообщение со статусом")
    else:
        try:
            await bot.status_message.edit(embed=embed_status)
        except discord.NotFound:
            bot.status_message = await channel.send(embed=embed_status)
            logging.warning("Статус-сообщение потеряно, создано новое")
        except Exception as e:
            logging.error(f"Ошибка редактирования статуса: {e}")

    players_list = status_data["players_list"] if status_data else []
    embed_players = create_players_embed(players_list)
    if bot.players_message is None:
        async for msg in channel.history(limit=50):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title and "Список игроков" in msg.embeds[0].title:
                bot.players_message = msg
                break
        if bot.players_message is None:
            bot.players_message = await channel.send(embed=embed_players)
            logging.info("Создано сообщение со списком игроков")
    else:
        try:
            await bot.players_message.edit(embed=embed_players)
        except discord.NotFound:
            bot.players_message = await channel.send(embed=embed_players)
            logging.warning("Сообщение со списком потеряно, создано новое")
        except Exception as e:
            logging.error(f"Ошибка редактирования списка: {e}")
