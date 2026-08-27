#imports

import datetime
import os
from sqlalchemy import ForeignKey, String, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.future import select

#base steps/definition dialog rules

DATABASE_URL = "sqlite+aiosqlite:///./ylmj_base.db"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

#base class

class Base(DeclarativeBase, AsyncAttrs):
    pass

#data tables

class Countrycodes(Base):
    __tablename__ = "Countrycodes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    countryname: Mapped[str] = mapped_column(String(255))
    countrycode: Mapped[str] = mapped_column(String(64))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    login_count: Mapped[int] = mapped_column(default=0)
    latitude: Mapped[int] = mapped_column()
    longitude: Mapped[int] = mapped_column()
    history: Mapped[list["MorningHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    preferences: Mapped["UserPreferences"] = relationship( back_populates="user", cascade="all, delete-orphan")
    alarms: Mapped[list["Alarm"]] = relationship("Alarm", back_populates="user", cascade="all, delete-orphan")
    schedule: Mapped[list["Schedule"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chat: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    country: Mapped[str] =  mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)

class UserPreferences(Base):
    __tablename__ = 'UserPreferences'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_description: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="preferences")


class TrackData(Base):
    __tablename__ = 'TrackData'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    track: Mapped[str]  = mapped_column(String(255))
    play_url: Mapped[str] = mapped_column(String(255))


class MorningHistory(Base):
    __tablename__  = 'MorningHistory'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    morning_track: Mapped[str] = mapped_column(String(255))
    user: Mapped["User"] = relationship(back_populates="history")

class Schedule(Base):
    __tablename__ = 'Schedule'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)     
    event_time: Mapped[str] = mapped_column(String(10), nullable=False)              
    event_title: Mapped[str] = mapped_column(String(100), nullable=False)            
    location: Mapped[str] = mapped_column(String(150), nullable=True)                
    description: Mapped[str] = mapped_column(Text, nullable=True)                     
    ai_advice: Mapped[str] = mapped_column(Text, nullable=True)                       
    user: Mapped["User"] = relationship("User", back_populates="schedule")

class Chat(Base):
    __tablename__ = 'Chat'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    sender: Mapped[str] = mapped_column(String(10), nullable=False)                  
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    user: Mapped["User"] = relationship("User", back_populates="chat")

class Alarm(Base):
    __tablename__ = "alarms"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    alarm_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)  
    description: Mapped[str] = mapped_column(String(255), nullable=True)             
    music_style: Mapped[str] = mapped_column(String(100), default="AI")              
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)
    weather_info: Mapped[str] = mapped_column(String(255), nullable=True)            
    traffic_info: Mapped[str] = mapped_column(String(255), nullable=True)            
    ai_advice: Mapped[str] = mapped_column(Text, nullable=True)                       
    audio_url: Mapped[str] = mapped_column(Text, nullable=True)                     
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship("User", back_populates="alarms")

#control function

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await load_songs_to_database()
    await load_country_list()

async def load_country_list():
    path = "static\countrycodes.txt"
    async with async_session() as session:
        result = await session.execute(select(Countrycodes))
        if result.scalars().first() is not None:
            print("-- Base: No need to load countries")
            return

        print(f"-- Base: Loading countries data. Path: {path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    parts = line.split(",")
                    countryname = parts[0]
                    countrycode = parts[1]
                    data = Countrycodes(
                        countryname = countryname,
                        countrycode = countrycode)
                    session.add(data)
                except Exception as e:
                    print(f"-! Base: country parsing error: line:'{line}' error: {e}")

        await session.commit()
        print("-- Base: Countries loading complete!")


async def load_songs_to_database():
    file_path = "static\avaible_songs.txt"
    async with async_session() as session:
        result = await session.execute(select(TrackData))
        if result.scalars().first() is not None:
            print("-- Base: No need to load songs")
            return

        print(f"-- Base: Loading track data.Path: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    parts = line.split(";")
                    id = int(parts[0])
                    track = parts[1]
                    play_url = parts[2]
                    track = TrackData(id=id, track=track, play_url=play_url)
                    session.add(track)
                except Exception as e:
                    print(f"-! Base: tracks parsing error: line:'{line}' error: {e}")
                    
        await session.commit()
        print("-- Base: Track loading complete!")

