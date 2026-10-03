"""Minimal stdlib RFC 6455 WebSocket server->client channel.

Implements ONLY what the dev-server events channel needs:

* server->client TEXT frames (JSON event payloads)
* client->-server control frames handled per the RFC (ping/pong/close);
  text frames from the client are READ AND IGNORED (v1 is server->client
  only; the socket is future-proofed for v2 bidirectional commands)

Deliberately dependency-free (conductor constraint: zero new runtime
deps). Not a general-purpose WebSocket implementation: single-user,
localhost, low traffic, we own both ends.

Handshake: HTTP/1.1 Upgrade on GET /api/events with Sec-WebSocket-Key;
the response Sec-WebSocket-Accept is base64(SHA1(key + GUID)) per
RFC 6455 §4.2.2.
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import struct
from typing import Any

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


def accept_key(sec_websocket_key: str) -> str:
    """Compute the Sec-WebSocket-Accept value for a handshake key."""
    digest = hashlib.sha1((sec_websocket_key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_text_frame(payload: str) -> bytes:
    """Encode one server->client TEXT frame (server frames are never
    masked; payload length uses the minimal length encoding)."""
    data = payload.encode("utf-8")
    n = len(data)
    if n < 126:
        header = struct.pack("!BB", 0x80 | OP_TEXT, n)
    elif n < 65536:
        header = struct.pack("!BBH", 0x80 | OP_TEXT, 126, n)
    else:
        header = struct.pack("!BBQ", 0x80 | OP_TEXT, 127, n)
    return header + data


def encode_close_frame(code: int = 1000) -> bytes:
    return struct.pack("!BBH", 0x80 | OP_CLOSE, 2, code)


def encode_pong_frame(payload: bytes) -> bytes:
    header = struct.pack("!BB", 0x80 | OP_PONG, len(payload))
    return header + payload


class WsEOF(Exception):
    """Peer closed the connection (or transport died)."""


def read_client_frame(rfile: Any) -> tuple[int, bytes]:
    """Read ONE client frame. Client->server frames MUST be masked (RFC
    §5.3); unmasked client frames are a protocol error -> WsEOF.

    Returns (opcode, unmasked payload). Handles only what the dev server
    needs: control frames + (ignored) text frames.
    """
    head = rfile.read(2)
    if len(head) < 2:
        raise WsEOF("eof")
    b1, b2 = head[0], head[1]
    opcode = b1 & 0x0F
    fin = bool(b1 & 0x80)
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if not masked:
        # RFC 6455 §5.1: client frames must be masked.
        raise WsEOF("unmasked client frame")
    if length == 126:
        ext = rfile.read(2)
        if len(ext) < 2:
            raise WsEOF("eof")
        length = struct.unpack("!H", ext)[0]
    elif length == 127:
        ext = rfile.read(8)
        if len(ext) < 8:
            raise WsEOF("eof")
        length = struct.unpack("!Q", ext)[0]
    if length > 1 << 20:  # 1 MiB guard for a channel that only pings
        raise WsEOF("oversized frame")
    mask = rfile.read(4)
    if len(mask) < 4:
        raise WsEOF("eof")
    payload = bytearray(rfile.read(length))
    if len(payload) < length:
        raise WsEOF("eof")
    for i in range(length):
        payload[i] ^= mask[i % 4]
    # Fragmentation (FIN=0 with continuation) is not expected from our own
    # client; treat as protocol simplicity: accept only FIN frames.
    if not fin and opcode in (OP_TEXT, OP_BINARY):
        raise WsEOF("fragmented client frame")
    return opcode, bytes(payload)


def event_json(event: Any) -> str:
    """Serialize a WorkspaceEvent-shaped object (has to_dict()) to a
    single text-frame payload."""
    return json.dumps(event.to_dict())
