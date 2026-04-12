from telethon import TelegramClient, events

# Thay bằng Token Bot của bạn
API_ID = 36437338
API_HASH = "18d34c7efc396d277f3db62baa078efc"
BOT_TOKEN = "8281748233:AAFCVhG3-LBvG_wAli70gRLbfSCOf7fzqTA" 

# Bật chế độ HTML để bot dùng được Emoji Premium
bot = TelegramClient('bot_test_sender', API_ID, API_HASH)
bot.parse_mode = 'html'

@bot.on(events.NewMessage())
async def handler(event):
    if event.text.startswith('/start'):
        await event.reply("👋 Gửi cho tôi 1 Emoji Động Premium bất kỳ, tôi sẽ dùng nó để gửi lại một tin nhắn mới cho bạn xem!")
        return
        
    # Tìm xem trong tin nhắn bạn gửi có Emoji Động không
    if hasattr(event.message, 'entities') and event.message.entities:
        for ent in event.message.entities:
            if hasattr(ent, 'document_id'): # Nếu tìm thấy ID của Emoji Premium
                doc_id = ent.document_id
                fallback = event.message.text[ent.offset : ent.offset + ent.length]
                
                # CHÍNH BOT SẼ TỰ TẠO TIN NHẮN MỚI CÓ CHỨA EMOJI NÀY VÀ GỬI RA
                tin_nhan_test = f"🤖 <b>TEST TỪ BOT:</b> Đây là icon <tg-emoji emoji-id=\"{doc_id}\">{fallback}</tg-emoji> bot tự gửi, xem nó có chớp nháy không nhé!"
                
                await event.respond(tin_nhan_test)
                return
    
    await event.reply("❌ Không tìm thấy mã Emoji Premium. Bạn hãy gửi một icon động phát sáng xem sao!")

print("--- BOT TEST ĐANG CHẠY ---")
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
