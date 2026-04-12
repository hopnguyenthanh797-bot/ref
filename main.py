from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityCustomEmoji

API_ID = 36437338
API_HASH = "18d34c7efc396d277f3db62baa078efc"
BOT_TOKEN = "8281748233:AAFCVhG3-LBvG_wAli70gRLbfSCOf7fzqTA" # <--- THAY TOKEN CỦA BẠN VÀO ĐÂY

# Bật parse_mode html để hỗ trợ thẻ <tg-emoji>
bot = TelegramClient('test_session_emoji', API_ID, API_HASH)
bot.parse_mode = 'html'

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("👋 Chào bạn! Hãy thử gửi một **Emoji Động Premium** vào đây để kiểm tra nhé!")

@bot.on(events.NewMessage())
async def handler(event):
    if event.message.text == '/start':
        return
        
    has_custom_emoji = False
    if event.message.entities:
        for ent in event.message.entities:
            if isinstance(ent, MessageEntityCustomEmoji):
                has_custom_emoji = True
                doc_id = ent.document_id
                # Lấy icon tĩnh làm dự phòng (fallback)
                fallback = event.message.text[ent.offset:ent.offset+ent.length]
                
                # Ép bot gửi lại bằng mã HTML
                html_text = f'🎉 Thành công! Đây là Emoji của bạn: <tg-emoji emoji-id="{doc_id}">{fallback}</tg-emoji>'
                await event.reply(html_text)
                return
    
    if not has_custom_emoji:
        await event.reply("❌ Tin nhắn này không chứa Emoji Premium nào, hoặc API trên máy không bắt được ID.")

print("--- BOT TEST EMOJI ĐANG CHẠY ---")
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()

