import asyncio
from supabase import create_client, Client
from config import config

class Database:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # Chạy query Supabase trong thread để không block luồng Async của Bot
    async def get_user(self, user_id: int, full_name: str):
        def _get():
            res = self.client.table('users').select('*').eq('user_id', user_id).execute()
            if not res.data:
                new_user = {
                    'user_id': user_id,
                    'full_name': full_name,
                    'balance': 0,
                    'total_spent': 0
                }
                self.client.table('users').insert(new_user).execute()
                return new_user
            return res.data[0]
        return await asyncio.to_thread(_get)

    async def update_balance(self, user_id: int, amount: int):
        def _update():
            user = self.client.table('users').select('balance').eq('user_id', user_id).execute().data[0]
            new_balance = user['balance'] + amount
            self.client.table('users').update({'balance': new_balance}).eq('user_id', user_id).execute()
            return new_balance
        return await asyncio.to_thread(_update)

    async def add_spent(self, user_id: int, amount: int):
        def _add():
            user = self.client.table('users').select('total_spent').eq('user_id', user_id).execute().data[0]
            self.client.table('users').update({'total_spent': user['total_spent'] + amount}).eq('user_id', user_id).execute()
        return await asyncio.to_thread(_add)

    async def get_markup(self):
        def _get_markup():
            res = self.client.table('settings').select('markup_percent').eq('id', 1).execute()
            if not res.data:
                self.client.table('settings').insert({'id': 1, 'markup_percent': 20}).execute()
                return 20
            return res.data[0]['markup_percent']
        return await asyncio.to_thread(_get_markup)

    async def set_markup(self, percent: int):
        def _set_markup():
            self.client.table('settings').update({'markup_percent': percent}).eq('id', 1).execute()
        return await asyncio.to_thread(_set_markup)

db = Database()
