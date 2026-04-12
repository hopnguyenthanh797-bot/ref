from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityCustomEmoji

# Thông tin API và Token Bot của bạn
API_ID = 36437338
API_HASH = "18d34c7efc396d277f3db62baa078efc"
BOT_TOKEN = "8281748233:AAFCVhG3-LBvG_wAli70gRLbfSCOf7fzqTA" # <--- NHỚ THAY TOKEN CỦA BẠN VÀO ĐÂY NHÉ

# Bật parse_mode html để bot hiểu được thẻ <tg-emoji>
bot = TelegramClient('bot_test_sender', API_ID, API_HASH)
bot.parse_mode = 'html'

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("👋 <b>TEST BOT GỬI EMOJI ĐỘNG</b>\n\nHãy gửi 1 Emoji Premium bất kỳ vào đây, bot sẽ gửi lại chính xác nội dung chứa Emoji đó cho bạn xem!")

@bot.on(events.NewMessage())
async def handler(event):
    if event.text.startswith('/start'):
        return
        
    has_custom_emoji = False
    
    # Kiểm tra xem tin nhắn bạn gửi có chứa Emoji Động hay không
    if hasattr(event.message, 'entities') and event.message.entities:
        for ent in event.message.entities:
            if isinstance(ent, MessageEntityCustomEmoji) or (hasattr(ent, 'document_id') and type(ent).__name__ == 'MessageEntityCustomEmoji'):
                has_custom_emoji = True
                doc_id = ent.document_id
                fallback = event.message.text[ent.offset:ent.offset+ent.length]
                
                # 1. Gửi cho bạn đoạn mã HTML để bạn có thể copy dùng sau này
                html_code_to_copy = f'&lt;tg-emoji emoji-id="{doc_id}"&gt;{fallback}&lt;/tg-emoji&gt;'
                await event.reply(f"📌 <b>Mã HTML của Emoji này là:</b>\n<code>{html_code_to_copy}</code>\n\n<i>(Bạn có thể copy mã này dán thẳng vào code bot nếu muốn fix cứng)</i>")
                
                # 2. BOT CHỦ ĐỘNG GỬI TIN NHẮN CHỨA EMOJI ĐỘNG ĐÓ
                test_msg = f"🔥 <b>Nội dung bot gửi test:</b> Nhìn xem cái icon <tg-emoji emoji-id=\"{doc_id}\">{fallback}</tg-emoji> này có chuyển động không nhé!"
                await event.reply(test_msg)
                return
    
    if not has_custom_emoji:
        await event.reply("❌ Bot không nhận diện được Emoji Premium trong tin nhắn này. Thử gửi 1 icon khác xem sao!")

print("--- BOT TEST ĐANG CHẠY - HÃY VÀO TELEGRAM GỬI LỆNH /start ---")
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
