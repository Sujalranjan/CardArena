# CardArena System Overview

CardArena is a server-authoritative multiplayer online card-game platform designed for scalable room management, low-latency WebSocket communication, and pluggable card game implementations.

```
                          [ Client Browser ]
                     (React + Vite + TypeScript)
                                 │
                 REST (HTTP)     │     WebSockets (WS)
                 auth / rooms    │     realtime sync & actions
                                 ▼
                     ┌───────────────────────┐
                     │    FastAPI Backend    │
                     ├───────────────────────┤
                     │  WebSocket Manager    │
                     │  Room Service Layer   │
                     │  Auth & Token Guard   │
                     └──────────┬────────────┘
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│   PostgreSQL Database   │           │   Generic Game Engine   │
│  users, rooms, players  │           │   BaseGame, Deck, Card  │
└─────────────────────────┘           │   Registry, PlayerView  │
                                      └─────────────────────────┘
```

## Layers of Responsibility

1. **Frontend (React + Vite + Tailwind CSS)**:
   - Dumb presentation layer.
   - Collects user inputs (room creation, joining, toggling ready, starting match).
   - Renders server-confirmed state received over WebSocket/REST.
   - Performs no authoritative game validation.

2. **API & WebSocket Layer (FastAPI)**:
   - Validates message schemas using Pydantic.
   - Enforces bearer token JWT authorization on REST and WebSocket connections.
   - Guards host privileges (settings adjustments, starting game).
   - Converts network payloads into service calls.

3. **Room Service Layer**:
   - Manages room lifecycle: creation, joining, capacity checks, leaving, host transfers, ready toggling.
   - Synchronizes room membership changes across active connections via the `ConnectionManager`.

4. **Generic Game Engine**:
   - Isolated from HTTP/WebSocket/DB frameworks.
   - Encapsulates cryptographic card shuffling (`secrets` module), deck operations, player view filtering, and game event publishing.

5. **Persistence Layer**:
   - PostgreSQL backed by SQLAlchemy 2.0 async engine and declarative models (`users`, `rooms`, `room_players`).
