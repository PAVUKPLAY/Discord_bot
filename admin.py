import sys
import logging
import discord
from bot import bot
from config import RESTART_ROLE_IDS


@bot.tree.command(name="restart", description="Перезапустить бота (только для определённых ролей)")
async def restart_command(interaction: discord.Interaction):
    user_role_ids = [role.id for role in interaction.user.roles]
    if not any(role_id in user_role_ids for role_id in RESTART_ROLE_IDS):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды.", ephemeral=True)
        return
    await interaction.response.send_message("🔄 Перезапуск бота...", ephemeral=True)
    logging.info(f"Бот перезапущен пользователем {interaction.user} (ID: {interaction.user.id})")
    await bot.close()
    sys.exit(0)
