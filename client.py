import asyncio
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

def get_URL() -> str:
    # Fetches URL from env
    return os.environ["AINM_URL"]


async def play():
    WS_URL  = get_URL()

    async with websockets.connect(WS_URL) as ws:
        while True:
            state = await ws.recv()
            return state
            # ... decide actions ...
            #await ws.send('{"actions": [...]}')
#          asyncio.run(play())
#       Respond within 2 seconds per round