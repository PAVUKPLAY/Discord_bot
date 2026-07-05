import discord
from discord import app_commands
from discord.ui import Modal, TextInput, View, button, ButtonStyle

from bot import bot
from config import (
    ROLE_SETUP_CHANNEL_ID,
    GUEST_ROLE_ID,
    FIGHTER_ROLE_ID,
    ALLOWED_ROLE_IDS_FOR_BUTTONS,
)


# ------------------------------------------------------------
class RoleModal(Modal, title='Выдача роли'):
    def __init__(self, role_name: str, role_id: int):
        super().__init__()
        self.role_name = role_name
        self.role_id = role_id

    user_input = TextInput(
        label='ID пользователя или упоминание',
        placeholder='Введите ID или @упомяните пользователя',
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.check_permissions(interaction):
            await interaction.response.send_message("❌ У вас нет прав на выдачу ролей.", ephemeral=True)
            return

        input_text = self.user_input.value.strip()
        user = None
        if input_text.startswith('<@') and input_text.endswith('>'):
            user_id = int(input_text.strip('<@!>'))
            user = interaction.guild.get_member(user_id)
        elif input_text.isdigit():
            user_id = int(input_text)
            user = interaction.guild.get_member(user_id)
        else:
            for member in interaction.guild.members:
                if member.name.lower() == input_text.lower() or member.display_name.lower() == input_text.lower():
                    user = member
                    break

        if user is None:
            await interaction.response.send_message("❌ Пользователь не найден. Укажите корректный ID или упоминание.", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("❌ Роль не найдена. Обратитесь к администратору.", ephemeral=True)
            return

        if role in user.roles:
            await interaction.response.send_message(f"ℹ️ У пользователя {user.mention} уже есть роль **{role.name}**.", ephemeral=True)
            return

        try:
            await user.add_roles(role, reason=f"Выдано через кнопку {self.role_name} пользователем {interaction.user}")
            await interaction.response.send_message(f"✅ Роль **{role.name}** успешно выдана пользователю {user.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ У бота недостаточно прав для выдачи этой роли.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при выдаче роли: {e}", ephemeral=True)

    async def check_permissions(self, interaction: discord.Interaction) -> bool:
        if not ALLOWED_ROLE_IDS_FOR_BUTTONS:
            return True
        user_role_ids = [role.id for role in interaction.user.roles]
        return any(role_id in user_role_ids for role_id in ALLOWED_ROLE_IDS_FOR_BUTTONS)


# ------------------------------------------------------------
class RoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label='👤 Гость', style=ButtonStyle.primary, custom_id='give_guest')
    async def guest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(role_name='Гость', role_id=GUEST_ROLE_ID)
        await interaction.response.send_modal(modal)

    @button(label='⚔️ Боец', style=ButtonStyle.success, custom_id='give_fighter')
    async def fighter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(role_name='Боец', role_id=FIGHTER_ROLE_ID)
        await interaction.response.send_modal(modal)


# ------------------------------------------------------------
@bot.tree.command(name="setup_roles", description="Создать сообщение с кнопками для выдачи ролей (только администраторы)")
@app_commands.default_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    channel = bot.get_channel(ROLE_SETUP_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message(f"❌ Канал с ID {ROLE_SETUP_CHANNEL_ID} не найден. Проверьте ROLE_SETUP_CHANNEL_ID.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎫 Выдача ролей",
        description="Нажмите на кнопку ниже, чтобы выдать роль новому игроку.\n"
                    "В открывшемся окне укажите ID пользователя или упомяните его.",
        color=discord.Color.gold()
    )
    embed.add_field(name="🟦 Гость", value="Базовая роль для новичков", inline=True)
    embed.add_field(name="🟩 Боец", value="Роль для опытных игроков", inline=True)
    embed.set_footer(text="Бот выдаст роль только при наличии прав")

    view = RoleView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Сообщение с кнопками отправлено в канал {channel.mention}", ephemeral=True)