from pydantic import BaseModel, Field
import datetime
from typing import Optional

#pydantic_schemes
class ChatSendMessage(BaseModel):
    user_id:int
    message_text: str
    timestamp: datetime.datetime

class ChatMessageResponse(BaseModel):
    id: int
    user_id: int
    sender: str
    message_text: str
    timestamp: datetime.datetime

class GeminiEveningResponse(BaseModel):
    to_do: str = Field(description = 'Совет - чем пользователю лучше заняться сегодня вечером с учётом его усталости и предпочтений')
    rec_time: str = Field(description = 'Рекомендуемое время в которое пользователю лучше лечь спать с учётом усталости')
    eat_advice: str = Field(description = 'Креативная идея ужина и общий совет по еде сегодня с учётом распиания')
    tommorow_advice: str = Field(description = 'Совет по распределению распиания на следующий день')

class GeminiEvents(BaseModel):
    event_time: datetime.time
    event_title: str
    location: Optional[str] = None
    description: Optional[str] = None

class ScheduleResponse(BaseModel):
    id: int
    user_id: int
    event_date: datetime.date
    event_time: datetime.time
    event_title: str
    location: Optional[str] = None
    description: Optional[str] = None
    ai_advice: Optional[str] = None

class Schedule_short_respose(BaseModel):
    id: int
    user_id:int
    event_title: str
    event_time: datetime.time

class Schedule_advice(BaseModel):
    advice: str

class Schedule_new(BaseModel):
    user_id: int
    event_date: datetime.date
    event_time: datetime.time
    event_title: str
    location: Optional[str] = None
    description: Optional[str] = None

class RegRequest(BaseModel):
    username: str
    password: str
    country: str
    city: str

class AuthRequest(BaseModel):
    username: str
    password: str

class GeminiMorningResponse(BaseModel):
    greeting: str = Field(description="Доброе утреннее приветствие по имени и краткий разбор дня на 2-3 предложения.")
    action_advice: str = Field(description="Конкретный совет на утро на основе погоды, пробок и планов пользователя.")
    chosen_song_title: str = Field(description="Название выбранной песни. Если песня была жестко задана пользователем, верни её название без изменений.")

class AlarmCreateSchema(BaseModel):
    user_id: int
    alarm_time: datetime.datetime  
    description: str
    music_style: str = "AI"    

class AlarmsResponseSchema(BaseModel):
    id: int
    user_id: int
    alarm_time: datetime.datetime
    description: str
    weather: Optional[str] = None
    traffic: Optional[str] = None
    ai_advice: Optional[str] = None
    audio_url: Optional[str] = None

class Alarm_short_response(BaseModel):
    id: int
    user_id: int
    alarm_time: datetime.datetime
    description: str