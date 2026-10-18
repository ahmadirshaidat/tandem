import base64

from fastapi import FastAPI, WebSocket
from pycrdt import Doc, Text

app = FastAPI()
doc = Doc({"probe": Text()})
peers = set()


@app.websocket("/sync")
async def sync(ws: WebSocket):
    await ws.accept()
    peers.add(ws)
    await ws.send_json({"state": base64.b64encode(doc.get_update()).decode()})
    try:
        while True:
            m = await ws.receive_json()
            # Both spikes use the same synthetic authorization decision per frame.
            if m.get("role") != "editor":
                await ws.send_json({"denied": True, "id": m.get("id")})
                continue
            try:
                doc.apply_update(base64.b64decode(m["update"], validate=True))
            except Exception:
                await ws.send_json({"invalid": True, "id": m.get("id")})
                continue
            for peer in list(peers):
                await peer.send_json(
                    {
                        "state": base64.b64encode(doc.get_update()).decode(),
                        "id": m.get("id"),
                    }
                )
    finally:
        peers.discard(ws)
