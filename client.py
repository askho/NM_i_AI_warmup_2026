import asyncio
import websockets
import os


def get_URL() -> str:
    TOKEN = os.environ["AINM_TOKEN"]
    return  f"wss://game.ainm.no/ws?token={TOKEN}"

async def play():
    URL = get_URL

    async with websockets.connect(URL) as ws:
        while True:
            state = await ws.recv()
            return state
            # ... decide actions ...
            #await ws.send('{"actions": [...]}')
