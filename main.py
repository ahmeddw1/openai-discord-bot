import discord
from discord import app_commands
import os
import sqlite3
import random
from flask import Flask, render_template_string, request, redirect, session
from threading import Thread
from openai import OpenAI

# =========================
# ENV VARIABLES
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

ai = OpenAI(api_key=OPENAI_KEY)

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS memory (user_id TEXT, message TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS economy (user_id TEXT PRIMARY KEY, balance INTEGER)")
conn.commit()

def save_memory(user_id, message):
    cursor.execute("INSERT INTO memory VALUES (?,?)", (user_id, message))
    conn.commit()

def get_memory(user_id):
    cursor.execute("SELECT message FROM memory WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    return "\n".join([r[0] for r in rows[-5:]])

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

# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# ---- AI CODE ----
@tree.command(name="code", description="Generate code")
async def code(interaction: discord.Interaction, language: str, prompt: str):
    await interaction.response.defer()

    memory = get_memory(str(interaction.user.id))

    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are an expert programmer. Return only clean {language} code."},
            {"role": "user", "content": f"Context:\n{memory}\n\nRequest:\n{prompt}"}
        ]
    )

    result = response.choices[0].message.content
    save_memory(str(interaction.user.id), prompt)

    file_name = f"generated.{language}"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(result)

    embed = discord.Embed(
        title="💻 AI Code Generated",
        description="Your file is attached.",
        color=discord.Color.purple()
    )

    await interaction.followup.send(embed=embed, file=discord.File(file_name))

# ---- AI CHAT ----
@tree.command(name="chat", description="Talk to AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()

    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a smart gaming AI assistant."},
            {"role": "user", "content": message}
        ]
    )

    reply = response.choices[0].message.content

    embed = discord.Embed(
        title="🧠 AI Chat",
        description=reply,
        color=discord.Color.blue()
    )

    await interaction.followup.send(embed=embed)

# ---- ECONOMY ----
@tree.command(name="balance", description="Check balance")
async def balance(interaction: discord.Interaction):
    bal = get_balance(str(interaction.user.id))
    await interaction.response.send_message(f"💰 Balance: {bal} coins")

@tree.command(name="daily", description="Daily reward")
async def daily(interaction: discord.Interaction):
    reward = 100
    new_bal = update_balance(str(interaction.user.id), reward)
    await interaction.response.send_message(f"🎁 +{reward} coins! Balance: {new_bal}")

@tree.command(name="work", description="Work for coins")
async def work(interaction: discord.Interaction):
    earned = random.randint(50, 200)
    new_bal = update_balance(str(interaction.user.id), earned)
    await interaction.response.send_message(f"🎮 You earned {earned} coins! Balance: {new_bal}")

# =========================
# FLASK DASHBOARD
# =========================
app = Flask(__name__)
app.secret_key = "supersecret"

login_page = """
<h2>🔒 Admin Login</h2>
<form method="POST">
<input name="username" placeholder="Username"><br>
<input name="password" type="password" placeholder="Password"><br>
<button type="submit">Login</button>
</form>
"""

dashboard_page = """
<h1>🔥 Bot Dashboard</h1>
<a href='/logout'>Logout</a>
<h3>User Memory</h3>
{% for row in data %}
<p><b>{{row[0]}}</b>: {{row[1]}}</p>
{% endfor %}
"""

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/dashboard")
    return render_template_string(login_page)

@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect("/")
    cursor.execute("SELECT * FROM memory")
    data = cursor.fetchall()
    return render_template_string(dashboard_page, data=data)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

def run_web():
    app.run(host="0.0.0.0", port=8080)

# =========================
# START BOTH
# =========================
Thread(target=run_web).start()
client.run(DISCORD_TOKEN)