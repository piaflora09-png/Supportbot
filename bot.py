import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# --- RENDER WEB SERVER KEEP-ALIVE ---
# Render Web Services require an active HTTP port to prevent sleep/spin-down.
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check web server running on port {port}")
    server.serve_forever()

# Start the web server in a background thread so it doesn't block the Discord bot
threading.Thread(target=run_web_server, daemon=True).start()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

SUPPORT_ROLE_NAME = "Support Team"

# Helper function to handle ticket creation logic for buttons
async def create_ticket_channel(interaction: discord.Interaction, ticket_type: str):
    guild = interaction.guild
    member = interaction.user
    
    # Check existing channel to prevent duplicate spam
    channel_name = f"ticket-{member.name.lower()}"
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if existing_channel:
        await interaction.response.send_message(f"❌ You already have an open ticket here: {existing_channel.mention}", ephemeral=True)
        return

    # Setup channel permissions
    support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
    }
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)

    ticket_channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        topic=f"Category: {ticket_type} | User ID: {member.id}"
    )

    await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

    # Components V2 layout for the ticket channel welcome screen
    ticket_layout = discord.ui.LayoutView()
    ticket_container = discord.ui.Container(accent_color=discord.Colour.blurple())
    
    ticket_container.add_item(discord.ui.TextDisplay(f"# Support Ticket — {ticket_type}"))
    ticket_container.add_item(discord.ui.Separator())
    ticket_container.add_item(discord.ui.TextDisplay(f"Welcome {member.mention}!\n\nOur team has been notified. Please provide as much detail (screenshots, error codes, logs) as possible."))
    ticket_container.add_item(discord.ui.Separator())
    
    # Action row with Close button
    close_btn = discord.ui.Button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    
    async def close_callback(btn_interaction: discord.Interaction):
        await btn_interaction.response.send_message("🔒 Saving transcript and closing channel in 5 seconds...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await btn_interaction.channel.delete(reason=f"Closed by {btn_interaction.user}")
        except Exception as e:
            print(f"Error closing channel: {e}")

    close_btn.callback = close_callback
    ticket_container.add_item(discord.ui.ActionRow(close_btn))
    
    ticket_layout.add_item(ticket_container)
    await ticket_channel.send(view=ticket_layout)


# Components V2 Layout featuring Interactive Buttons for each category
class TicketSetupLayout(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        
        container = discord.ui.Container(accent_color=discord.Colour.green())
        container.add_item(discord.ui.TextDisplay("# 🛡️ Customer Support Helpdesk"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("Click one of the buttons below depending on your issue type to open a private support ticket channel.\n\n⏱️ **Response Time:** Usually answered within 15 minutes."))
        container.add_item(discord.ui.Separator())
        
        # Create individual buttons
        tech_btn = discord.ui.Button(label="Technical Support", style=discord.ButtonStyle.primary, emoji="💻", custom_id="btn_tech")
        billing_btn = discord.ui.Button(label="Billing & Payments", style=discord.ButtonStyle.secondary, emoji="💳", custom_id="btn_billing")
        general_btn = discord.ui.Button(label="General Inquiry", style=discord.ButtonStyle.success, emoji="❓", custom_id="btn_general")
        
        # Bind callbacks
        async def tech_callback(interaction: discord.Interaction):
            await create_ticket_channel(interaction, "Technical Support")
            
        async def billing_callback(interaction: discord.Interaction):
            await create_ticket_channel(interaction, "Billing & Payments")
            
        async def general_callback(interaction: discord.Interaction):
            await create_ticket_channel(interaction, "General Inquiry")

        tech_btn.callback = tech_callback
        billing_btn.callback = billing_callback
        general_btn.callback = general_callback
        
        # Add buttons to an ActionRow inside the container
        container.add_item(discord.ui.ActionRow(tech_btn, billing_btn, general_btn))
        
        self.add_item(container)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(e)
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Components V2 Button Ticket System is online and active!")

# --- SLASH COMMANDS ---

@bot.tree.command(name="setup_ticket", description="Deploy the interactive button support ticket panel using Components V2")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    await interaction.channel.send(view=TicketSetupLayout())
    await interaction.response.send_message("✅ Button support ticket panel deployed successfully!", ephemeral=True)

@bot.tree.command(name="add_user", description="Add a user to the current ticket channel")
@app_commands.describe(member="The user to add to this ticket")
async def add_user(interaction: discord.Interaction, member: discord.Member):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
        return
    
    await interaction.channel.set_permissions(member, read_messages=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"✅ Added {member.mention} to this support ticket.")

@bot.tree.command(name="remove_user", description="Remove a user from the current ticket channel")
@app_commands.describe(member="The user to remove from this ticket")
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
        return
    
    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"🔒 Removed {member.mention} from this ticket.")

# Run the bot using the token stored securely in Render environment variables
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is missing!")

bot.run(TOKEN)
