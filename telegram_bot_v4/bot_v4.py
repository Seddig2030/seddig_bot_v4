# -*- coding: utf-8 -*-
"""
بوت تلجرام للردود التلقائية - الإصدار v4
قابل للتعديل بالكامل عن طريق config.json فقط (أو عبر المحرر editor.py).

الجديد في v4:
- أزرار متداخلة بلا حدود (زر داخل زر داخل زر ... إلخ) عبر ربط reply_key بمفتاح
  آخر داخل callback_responses، وهذا المفتاح نفسه يقدر يملك أزرار توديه لمفاتيح
  تانية، وهكذا بأي عمق تحبه.
- كل رد (رئيسي أو رد زر أو ترحيب/وداع) يقدر يحمل صورة أو فيديو أو صوت أو
  ملف صوتي (voice) أو مستند أو GIF، مو بس نص.
- توقيع تلقائي يُضاف بآخر كل رسالة يرسلها البوت (مثل: 𝑺𝑬𝑫𝑫𝑰𝑮).

طريقة الإضافة:
- لإضافة رد جديد: أضف عنصر جديد داخل "responses" في config.json
- لإضافة زر: أضف عنصر داخل "buttons" يحتوي على "text" + ("reply_key" أو "url")
- لإضافة رد لزر: أضف عنصر جديد داخل "callback_responses" بنفس الاسم (reply_key)
- لإضافة زر يفتح قائمة فرعية: خلي reply_key يشاور على مفتاح آخر بداخل
  callback_responses، وهذاك المفتاح فيه أزراره الخاصة (وهكذا بلا حدود عمق).
- لإضافة وسائط لأي رد: أضف "media": {"type": "photo|video|audio|voice|document|animation",
  "path": "media/xxx.jpg"}  (أو "file_id" لو عندك file_id جاهز من تلجرام).
"""

import json
import re
import logging
import difflib
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# تشكيل عربي يتم إزالته عند المطابقة لتسهيل التشابه بين الكلمات
ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]")

# طرق الإرسال المتاحة لكل نوع وسائط
MEDIA_SEND_METHODS = {
    "photo": "reply_photo",
    "video": "reply_video",
    "audio": "reply_audio",
    "voice": "reply_voice",
    "document": "reply_document",
    "animation": "reply_animation",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()


def normalize(text: str) -> str:
    """تنظيف النص العربي لتسهيل المطابقة"""
    if not text:
        return ""
    text = text.strip().lower()
    text = ARABIC_DIACRITICS.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_match(user_text: str, triggers: list, threshold: float) -> bool:
    """مطابقة غير صارمة: تحتوي / تشابه نسبي، وليس تطابق حرفي كامل"""
    norm_text = normalize(user_text)
    if not norm_text:
        return False
    for trig in triggers:
        norm_trig = normalize(trig)
        if not norm_trig:
            continue
        if norm_trig in norm_text or norm_text in norm_trig:
            return True
        ratio = difflib.SequenceMatcher(None, norm_trig, norm_text).ratio()
        if ratio >= threshold:
            return True
        for word in norm_text.split():
            if difflib.SequenceMatcher(None, norm_trig, word).ratio() >= threshold:
                return True
    return False


def with_signature(text: str) -> str:
    """يضيف التوقيع التلقائي بآخر أي نص يرسله البوت، إن كان مفعّلاً بالإعدادات"""
    text = text or ""
    signature = CONFIG.get("settings", {}).get("signature", "")
    if not signature:
        return text
    return f"{text}\n\n{signature}"


def build_inline_keyboard(buttons_config):
    """
    يبني InlineKeyboardMarkup من إعداد الأزرار.
    يدعم:
      - مصفوفة من مصفوفات (rows): [[btn, btn], [btn]]
      - مصفوفة مسطحة من الأزرار: [btn, btn] (كل زر في صف منفرد)
      - مصفوفة فارغة أو None
    كل زر "reply_key" يقدر يشاور على مفتاح آخر بداخل callback_responses
    وهذاك بدوره يقدر يملك أزراره الخاصة => قوائم متداخلة بأي عمق تحبه.
    """
    if not buttons_config:
        return None

    rows = []

    if buttons_config and isinstance(buttons_config[0], list):
        nested = buttons_config
    elif buttons_config and isinstance(buttons_config[0], dict):
        nested = [[btn] for btn in buttons_config]
    else:
        return None

    for row in nested:
        if not row:
            continue
        btn_row = []
        for btn in row:
            if not isinstance(btn, dict):
                continue
            text = btn.get("text", "زر")
            if "url" in btn and btn["url"]:
                btn_row.append(InlineKeyboardButton(text, url=btn["url"]))
            else:
                key = btn.get("reply_key", "")
                btn_row.append(InlineKeyboardButton(text, callback_data=f"key:{key}"))
        if btn_row:
            rows.append(btn_row)

    return InlineKeyboardMarkup(rows) if rows else None


def build_reply_keyboard(buttons_config):
    """يبني ReplyKeyboardMarkup (الشريط السفلي الثابت) من start_keyboard بالكونفيج"""
    if not buttons_config:
        return None
    rows = []
    for row in buttons_config:
        if isinstance(row, list):
            rows.append([KeyboardButton(text) for text in row if text])
        elif isinstance(row, str) and row:
            rows.append([KeyboardButton(row)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True) if rows else None


def resolve_media_path(media: dict):
    """يرجع (kwarg_value, send_method) لإرسال الوسائط: إما ملف محلي أو file_id/رابط جاهز"""
    if not media or not isinstance(media, dict):
        return None, None
    media_type = media.get("type")
    if media_type not in MEDIA_SEND_METHODS:
        return None, None

    if media.get("file_id"):
        return media["file_id"], MEDIA_SEND_METHODS[media_type]

    path = media.get("path")
    if not path:
        return None, None
    full_path = os.path.join(BASE_DIR, path)
    if not os.path.exists(full_path):
        logger.warning("ملف الوسائط غير موجود: %s", full_path)
        return None, None
    return full_path, MEDIA_SEND_METHODS[media_type]


async def send_item(message_or_query, text: str, media: dict, keyboard, edit: bool = False):
    """
    يرسل رد (نص أو وسائط) مع الأزرار، ويضيف التوقيع تلقائياً.
    - message_or_query: كائن update.message (لرسالة جديدة) أو update.callback_query (لتعديل/رد على زر)
    - edit=True: يحاول تعديل الرسالة الحالية بدل إرسال رسالة جديدة (يُستخدم فقط مع الأزرار،
      ويعمل فقط إذا كانت الرسالة الحالية نصية والرد الجديد نصي أيضاً؛ غير ذلك يرسل رسالة جديدة).
    """
    final_text = with_signature(text)
    media_value, send_method = resolve_media_path(media)

    is_callback = hasattr(message_or_query, "message")  # CallbackQuery has .message
    target_message = message_or_query.message if is_callback else message_or_query

    if media_value and send_method:
        # إرسال وسائط: نرسل رسالة جديدة دائماً (تعديل نوع رسالة موجودة لنوع مختلف غير مدعوم)
        if is_callback:
            try:
                await message_or_query.edit_message_reply_markup(reply_markup=None)
            except BadRequest:
                pass
        send_func = getattr(target_message, send_method)
        kwargs = {"caption": final_text, "reply_markup": keyboard}

        def _open(value):
            return open(value, "rb") if isinstance(value, str) and os.path.exists(value) else value

        file_arg = _open(media_value)
        field_name = {
            "reply_photo": "photo",
            "reply_video": "video",
            "reply_audio": "audio",
            "reply_voice": "voice",
            "reply_document": "document",
            "reply_animation": "animation",
        }[send_method]
        kwargs[field_name] = file_arg
        try:
            await send_func(**kwargs)
        finally:
            if hasattr(file_arg, "close"):
                file_arg.close()
        return

    # لا يوجد وسائط -> رد نصي فقط
    if edit and is_callback:
        try:
            await message_or_query.edit_message_text(final_text, reply_markup=keyboard)
            return
        except BadRequest:
            pass  # الرسالة الأصلية كانت وسائط أو فشل التعديل لأي سبب -> نكمل تحت لإرسال رسالة جديدة

    if is_callback:
        try:
            await message_or_query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        await target_message.reply_text(final_text, reply_markup=keyboard)
    else:
        await target_message.reply_text(final_text, reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start - يرسل رسالة الترحيب الرئيسية مع الأزرار"""
    cfg = CONFIG.get("start", {})
    text = cfg.get("text", f"✅ البوت يعمل الآن.\nاسم البوت: {CONFIG['settings'].get('bot_name', 'بوتي')}")
    reply_kb = build_reply_keyboard(cfg.get("reply_keyboard"))
    inline_kb = build_inline_keyboard(cfg.get("buttons"))
    await send_item(update.message, text, cfg.get("media"), inline_kb or reply_kb)


async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CONFIG
    try:
        CONFIG = load_config()
        await update.message.reply_text(with_signature("♻️ تم إعادة تحميل config.json بنجاح."))
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في تحميل الملف:\n{e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    threshold = CONFIG["settings"].get("fuzzy_threshold", 0.55)

    for item in CONFIG.get("responses", []):
        triggers = item.get("triggers", [])
        if is_match(text, triggers, threshold):
            keyboard = build_inline_keyboard(item.get("buttons"))
            await send_item(update.message, item.get("reply", ""), item.get("media"), keyboard)
            return


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("key:"):
        return
    key = data[len("key:"):]
    item = CONFIG.get("callback_responses", {}).get(key)
    if not item:
        await query.message.reply_text(with_signature("⚠️ لم يتم العثور على رد لهذا الزر."))
        return
    keyboard = build_inline_keyboard(item.get("buttons"))
    await send_item(query, item.get("reply", ""), item.get("media"), keyboard, edit=True)


async def get_profile_photo_file(bot, user_id):
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            return photos.photos[0][-1].file_id
    except Exception as e:
        logger.warning(f"تعذر جلب صورة البروفايل: {e}")
    return None


def get_display_name(user):
    return user.full_name or user.first_name or user.username or "صديقنا"


async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = CONFIG.get("welcome", {})
    if not cfg.get("enabled", True):
        return
    for user in update.message.new_chat_members:
        if user.is_bot:
            continue
        name = get_display_name(user)
        caption = cfg.get("text", "أهلاً {name}").format(
            name=name, username=f"@{user.username}" if user.username else name
        )
        keyboard = build_inline_keyboard(cfg.get("buttons"))
        final_caption = with_signature(caption)

        media = cfg.get("media")
        media_value, send_method = resolve_media_path(media) if media else (None, None)

        if media_value and send_method:
            send_func = getattr(update.message, send_method)
            field_name = {
                "reply_photo": "photo", "reply_video": "video", "reply_audio": "audio",
                "reply_voice": "voice", "reply_document": "document", "reply_animation": "animation",
            }[send_method]
            f = open(media_value, "rb") if os.path.exists(str(media_value)) else media_value
            try:
                await send_func(**{field_name: f, "caption": final_caption, "reply_markup": keyboard})
            finally:
                if hasattr(f, "close"):
                    f.close()
            continue

        # سلوك افتراضي قديم: صورة البروفايل أو صورة افتراضية إن لم يحدَّد media
        photo_id = await get_profile_photo_file(context.bot, user.id)
        default_photo = os.path.join(BASE_DIR, cfg.get("default_photo", "media/default.jpg"))
        if photo_id:
            await update.message.reply_photo(photo=photo_id, caption=final_caption, reply_markup=keyboard)
        elif os.path.exists(default_photo):
            with open(default_photo, "rb") as f:
                await update.message.reply_photo(photo=f, caption=final_caption, reply_markup=keyboard)
        else:
            await update.message.reply_text(final_caption, reply_markup=keyboard)


async def farewell_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = CONFIG.get("farewell", {})
    if not cfg.get("enabled", True):
        return
    user = update.message.left_chat_member
    if not user or user.is_bot:
        return
    name = get_display_name(user)
    caption = cfg.get("text", "وداعاً {name}").format(
        name=name, username=f"@{user.username}" if user.username else name
    )
    keyboard = build_inline_keyboard(cfg.get("buttons"))
    final_caption = with_signature(caption)

    media = cfg.get("media")
    media_value, send_method = resolve_media_path(media) if media else (None, None)
    if media_value and send_method:
        send_func = getattr(update.message, send_method)
        field_name = {
            "reply_photo": "photo", "reply_video": "video", "reply_audio": "audio",
            "reply_voice": "voice", "reply_document": "document", "reply_animation": "animation",
        }[send_method]
        f = open(media_value, "rb") if os.path.exists(str(media_value)) else media_value
        try:
            await send_func(**{field_name: f, "caption": final_caption, "reply_markup": keyboard})
        finally:
            if hasattr(f, "close"):
                f.close()
        return

    photo_id = await get_profile_photo_file(context.bot, user.id)
    default_photo = os.path.join(BASE_DIR, cfg.get("default_photo", "media/default.jpg"))
    if photo_id:
        await update.message.reply_photo(photo=photo_id, caption=final_caption, reply_markup=keyboard)
    elif os.path.exists(default_photo):
        with open(default_photo, "rb") as f:
            await update.message.reply_photo(photo=f, caption=final_caption, reply_markup=keyboard)
    else:
        await update.message.reply_text(final_caption, reply_markup=keyboard)


def main():
    token = CONFIG["settings"].get("token", "")
    if not token or "ضع_التوكن_هنا" in token:
        print("⚠️  لم يتم وضع توكن البوت في config.json (settings.token). عدّل الملف وأعد المحاولة.")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, farewell_handler))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 البوت (v4) يعمل الآن... اضغط Ctrl+C للتوقف")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
