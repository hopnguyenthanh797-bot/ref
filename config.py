import os

class Config:
    # Render sẽ tự cấp PORT, nếu test local thì dùng 10000
    PORT = int(os.environ.get("PORT", 10000))
    
    # Token bot của sếp
    BOT_TOKEN = "8743099227:AAGXQH4f9SUndwnCjahZ9b_Tsa-yQUGOq4g"
    
    # API của trumsmm
    TRUMSMM_API_KEY = "751f5288302b02735a318e2cedf4689e"
    TRUMSMM_URL = "http://api.trumsmm.com/api"
    
    # Thông tin Supabase
    SUPABASE_URL = "https://utpicxugychrwlskmxxn.supabase.co"
    SUPABASE_KEY = "sb_publishable_KL4JPyhuQuxuHPLDaJwCzg_KpqrcfkP"
    
    # ID của sếp để xài lệnh Admin
    ADMIN_IDS = [7816353760]

config = Config()

