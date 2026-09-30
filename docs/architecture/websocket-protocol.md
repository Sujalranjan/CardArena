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
- `START_GAME`: Host launches the game session (validates minimum 2 players and player readiness). Only accepted while the room is `WAITING`; otherwise an `ERROR` is returned and any existing game session is left untouched.
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
- `GAME_STATE`: Player-specific game view (own hand only). Re-sent to every player on game actions, disconnects and reconnects. `players[].is_connected` is derived from live WebSocket connections; `players[].display_name` comes from the authoritative user record.
- `FAIRNESS_COMMITTED`: `{"fairness": <public record, server_seed null>, "sequence_number": n}`. Sent when a round's shuffle is committed, before any `GAME_STATE` containing that round's cards. See [provably-fair.md](provably-fair.md).
- `FAIRNESS_REVEALED`: `{"fairness": <public record with server_seed>, "sequence_number": n}`. Sent when a round ends (or at game over for any unrevealed round).
- `GAME_STATE.game_view.fairness`: list of public fairness records for the session (seeds only for revealed rounds); also delivered on reconnect.
- `ROOM_STATE` with `"event": "GAME_OVER"`: Sent after the final `GAME_STATE` when a game concludes. The room moves to `FINISHED` and the in-memory game session is removed; further game actions are rejected.
- `ERROR`: Emitted to offending socket when an action is rejected or unauthorized.
- `PONG`: Keep-alive response.

## 3. Game Session Lifetime

Active game sessions are held in backend process memory (`GameSessionManager`) and are **not persisted**. A backend restart loses all in-progress games; rooms that were `PLAYING` at that moment remain `PLAYING` in the database with no session behind them. Restart persistence is not implemented.
