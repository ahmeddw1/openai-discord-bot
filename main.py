import discord
from discord import app_commands
import os
import sqlite3
import random
from flask import Flask, render_template_string, request, redirect, session
from threading import Thread
from openai import OpenAI, RateLimitError

# =====================
# ENV
# =====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

ai = OpenAI(api_key=OPENAI_KEY)

# =====================
# DATABASE
# =====================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS memory (user_id TEXT, message TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS economy (user_id TEXT PRIMARY KEY, balance INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS inventory (user_id TEXT, item TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cooldowns (user_id TEXT, command TEXT, timestamp INTEGER)")
conn.commit()

# =====================
# ECONOMY FUNCTIONS
# =====================
def get_balance(user_id):
    cursor.execute("SELECT balance FROM economy WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute("INSERT INTO economy VALUES (?,?)", (user_id, 0))
    conn.commit()
    return 0

def update_balance(user_id, amount):
    bal = get_balance(user_id)
    new_bal = bal + amount
    cursor.execute("UPDATE economy SET balance=? WHERE user_id=?", (new_bal, user_id))
    conn.commit()
    return new_bal

# =====================
# MEMORY
# =====================
def save_memory(user_id, message):
    cursor.execute("INSERT INTO memory VALUES (?,?)", (user_id, message))
    conn.commit()

def get_memory(user_id):
    cursor.execute("SELECT message FROM memory WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    return "\n".join([r[0] for r in rows[-5:]])

# =====================
# COOLDOWN
# =====================
import time
COOLDOWN_SECONDS = 10

def check_cooldown(user_id, command):
    cursor.execute("SELECT timestamp FROM cooldowns WHERE user_id=? AND command=?", (user_id, command))
    row = cursor.fetchone()
    now = int(time.time())
    if row:
        last = row[0]
        if now - last < COOLDOWN_SECONDS:
            return COOLDOWN_SECONDS - (now - last)
    cursor.execute("INSERT OR REPLACE INTO cooldowns VALUES (?,?,?)", (user_id, command, now))
    conn.commit()
    return 0

# =====================
# DISCORD BOT
# =====================
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# =====================
# AI CHAT COMMAND
# =====================
AI_COST = 50  # coins per AI command

@tree.command(name="chat", description="Talk to AI (costs coins)")
async def chat(interaction: discord.Interaction, message: str):
    user_id = str(interaction.user.id)
    if get_balance(user_id) < AI_COST:
        await interaction.response.send_message(f"⚠️ Not enough coins. You need {AI_COST} coins to use AI.", ephemeral=True)
        return

    cd = check_cooldown(user_id, "chat")
    if cd > 0:
        await interaction.response.send_message(f"⏱ Cooldown active. Try again in {cd}s.", ephemeral=True)
        return

    await interaction.response.defer()
    try:
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a smart gaming AI assistant."},
                {"role": "user", "content": message}
            ]
        )
        reply = response.choices[0].message.content
        update_balance(user_id, -AI_COST)
        await interaction.followup.send(embed=discord.Embed(
            title=f"🧠 AI Chat (-{AI_COST} coins)",
            description=reply,
            color=discord.Color.blue()
        ))
    except RateLimitError:
        await interaction.followup.send("⚠️ AI quota exceeded. Try again later.")
    except Exception as e:
        await interaction.followup.send("❌ AI error occurred.")
        print(e)

# =====================
# AI CODE COMMAND
# =====================
CODE_COST = 75

@tree.command(name="code", description="Generate code using AI (costs coins)")
async def code(interaction: discord.Interaction, language: str, prompt: str):
    user_id = str(interaction.user.id)
    if get_balance(user_id) < CODE_COST:
        await interaction.response.send_message(f"⚠️ Not enough coins. You need {CODE_COST} coins.", ephemeral=True)
        return

    cd = check_cooldown(user_id, "code")
    if cd > 0:
        await interaction.response.send_message(f"⏱ Cooldown active. Try again in {cd}s.", ephemeral=True)
        return

    await interaction.response.defer()
    memory = get_memory(user_id)
    try:
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are an expert programmer. Return only clean {language} code."},
                {"role": "user", "content": f"Context:\n{memory}\n\nRequest:\n{prompt}"}
            ]
        )
        result = response.choices[0].message.content
        save_memory(user_id, prompt)
        update_balance(user_id, -CODE_COST)

        file_name = f"generated.{language}"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(result)

        await interaction.followup.send(embed=discord.Embed(
            title=f"💻 AI Code (-{CODE_COST} coins)",
            description="Your file is attached.",
            color=discord.Color.purple()
        ), file=discord.File(file_name))
    except RateLimitError:
        await interaction.followup.send("⚠️ AI quota exceeded. Try again later.")
    except Exception as e:
        await interaction.followup.send("❌ AI error occurred.")
        print(e)

# =====================
# ECONOMY COMMANDS
# =====================
@tree.command(name="balance", description="Check balance")
async def balance(interaction: discord.Interaction):
    bal = get_balance(str(interaction.user.id))
    await interaction.response.send_message(f"💰 You have {bal} coins")

@tree.command(name="daily", description="Claim daily reward")
async def daily(interaction: discord.Interaction):
    reward = 100
    new_bal = update_balance(str(interaction.user.id), reward)
    await interaction.response.send_message(f"🎁 You received {reward} coins! Balance: {new_bal}")

@tree.command(name="work", description="Work for coins")
async def work(interaction: discord.Interaction):
    earned = random.randint(50, 200)
    new_bal = update_balance(str(interaction.user.id), earned)
    await interaction.response.send_message(f"🎮 You earned {earned} coins! Balance: {new_bal}")

# =====================
# SHOP
# =====================
SHOP_ITEMS = {"VIP":500, "Sword":300, "Shield":250, "LootBox":400}

@tree.command(name="shop", description="View shop")
async def shop(interaction: discord.Interaction):
    desc = "\n".join([f"**{i}** — {p} coins" for i,p in SHOP_ITEMS.items()])
    await interaction.response.send_message(embed=discord.Embed(
        title="🛒 Shop",
        description=desc,
        color=discord.Color.green()
    ))

@tree.command(name="buy", description="Buy item")
async def buy(interaction: discord.Interaction, item: str):
    user_id = str(interaction.user.id)
    if item not in SHOP_ITEMS:
        await interaction.response.send_message("❌ Item not found")
        return
    price = SHOP_ITEMS[item]
    if get_balance(user_id) < price:
        await interaction.response.send_message("❌ Not enough coins")
        return
    update_balance(user_id, -price)
    cursor.execute("INSERT INTO inventory VALUES (?,?)", (user_id, item))
    conn.commit()
    await interaction.response.send_message(f"✅ You bought {item}!")

# =====================
# LEADERBOARD
# =====================
@tree.command(name="leaderboard", description="Top players")
async def leaderboard(interaction: discord.Interaction):
    cursor.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT 10")
    top = cursor.fetchall()
    desc = "\n".join([f"#{i+1} — <@{uid}> : {bal} coins" for i,(uid,bal) in enumerate(top)])
    await interaction.response.send_message(embed=discord.Embed(
        title="🏆 Leaderboard",
        description=desc if desc else "No data yet.",
        color=discord.Color.gold()
    ))

# =====================
# FLASK DASHBOARD
# =====================
app = Flask(__name__)
app.secret_key = "supersecret"

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form.get("username")==ADMIN_USERNAME and request.form.get("password")==ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/dashboard")
    return """
    <h2>🔒 Admin Login</h2>
    <form method="POST">
    <input name="username" placeholder="Username"><br>
    <input name="password" type="password" placeholder="Password"><br>
    <button type="submit">Login</button>
    </form>
    """

@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect("/")
    cursor.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC")
    data = cursor.fetchall()
    html = "<h1>🔥 Economy Data</h1><a href='/logout'>Logout</a>"
    for row in data:
        html += f"<p>{row[0]} : {row[1]} coins</p>"
    return html

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

def run_web():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_web).start()
client.run(DISCORD_TOKEN)
