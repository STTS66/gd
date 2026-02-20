import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.environ["BOT_TOKEN"]
OWNER_ID   = int(os.environ["OWNER_ID"])
OWNER_TAG  = os.environ.get("OWNER_TAG", "@STTS84")
PORT       = int(os.environ.get("PORT", "8000"))
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)

pending_replies: dict[int, int] = {}   # msg_id → user_id
known_users:     set[int]       = set()  # все user_id кто писал боту
banned_users:    set[int]       = set()  # забаненные user_id


# ── HTTP-сервер для Render ─────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args): pass

def run_http():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == OWNER_ID:
        await update.message.reply_text(
            "👑 Вы владелец бота.\n\n"
            "📋 Команды:\n"
            "/ban <id> — заблокировать пользователя\n"
            "/unban <id> — разблокировать пользователя\n"
            "/broadcast <текст> — рассылка всем пользователям\n"
            "/users — список всех пользователей\n\n"
            "Чтобы ответить — нажмите Reply на сообщение."
        )
        return

    known_users.add(user.id)
    await update.message.reply_text(
        f"👋 Привет!\n"
        f"Этот бот позволяет отправлять {OWNER_TAG} анонимные сообщения.\n\n"
        f"💬 Отправляйте любое сообщение: текст, фото, видео, документ, аудио, голосовое, стикер или GIF.\n"
        f"📌 Все ваши сообщения будут доставлены анонимно: он не будет знать, кто Вы."
    )


# ── /ban ───────────────────────────────────────────────────────────────────────
async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not ctx.args:
        await update.message.reply_text("Использование: /ban <user_id>")
        return
    try:
        uid = int(ctx.args[0])
        banned_users.add(uid)
        await update.message.reply_text(f"🚫 Пользователь {uid} заблокирован.")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID.")


# ── /unban ─────────────────────────────────────────────────────────────────────
async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not ctx.args:
        await update.message.reply_text("Использование: /unban <user_id>")
        return
    try:
        uid = int(ctx.args[0])
        banned_users.discard(uid)
        await update.message.reply_text(f"✅ Пользователь {uid} разблокирован.")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID.")


# ── /users ─────────────────────────────────────────────────────────────────────
async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not known_users:
        await update.message.reply_text("Пока никто не писал боту.")
        return
    lines = []
    for uid in known_users:
        status = "🚫" if uid in banned_users else "✅"
        lines.append(f"{status} <code>{uid}</code>")
    await update.message.reply_text(
        f"👥 Пользователи ({len(known_users)}):\n" + "\n".join(lines),
        parse_mode="HTML"
    )


# ── /broadcast ─────────────────────────────────────────────────────────────────
async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not ctx.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return

    text = " ".join(ctx.args)
    msg_text = f"📢 <b>Сообщение от {OWNER_TAG}:</b>\n\n{text}"

    ok, fail = 0, 0
    for uid in known_users:
        if uid in banned_users:
            continue
        try:
            await ctx.bot.send_message(uid, msg_text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1

    await update.message.reply_text(
        f"📊 Рассылка завершена:\n✅ Доставлено: {ok}\n❌ Ошибок: {fail}"
    )


# ── Входящие сообщения от пользователей ────────────────────────────────────────
async def handle_user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg  = update.message

    if user.id == OWNER_ID:
        await handle_owner_reply(update, ctx)
        return

    # запоминаем пользователя
    known_users.add(user.id)

    # проверка бана
    if user.id in banned_users:
        await msg.reply_text("🚫 Вы заблокированы и не можете отправлять сообщения.")
        return

    caption = f"📨 <b>Новое анонимное сообщение:</b>\n<i>ID: <code>{user.id}</code></i>"
    sent = None

    if msg.text:
        sent = await ctx.bot.send_message(OWNER_ID, f"{caption}\n\n{msg.text}", parse_mode="HTML")
    elif msg.photo:
        sent = await ctx.bot.send_photo(OWNER_ID, msg.photo[-1].file_id, caption=caption, parse_mode="HTML")
    elif msg.video:
        sent = await ctx.bot.send_video(OWNER_ID, msg.video.file_id, caption=caption, parse_mode="HTML")
    elif msg.document:
        sent = await ctx.bot.send_document(OWNER_ID, msg.document.file_id, caption=caption, parse_mode="HTML")
    elif msg.audio:
        sent = await ctx.bot.send_audio(OWNER_ID, msg.audio.file_id, caption=caption, parse_mode="HTML")
    elif msg.voice:
        sent = await ctx.bot.send_voice(OWNER_ID, msg.voice.file_id, caption=caption, parse_mode="HTML")
    elif msg.sticker:
        await ctx.bot.send_message(OWNER_ID, caption, parse_mode="HTML")
        sent = await ctx.bot.send_sticker(OWNER_ID, msg.sticker.file_id)
    elif msg.animation:
        sent = await ctx.bot.send_animation(OWNER_ID, msg.animation.file_id, caption=caption, parse_mode="HTML")
    elif msg.video_note:
        await ctx.bot.send_message(OWNER_ID, caption, parse_mode="HTML")
        sent = await ctx.bot.send_video_note(OWNER_ID, msg.video_note.file_id)
    else:
        await msg.reply_text("⚠️ Этот тип сообщения не поддерживается.")
        return

    if sent:
        pending_replies[sent.message_id] = user.id

    await msg.reply_text("✅ Ваше сообщение успешно отправлено анонимно!")


# ── Ответ владельца ─────────────────────────────────────────────────────────────
async def handle_owner_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg.reply_to_message:
        return

    original_id = msg.reply_to_message.message_id
    target_user = pending_replies.get(original_id)

    if not target_user:
        await msg.reply_text("❌ Не могу определить получателя. Ответьте (Reply) на сообщение бота.")
        return

    prefix = "📩 <b>Анонимный ответ:</b>\n\n"

    try:
        if msg.text:
            await ctx.bot.send_message(target_user, prefix + msg.text, parse_mode="HTML")
        elif msg.photo:
            await ctx.bot.send_photo(target_user, msg.photo[-1].file_id, caption=prefix, parse_mode="HTML")
        elif msg.video:
            await ctx.bot.send_video(target_user, msg.video.file_id, caption=prefix, parse_mode="HTML")
        elif msg.document:
            await ctx.bot.send_document(target_user, msg.document.file_id, caption=prefix, parse_mode="HTML")
        elif msg.audio:
            await ctx.bot.send_audio(target_user, msg.audio.file_id, caption=prefix, parse_mode="HTML")
        elif msg.voice:
            await ctx.bot.send_voice(target_user, msg.voice.file_id, caption=prefix, parse_mode="HTML")
        elif msg.sticker:
            await ctx.bot.send_message(target_user, prefix, parse_mode="HTML")
            await ctx.bot.send_sticker(target_user, msg.sticker.file_id)
        elif msg.animation:
            await ctx.bot.send_animation(target_user, msg.animation.file_id, caption=prefix, parse_mode="HTML")
        else:
            await msg.reply_text("⚠️ Этот тип ответа не поддерживается.")
            return

        await msg.reply_text("✅ Ответ доставлен анонимно.")
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка при отправке: {e}")


# ── Запуск ──────────────────────────────────────────────────────────────────────
def main():
    threading.Thread(target=run_http, daemon=True).start()
    print(f"HTTP-сервер запущен на порту {PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("ban",       ban_cmd))
    app.add_handler(CommandHandler("unban",     unban_cmd))
    app.add_handler(CommandHandler("users",     users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
