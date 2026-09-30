# WebSocket Message Protocol

CardArena coordinates all realtime room and match transitions through a typed WebSocket contract (`WSClientMessage` and `WSServerMessage`).

Endpoint: `/ws/rooms/{room_id}?token={jwt_token}`

## 1. Client -> Server Messages

All client messages adhere to:
```json
{
  "type": "<ACTION_NAME>",
  "payload": {}
}
```

### Supported Actions (Phase 1)
- `GET_ROOM_STATE`: Requests immediate authoritative snapshot of room metadata and players.
- `READY`: Player marks themselves ready.
- `NOT_READY`: Player marks themselves not ready.
- `START_GAME`: Host launches the game session (validates minimum 2 players and player readiness).
- `UPDATE_SETTINGS`: Host updates selected game mode or capacity.
- `PING`: Keep-alive ping from client.

---

## 2. Server -> Client Broadcasts

All server responses adhere to:
```json
{
  "type": "<EVENT_NAME>",
  "payload": {}
}
```

### Supported Events
- `ROOM_STATE`: Full room snapshot containing player seats, readiness, connection status, and host ID.
- `PLAYER_JOINED`: Emitted when a new peer enters the room.
- `PLAYER_LEFT`: Emitted when a peer leaves.
- `PLAYER_DISCONNECTED`: Emitted when a peer temporarily loses connection.
- `PLAYER_RECONNECTED`: Emitted when a peer reconnects.
- `GAME_STARTED`: Broadcasted when host launches the game session.
- `ERROR`: Emitted to offending socket when an action is rejected or unauthorized.
- `PONG`: Keep-alive response.
