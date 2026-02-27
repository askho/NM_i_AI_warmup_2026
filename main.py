import websockets
import asyncio
 
from client import play
from utils import save_json
import json

async def main():
    raw_json = await play()
    state = json.loads(raw_json)
    save_json(state)


if __name__ == "__main__":
    asyncio.run(main())
    