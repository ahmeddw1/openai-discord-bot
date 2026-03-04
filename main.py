import os
import discord
from discord import app_commands
from openai import OpenAI
import sqlite3
import asyncio

# -------------------------------
# ENV
# -------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROK_KEY = os.getenv("GROK_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # simple admin login

# -------------------------------
# Discord & Grok
# -------------------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
ai = OpenAI(api_key=GROK_KEY)

# -------------------------------
# Database
# -------------------------------
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

# Users table: balance, memory (JSON string of messages)
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    memory TEXT DEFAULT ''
)""")

# Shop table: item_name, price
cursor.execute("""CREATE TABLE IF NOT EXISTS shop (
    item TEXT PRIMARY KEY,
    price INTEGER
)""")
conn.commit()

# -------------------------------
# Economy Functions
# -------------------------------
def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row: return row[0]
    cursor.execute("INSERT INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()
    return 0

def update_balance(user_id, amount):
    bal = get_balance(user_id)
    new_bal = bal + amount
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, user_id))
    conn.commit()
    return new_bal

# -------------------------------
# Memory Functions
# -------------------------------
def get_memory(user_id):
    cursor.execute("SELECT memory FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return row[0].split("|")
    return []

def add_memory(user_id, message):
    mem = get_memory(user_id)
    mem.append(message)
    if len(mem) > 10: mem = mem[-10:]
    cursor.execute("UPDATE users SET memory=? WHERE user_id=?", ("|".join(mem), user_id))
    conn.commit()

# -------------------------------
# Bot Events
# -------------------------------
@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# -------------------------------
# AI Chat Command
# -------------------------------
@tree.command(name="chat", description="🧠 AI Chat using Grok")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    try:
        memory = get_memory(user_id)
        prompt = "\n".join(memory[-5:] + [message])
        response = ai.chat.completions.create(
            model="grok-mini",
            messages=[{"role":"user","content":prompt}]
        )
        reply = response.choices[0].message.content
        add_memory(user_id, message)
        await interaction.followup.send(f"🧠 **Grok AI:** {reply}")
    except Exception as e:
        print(e)
        await interaction.followup.send("⚠️ Grok AI failed. Check API key/quota.")

# -------------------------------
# AI Code Generator
# -------------------------------
@tree.command(name="code", description="🤖 Generate code with Grok")
async def code(interaction: discord.Interaction, language: str, prompt: str):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    try:
        response = ai.chat.completions.create(
            model="grok-mini",
            messages=[
                {"role": "system", "content": f"Write only {language} code."},
                {"role": "user", "content": prompt}
            ]
        )
        code_result = response.choices[0].message.content
        # Save code to file
        file_name = f"code.{language.lower()}"
        with open(file_name, "w", encoding="utf-8") as f: f.write(code_result)
        await interaction.followup.send(content="💻 Code generated:", file=discord.File(file_name))
    except Exception as e:
        print(e)
        await interaction.followup.send("⚠️ Grok AI failed. Check API key/quota.")

# -------------------------------
# Economy Commands
# -------------------------------
@tree.command(name="balance", description="🎮 Check your balance")
async def balance(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    bal = get_balance(user_id)
    await interaction.response.send_message(f"💰 Your balance: {bal} coins")

@tree.command(name="daily", description="🎁 Claim daily reward")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    reward = 100
    new_bal = update_balance(user_id, reward)
    await interaction.response.send_message(f"🎁 You received {reward} coins! Balance: {new_bal}")

# -------------------------------
# Shop Commands
# -------------------------------
@tree.command(name="shop", description="🛒 View shop items")
async def shop(interaction: discord.Interaction):
    cursor.execute("SELECT item, price FROM shop")
    items = cursor.fetchall()
    msg = "🛒 **Shop Items:**\n"
    for item, price in items:
        msg += f"{item} - {price} coins\n"
    await interaction.response.send_message(msg)

@tree.command(name="buy", description="🛒 Buy an item")
async def buy(interaction: discord.Interaction, item: str):
    user_id = str(interaction.user.id)
    cursor.execute("SELECT price FROM shop WHERE item=?", (item,))
    row = cursor.fetchone()
    if not row:
        return await interaction.response.send_message("⚠️ Item not found.")
    price = row[0]
    if get_balance(user_id) < price:
        return await interaction.response.send_message("⚠️ Not enough coins.")
    update_balance(user_id, -price)
    await interaction.response.send_message(f"✅ You bought **{item}**!")

# -------------------------------
# Leaderboard
# -------------------------------
@tree.command(name="leaderboard", description="🏆 Top users")
async def leaderboard(interaction: discord.Interaction):
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = cursor.fetchall()
    msg = "🏆 **Leaderboard:**\n"
    for i, (uid, bal) in enumerate(top, 1):
        msg += f"#{i} - <@{uid}> : {bal} coins\n"
    await interaction.response.send_message(msg)

# -------------------------------
# Admin Dashboard (Password)
# -------------------------------
@tree.command(name="admin", description="🔒 Admin Panel")
async def admin(interaction: discord.Interaction, password: str):
    if password != ADMIN_PASSWORD:
        return await interaction.response.send_message("⚠️ Wrong password!")
    # Example: list shop items
    cursor.execute("SELECT item, price FROM shop")
    items = cursor.fetchall()
    msg = "**Admin Dashboard:**\nShop Items:\n"
    for item, price in items:
        msg += f"{item} - {price}\n"
    await interaction.response.send_message(msg)

# -------------------------------
# Run Bot
# -------------------------------
client.run(DISCORD_TOKEN)
