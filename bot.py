import discord
from discord.ext import commands, tasks
import scratchattach as scratch3
import random
import string
import os
import time
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SESSION_ID = os.getenv("SESSION_ID")
PROJECT_ID = os.getenv("PROJECT_ID")
GUILD_ID = int(os.getenv("GUILD_ID"))
SCRATCHER_ROLE_NAME = os.getenv("SCRATCHER_ROLE_NAME")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# Scratchログイン
session = scratch3.login_by_id(SESSION_ID, username="p9el")  # usernameは適宜変更
conn = session.connect_project(PROJECT_ID)
user = session.get_linked_user()
print(f"{user.username}でScratchにログインしました")

# {discord_user_id: (scratch_username, code, 発行時刻)}
verify_codes = {}


def generate_code(length=6):
    """ランダムコード生成"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def handle_auth_success(scratch_id, discord_id, guild):
    """認証成功時の処理（SCRATCHER_ROLE_NAMEだけ付与）"""
    with open("auth.txt", "a", encoding="utf-8") as f:
        f.write(f"{scratch_id},{discord_id}\n")

    member = guild.get_member(int(discord_id))
    if not member:
        print(f"[WARN] メンバーが見つかりません: {discord_id}")
        return

    # Scratcherロールを付与
    scratcher_role = discord.utils.get(guild.roles, name=SCRATCHER_ROLE_NAME)
    if scratcher_role:
        try:
            await member.add_roles(scratcher_role)
            print(f"[INFO] Scratcherロールを付与: {member}")
        except discord.Forbidden:
            print(f"[ERROR] Scratcherロールの付与に失敗（権限不足）: {member}")

    # DMで通知
    try:
        await member.send(
            f"🎉 認証完了！\n"
            f"あなたのScratchアカウント『{scratch_id}』が認証されました！\n"
            f"Scratcherロールが付与されました。"
        )
    except discord.Forbidden:
        print(f"[WARN] {member} にDMを送れませんでした。")


@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user} (ID: {bot.user.id})')
    check_comments.start()
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ スラッシュコマンド同期: {len(synced)}個")
    except Exception as e:
        print(f"[ERROR] コマンド同期失敗: {e}")


@bot.tree.command(name="verify", description="Scratchアカウントを認証します", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction, scratch_username: str):
    """Scratch認証用スラッシュコマンド"""
    code = generate_code()
    issued_time = time.time()  # 発行時刻を記録
    verify_codes[interaction.user.id] = (scratch_username, code, issued_time)

    try:
        await interaction.user.send(
            f"✅ 認証コードを生成しました。\n"
            f"⏳ 有効期限: 2分\n"
            f"Scratchで次のコードをコメントしてください： `{code}`\n"
            f"<https://scratch.mit.edu/projects/{PROJECT_ID}>"
        )
        await interaction.response.send_message("📬 認証コードをDMに送りました！", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            "⚠️ DMを送信できませんでした。プライバシー設定をご確認ください。",
            ephemeral=True
        )


@tasks.loop(seconds=10)
async def check_comments():
    """Scratchプロジェクトのコメントを定期的に確認 & 有効期限チェック"""
    current_time = time.time()

    # まず期限切れチェック
    for discord_id, (expected_user, code, issued_time) in list(verify_codes.items()):
        if current_time - issued_time > 120:  # 2分(120秒)経過
            member = bot.get_user(discord_id)
            if member:
                try:
                    await member.send(
                        f"⌛ 認証コード `{code}` の有効期限が切れました。\n"
                        f"もう一度 `/verify` コマンドでやり直してください。"
                    )
                except discord.Forbidden:
                    print(f"[WARN] {member} に期限切れDMを送れませんでした。")
            del verify_codes[discord_id]

    # コメントチェック
    comments = conn.comments()
    for comment in comments:
        content = comment.content
        author = comment.author()
        scratch_username = author.username

        for discord_id, (expected_user, code, issued_time) in list(verify_codes.items()):
            if scratch_username.lower() == expected_user.lower() and code in content:
                guild = bot.get_guild(GUILD_ID)
                await handle_auth_success(scratch_username, discord_id, guild)
                del verify_codes[discord_id]  # 認証成功したらカウントダウン終了
                break

bot.run(DISCORD_TOKEN)
