"""SQLAlchemy database models for Users, Rooms, and RoomPlayers."""
import enum
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class RoomStatus(str, enum.Enum):
    WAITING = "WAITING"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    avatar = Column(String(255), nullable=True, default="default")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    hosted_rooms = relationship("Room", back_populates="host_user", foreign_keys="Room.host_id")
    memberships = relationship("RoomPlayer", back_populates="user", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(8), unique=True, index=True, nullable=False)
    host_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    selected_game = Column(String(50), nullable=False, default="hearts")
    max_players = Column(Integer, nullable=False, default=4)
    status = Column(Enum(RoomStatus), nullable=False, default=RoomStatus.WAITING)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host_user = relationship("User", foreign_keys=[host_id], back_populates="hosted_rooms")
    players = relationship(
        "RoomPlayer",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="RoomPlayer.seat",
    )


class RoomPlayer(Base):
    __tablename__ = "room_players"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    room_id = Column(String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seat = Column(Integer, nullable=False)
    is_ready = Column(Boolean, default=False, nullable=False)
    is_connected = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    room = relationship("Room", back_populates="players")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_user"),
        UniqueConstraint("room_id", "seat", name="uq_room_seat"),
    )
