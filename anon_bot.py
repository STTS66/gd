import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ─── НАСТРОЙКИ (переменные окружения задаются на Render) ──────────────────────
BOT_TOKEN  = os.environ["BOT_TOKEN"]
OWNER_ID   = int(os.environ["OWNER_ID"])
OWNER_TAG  = os.environ.get("OWNER_TAG", "@STTS84")
PORT       = int(os.environ.get("PORT", "8000"))
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
pending_replies: dict[int, int] = {}


# ── Минимальный HTTP-сервер для Render (Web Service) ───────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass  # отключаем логи HTTP

def run_http():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text(
            "👑 Вы владелец бота.\n"
            "Чтобы ответить — просто нажмите Reply на пересланное сообщение."
        )
        return

    await update.message.reply_text(
        f"👋 Привет!\n"
        f"Этот бот позволяет отправлять {OWNER_TAG} анонимные сообщения.\n\n"
        f"💬 Отправляйте любое сообщение: текст, фото, видео, документ, аудио, голосовое, стикер или GIF.\n"
        f"📌 Все ваши сообщения будут доставлены анонимно: он не будет знать, кто Вы."
    )


# ── Входящие сообщения от пользователей ────────────────────────────────────────
async def handle_user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg  = update.message

    if user.id == OWNER_ID:
        await handle_owner_reply(update, ctx)
        return

    caption = "📨 <b>Новое анонимное сообщение:</b>"
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
    # Запускаем HTTP-сервер в фоне (нужен для Render Web Service)
    threading.Thread(target=run_http, daemon=True).start()
    print(f"HTTP-сервер запущен на порту {PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
