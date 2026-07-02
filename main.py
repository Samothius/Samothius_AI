import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import time

from config import DISCORD_TOKEN, STREAM_NOTIFICATION_ROLE_ID, SAMOBIT_EMOJI
from database import DatabaseManager
from twitch_api import TwitchApiClient

class NotificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Toggle Notifications", emoji="🔔", style=discord.ButtonStyle.secondary, custom_id="toggle_ping_role")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(STREAM_NOTIFICATION_ROLE_ID)
        
        if not role:
            return await interaction.response.send_message("Notification role not found on this server!", ephemeral=True)
        
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("Notifications disabled! 🔕", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Notifications enabled! 🔔", ephemeral=True)

class SamothiusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.db = DatabaseManager()
        self.twitch_api = TwitchApiClient()
        
        self.start_time = discord.utils.utcnow()
        self.daily_commands_run = 0             
        self.daily_errors = 0                   
        self.is_live = False

    async def setup_hook(self):
        self.add_view(NotificationView())

    async def on_ready(self):
        print(f"✅ Discord Bot connected as {self.user}")
        if not self.daily_report_loop.is_running():
            self.daily_report_loop.start()
            
        if not self.stream_announcement_loop.is_running():
            self.stream_announcement_loop.start()

    async def on_command_completion(self, ctx):
        self.daily_commands_run += 1

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return 
        self.daily_errors += 1
        print(f"⚠️ Command Error: {error}")

    async def run_daily_report(self):
        # 1: SYSTEM HEALTH REPORT 
        try:
            LOG_THREAD_ID = 1517792028862320640
            log_thread = self.get_channel(LOG_THREAD_ID)
            if not log_thread:
                log_thread = await self.fetch_channel(LOG_THREAD_ID)
            
            uptime = discord.utils.utcnow() - self.start_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m"

            total_users = self.db.get_total_users()
            total_volume = self.db.get_total_samobit_volume()

            status_embed = discord.Embed(
                title="🛠️ Samothius AI - Daily System Status",
                color=0x2ECC71, 
                timestamp=discord.utils.utcnow()
            )
            status_embed.add_field(name="⏱️ Bot Uptime", value=f"`{uptime_str}`", inline=True)
            status_embed.add_field(name="📡 API Ping", value=f"`{round(self.latency * 1000)}ms`", inline=True)
            status_embed.add_field(name="👥 Total Economy", value=f"{total_users} Users\n{total_volume} SamoBits {SAMOBIT_EMOJI}", inline=False)
            status_embed.add_field(name="⚙️ Daily Stats", value=f"Commands Run: `{self.daily_commands_run}`\nErrors Caught: `{self.daily_errors}`", inline=False)
            
            await log_thread.send(embed=status_embed)
            
            self.daily_commands_run = 0
            self.daily_errors = 0

        except Exception as e:
            print(f"⚠️ Failed to send System Status: {e}")

        # 2: DAILY TOP 50 LEADERBOARD
        try:
            LEADERBOARD_CHANNEL_ID = 1517832900794388551
            
            lb_channel = self.get_channel(LEADERBOARD_CHANNEL_ID)
            if not lb_channel:
                lb_channel = await self.fetch_channel(LEADERBOARD_CHANNEL_ID)

            def is_me(m):
                return m.author == self.user
            await lb_channel.purge(limit=10, check=is_me)

            top_50_users = self.db.get_top_richest_users(50)
            
            lb_embed = discord.Embed(
                title="🏆 Daily Top 50 Richest Players",
                description="The ultimate ranking of Samothius Economy! Updated daily.",
                color=0xF1C40F,
                timestamp=discord.utils.utcnow()
            )

            if not top_50_users:
                lb_embed.add_field(name="Ranking", value="No data yet. Start playing!", inline=False)
            else:
                lines = []
                for j, (name, bal) in enumerate(top_50_users, start=1):
                    medal = "👑" if j == 1 else "🥈" if j == 2 else "🥉" if j == 3 else f"`{j}.`"
                    lines.append(f"{medal} **{name}** — {bal} {SAMOBIT_EMOJI}")
                mid = len(lines) // 2
                lb_embed.add_field(name="Ranks 1-25", value="\n".join(lines[:mid]), inline=True)
                lb_embed.add_field(name="Ranks 26-50", value="\n".join(lines[mid:]), inline=True)

            await lb_channel.send(embed=lb_embed)
            print("🏆 Top 50 Leaderboard successfully purged and updated!")

        except Exception as e:
            print(f"⚠️ Failed to send Top 50 Leaderboard: {e}")

    @tasks.loop(minutes=3)  
    async def stream_announcement_loop(self):
        await self.wait_until_ready()
        try:
            streams = await self.twitch_api.get_live_stream()
            
            if streams:  
                if not self.is_live:  
                    self.is_live = True
                    
                    ANNOUNCEMENT_CHANNEL_ID = 1498468679879229570
                    channel = self.get_channel(ANNOUNCEMENT_CHANNEL_ID)
                    if not channel:
                        channel = await self.fetch_channel(ANNOUNCEMENT_CHANNEL_ID)
                    
                    if channel:
                        def is_me(m):
                            return m.author == self.user
                        await channel.purge(limit=10, check=is_me)
                        
                        stream_data = streams[0]
                        title = stream_data.get("title", "Samothius is LIVE!")
                        game = stream_data.get("game_name", "Just Chatting")
                        
                        embed = discord.Embed(
                            title="🔴 Samothius is now LIVE!",
                            color=0x9146FF, 
                            timestamp=discord.utils.utcnow()
                        )
                        
                        embed.description = (
                            "<:twitch:1493106317491962056> [twitch.tv](https://twitch.tv/samothius)   \n"
                            "<:kick:1498832104568655912> [kick.com](https://kick.com/samothius)   \n"
                            "<:youtube:1498832107034644580> [youtube.com](https://youtube.com/samothius)"
                        )
                        
                        embed.add_field(name="🎮 Category", value=game, inline=False)
                        embed.add_field(name="📝 Stream Title", value=title, inline=False)
                        embed.set_image(url="https://imgur.com/OneI0C5.jpg")
                        
                        ping_text = f"<@&{STREAM_NOTIFICATION_ROLE_ID}>"
                        view = NotificationView()
                        
                        await channel.send(content=ping_text, embed=embed, view=view)
                        print("📢 Stream announcement sent with custom UI and old ones purged!")
            else:
                self.is_live = False
                
        except Exception as e:
            print(f"⚠️ Stream announcement error: {e}")

    time_to_run = datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc)
    @tasks.loop(time=time_to_run)
    async def daily_report_loop(self):
        await self.wait_until_ready()
        await self.run_daily_report()

bot = SamothiusBot()

@bot.command(name="leaderboard")
async def leaderboard(ctx):
    """Shows the Top 10 richest users on the server on demand."""
    top_users = bot.db.get_top_richest_users(10)
    
    embed = discord.Embed(
        title="🏆 SamoBit Leaderboard",
        color=0xF1C40F,
        timestamp=discord.utils.utcnow()
    )
    
    if not top_users:
        embed.description = "No data yet. Start playing games!"
    else:
        leaderboard_text = ""
        for idx, (name, bal) in enumerate(top_users, 1):
            leaderboard_text += f"**{idx}.** {name} — {bal} SamoBit {SAMOBIT_EMOJI}\n"
        embed.description = leaderboard_text
        
    embed.set_footer(text="Updated in real-time")
    await ctx.send(embed=embed)

@bot.command(name="test_announcement")
async def test_announcement(ctx):
    """Developer command: Tests stream announcement and auto-purge silently."""
    channel_id = 1498468679879229570
    channel = bot.get_channel(channel_id)
    if not channel:
        channel = await bot.fetch_channel(channel_id)
    
    if channel:
        def is_me(m):
            return m.author == bot.user
        
        await channel.purge(limit=10, check=is_me)
        
        embed = discord.Embed(
            title="🔴 TEST STREAM - Samothius is now LIVE!",
            color=0x9146FF, 
            timestamp=discord.utils.utcnow()
        )
        
        embed.description = (
            "<:twitch:1493106317491962056> [twitch.tv](https://twitch.tv/samothius)   \n"
            "<:kick:1498832104568655912> [kick.com](https://kick.com/samothius)   \n"
            "<:youtube:1498832107034644580> [youtube.com](https://youtube.com/samothius)"
        )
        
        embed.add_field(name="🎮 Category", value="Test Simulator 2026", inline=False)
        embed.add_field(name="📝 Stream Title", value="Testing the ultimate bot features!", inline=False)
        embed.set_image(url="https://imgur.com/OneI0C5.jpg")
        
        view = NotificationView()
        await channel.send(content="[SILENT TEST] Samothius is live! 🚀", embed=embed, view=view)
        await ctx.send("✅ Silent test successfully triggered! Check the announcement channel.")
    else:
        await ctx.send("❌ Channel not found. Please check the ID.")

@bot.command(name="test_report")
async def test_report(ctx):
    """Developer command: Forces the daily report and leaderboard to run immediately."""
    await ctx.send("⏳ Generating daily report and Top 50 leaderboard...")
    try:
        await bot.run_daily_report()
        await ctx.send("✅ Daily report successfully generated in the log channels!")
    except Exception as e:
        await ctx.send(f"❌ Error generating report: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
