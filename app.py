# streamlit_app.py

import streamlit as st
import asyncio
import os
import struct
import uuid
from functools import partial
import websockets
import threading

# UUID from environment or default
UUID = os.getenv("UUID", "d342d11e-d424-4583-b36e-524ab1f0afa4").replace('-', '')
PORT = int(os.getenv("PORT", "443"))

def log(*args):
    print("LOG:", *args)

def err(*args):
    print("ERR:", *args)

async def handle_connection(websocket, path):
    log("New connection")
    try:
        # Read initial handshake message
        msg = await websocket.recv()
        if not isinstance(msg, bytes):
            err("Invalid data received")
            return

        msg = bytearray(msg)
        VERSION = msg[0]
        id_bytes = msg[1:17]

        # Validate UUID
        expected_id = bytearray.fromhex(UUID)
        if id_bytes != expected_id:
            err("UUID mismatch")
            return

        i = 17
        len_ = msg[i]
        i += 1 + len_
        
        port = int.from_bytes(msg[i:i+2], 'big')
        i += 2
        
        ATYP = msg[i]
        i += 1

        host = None
        if ATYP == 0x01:  # IPv4
            ip = msg[i:i+4]
            host = ".".join(str(b) for b in ip)
            i += 4
        elif ATYP == 0x02:  # Domain name
            domain_len = msg[i]
            host = msg[i+1:i+1+domain_len].decode('utf-8')
            i += 1 + domain_len
        elif ATYP == 0x03:  # IPv6
            err("IPv6 unsupported")
            return
        else:
            err("Unknown address type:", ATYP)
            return

        log(f"Connecting to {host}:{port}")

        # Acknowledge handshake
        await websocket.send(bytes([VERSION, 0]))

        # Connect to remote TCP server
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=10)
        
        # Forward remaining data from client
        writer.write(msg[i:])
        await writer.drain()

        async def ws_to_tcp():
            try:
                async for data in websocket:
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception as e:
                err("WS->TCP Error:", e)
            finally:
                writer.close()
                await writer.wait_closed()

        async def tcp_to_ws():
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    await websocket.send(data)
            except Exception as e:
                err("TCP->WS Error:", e)
            finally:
                await websocket.close()

        await asyncio.gather(ws_to_tcp(), tcp_to_ws())

    except Exception as e:
        err("Connection error:", e)

async def start_websocket_server():
    async with websockets.serve(
        handle_connection,
        "0.0.0.0",
        PORT,
        ping_interval=None,
        ping_timeout=None
    ):
        log(f"WebSocket server started on port {PORT}")
        await asyncio.Future()  # Run forever

def run_asyncio_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_websocket_server())

# Start WebSocket server in a background thread
threading.Thread(target=run_asyncio_loop, daemon=True).start()

# Streamlit UI
st.title("WebSocket Proxy Dashboard")
st.markdown(f"WebSocket server running on port `{PORT}`")

if st.checkbox("Show UUID"):
    st.code(UUID)
