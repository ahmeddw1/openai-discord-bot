import os
import discord
from discord import app_commands
from openai import OpenAI
import sqlite3

# -------------------------------
# ENV
# -------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROK_KEY = os.getenv("GROK_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

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

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    memory TEXT DEFAULT ''
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS shop (
    item TEXT PRIMARY KEY,
    price INTEGER
)""")
conn.commit()

# -------------------------------
# Economy & Memory
# -------------------------------
def get_balance(uid):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    if row: return row[0]
    cursor.execute("INSERT INTO users(user_id) VALUES (?)", (uid,))
    conn.commit()
    return 0

def update_balance(uid, amt):
    bal = get_balance(uid)
    new_bal = bal + amt
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
    conn.commit()
    return new_bal

def get_memory(uid):
    cursor.execute("SELECT memory FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return row[0].split("|") if row and row[0] else []

def add_memory(uid, msg):
    mem = get_memory(uid)
    mem.append(msg)
    if len(mem)>10: mem=mem[-10:]
    cursor.execute("UPDATE users SET memory=? WHERE user_id=?", ("|".join(mem), uid))
    conn.commit()

# -------------------------------
# Bot Ready
# -------------------------------
@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# -------------------------------
# AI Chat (Grok 3 Mini)
# -------------------------------
@tree.command(name="chat", description="🧠 AI Chat with Grok 3 Mini")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    uid = str(interaction.user.id)
    try:
        memory = get_memory(uid)
        prompt = "\n".join(memory[-5:] + [message])
        response = ai.chat.completions.create(
            model="grok-3-mini",
            messages=[{"role":"user","content":prompt}]
        )
        reply = response.choices[0].message.content
        add_memory(uid, message)
        await interaction.followup.send(f"🧠 **Grok 3 Mini:** {reply}")
    except Exception as e:
        print("Grok Chat error:", e)
        await interaction.followup.send("⚠️ Grok AI failed. Check API key/quota.")

# -------------------------------
# AI Code Generator
# -------------------------------
@tree.command(name="code", description="🤖 AI Code Generator (Grok 3 Mini)")
async def code(interaction: discord.Interaction, language: str, prompt: str):
    await interaction.response.defer()
    uid = str(interaction.user.id)
    try:
        response = ai.chat.completions.create(
            model="grok-3-mini",
            messages=[
                {"role":"system","content":f"Write only {language} code."},
                {"role":"user","content":prompt}
            ]
        )
        code_text = response.choices[0].message.content
        file_name = f"code.{language.lower()}"
        with open(file_name,"w",encoding="utf-8") as f: f.write(code_text)
        await interaction.followup.send(content="💻 Code generated:", file=discord.File(file_name))
    except Exception as e:
        print("Grok Code error:", e)
        await interaction.followup.send("⚠️ Grok AI failed. Check API key/quota.")

# -------------------------------
# Grok Imagine Image
# -------------------------------
@tree.command(name="imagine_image", description="🖼️ Grok Imagine Image")
async def imagine_image(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        resp = ai.images.generate(prompt=prompt, model="grok-image-1")  # example model
        url = resp.data[0].url
        await interaction.followup.send(f"🖼️ Generated Image:\n{url}")
    except Exception as e:
        print("Grok Imagine Image error:", e)
        await interaction.followup.send("⚠️ Grok Imagine Image failed.")

# -------------------------------
# Grok Imagine Video
# -------------------------------
@tree.command(name="imagine_video", description="🎥 Grok Imagine Video")
async def imagine_video(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        resp = ai.videos.generate(prompt=prompt, model="grok-video-1")  # example model
        url = resp.data[0].url
        await interaction.followup.send(f"🎥 Generated Video:\n{url}")
    except Exception as e:
        print("Grok Imagine Video error:", e)
        await interaction.followup.send("⚠️ Grok Imagine Video failed.")

# -------------------------------
# Economy Commands
# -------------------------------
@tree.command(name="balance", description="🎮 Check your coin balance")
async def balance(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    await interaction.response.send_message(f"💰 Balance: {get_balance(uid)} coins")

@tree.command(name="daily", description="🎁 Claim daily reward")
async def daily(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    reward = 100
    await interaction.response.send_message(f"🎁 You got {reward} coins! Balance: {update_balance(uid,reward)}")

# -------------------------------
# Shop Commands
# -------------------------------
@tree.command(name="shop", description="🛒 View shop")
async def shop(interaction: discord.Interaction):
    cursor.execute("SELECT item, price FROM shop")
    items = cursor.fetchall()
    msg = "🛒 **Shop Items:**\n"
    for item, price in items:
        msg+=f"{item} - {price} coins\n"
    await interaction.response.send_message(msg)

@tree.command(name="buy", description="🛒 Buy an item")
async def buy(interaction: discord.Interaction, item: str):
    uid = str(interaction.user.id)
    cursor.execute("SELECT price FROM shop WHERE item=?", (item,))
    row = cursor.fetchone()
    if not row: return await interaction.response.send_message("⚠️ Item not found")
    price=row[0]
    if get_balance(uid)<price: return await interaction.response.send_message("⚠️ Not enough coins")
    update_balance(uid,-price)
    await interaction.response.send_message(f"✅ You bought {item}!")

# -------------------------------
# Leaderboard
# -------------------------------
@tree.command(name="leaderboard", description="🏆 Top users")
async def leaderboard(interaction: discord.Interaction):
    cursor.execute("SELECT user_id,balance FROM users ORDER BY balance DESC LIMIT 10")
    top=cursor.fetchall()
    msg="🏆 **Leaderboard:**\n"
    for i,(uid,b) in enumerate(top,1):
        msg+=f"#{i} - <@{uid}> : {b} coins\n"
    await interaction.response.send_message(msg)

# -------------------------------
# Admin Dashboard
# -------------------------------
@tree.command(name="admin", description="🔒 Admin Panel")
async def admin(interaction: discord.Interaction, password: str):
    if password!=ADMIN_PASSWORD:
        return await interaction.response.send_message("⚠️ Wrong password!")
    cursor.execute("SELECT item,price FROM shop")
    items=cursor.fetchall()
    msg="**Admin Dashboard:**\nShop Items:\n"
    for item,price in items:
        msg+=f"{item} - {price}\n"
    await interaction.response.send_message(msg)

# -------------------------------
# Run Bot
# -------------------------------
client.run(DISCORD_TOKEN)
