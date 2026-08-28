#Imports
import os
import datetime
import requests
import bcrypt
from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
import uvicorn
from pydantic import BaseModel, Field
from sqlalchemy.future import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from google.genai import types
from database import (init_db, 
	async_session, 
	Alarm, 
	User,
	Chat,
	Schedule,
	MorningHistory,
	TrackData,
	UserPreferences,
    Countrycodes)
from static.static import return_codes, return_w_codes
import xmltodict

#get secrets
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

#Pydantic schemes
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

class AlarmFullResponseSchema(BaseModel):
    alarm_id: int
    user_id: int
    alarm_time: datetime.datetime
    description: str
    weather: str
    traffic: str
    ai_advice: str
    audio_url: str

#function block/api requests
def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')  

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )

async def get_cordinates(city:str, country:str, api_key = WEATHER_API_KEY):
    url = "http://api.openweathermap.org/geo/1.0/direct"

    async with async_session() as session:
        query = select(Countrycodes.countrycode).where(Countrycodes.countryname == country)
        result = await session.execute(query)
        code = result.scalars().all()
        сountrycode = code[0]

    params = {
        "q": f"{city},{сountrycode}",
        "limit": 1,
        "appid":api_key,
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data:
            lat = data[0]["lat"]
            lon = data[0]["lon"]
            return lat, lon
        else:
            return None, "-! Server error: city not found"
    else:
        return None,  f"-! Server error: response error, status: {response.status_code}"

def get_weather_description(code: int) -> str:
    wmo_codes = return_w_codes()
    return wmo_codes.get(code, "❓ Неизвестные погодные условия")

def get_region_code(city:str) -> int:
    codes = return_codes()
    return codes.get(city,0000)

async def fetch_weather(lat: int, long: int) -> str:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": long,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "wind_speed_unit": "ms",
        "timezone": "auto"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        current = data["current"]
        result = f'Температура: {current['temperature_2m']}°C (ощущается как {current['apparent_temperature']}°C), Влажность: {current['relative_humidity_2m']}%, Скорость ветра: {current['wind_speed_10m']} м/с, погода: {get_weather_description(current['weather_code'])} '
        return result
    else:
        print(f"-! Server error: response error: {response.status_code}")
        return (f'Данные о погоде временно не доступны') 

async def fetch_traffic(region: int) -> dict:
    url = f'https://export.yandex.ru/bar/reginfo.xml?region={region}'

    score = 0
    tendency = 0
    description = 'Нет данных'

    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = xmltodict.parse(response.text) or {}
        
        
        info = data.get('info') or {}
        traffic = info.get('traffic') or {}
        traffic_info = traffic.get('region') or {}

        if traffic_info:
            score = int(traffic_info.get('level', 0) or 0)
            tendency = int(traffic_info.get('tend', 0) or 0)
            hints = traffic_info.get('hint', [])
            
            if isinstance(hints, list):
                for h in hints:
                    if isinstance(h, dict) and h.get('@lang') == 'ru':
                        description = h.get('#text', 'Нет данных')
                        break
            elif isinstance(hints, dict):
                description = hints.get('#text', 'Нет данных')
    else:
        return (f'Данные о трафике временно недоступны')

    if tendency == -1:
        tendency = 'падает'
    if tendency == 1:
        tendency = 'растёт'
    else:
        tendency = 'не меняется'

    return f'Оценка пробок по 10ти бальной шкале {score}, загруженность дорог {tendency}, Оценка карт: {description}'

async def check_and_prepare_alarms():
    now = datetime.datetime.now(datetime.timezone.utc)
    ten_minutes_later = now + datetime.timedelta(minutes=10)
    async with async_session() as session:
        query = select(Alarm).where(
            Alarm.alarm_time >= now,
            Alarm.alarm_time <= ten_minutes_later,
            Alarm.is_ready == False
        )
        result = await session.execute(query)
        alarms_to_process = result.scalars().all()
        
        if not alarms_to_process:
            return

        songs_query = select(TrackData.track)
        songs_result = await session.execute(songs_query)
        available_songs = songs_result.scalars().all()
        songs_list_str = ", ".join([f"'{t}'" for t in available_songs])

        for alarm in alarms_to_process:
            try:
                user_result = await session.execute(select(User).where(User.id == alarm.user_id))
                user = user_result.scalar_one_or_none()
                user_name = user.username if user else "Друг"
                
                user_preferences = await session.execute(select(UserPreferences.user_description).where(UserPreferences.user_id == alarm.user_id))
                user_preferences = user_preferences.scalar_one_or_none()
                if user_preferences is None:
                	user_preferences = "обычный житель 2000 тысячелетия"

                history = await session.execute(select(MorningHistory.morning_track).where(MorningHistory.user_id == alarm.user_id).order_by(MorningHistory.id.desc()).limit(15))
                history = history.scalars().all()

                l_query = select(User.latitude).where(User.id == alarm.user_id)
                l_result = await session.execute(l_query)
                lat = l_result.scalars().all()

                lo_query = select(User.longitude).where(User.id == alarm.user_id)
                lo_result = await session.execute(lo_query)
                longi = lo_result.scalars().all()

                c_query = select(User.country).where(User.id == alarm.user_id)
                c_result = await session.execute(c_query)
                country = c_result.scalars().all()

                ci_query = select(User.city).where(User.id == alarm.user_id)
                ci_result = await session.execute(ci_query)
                city = ci_result.scalars().all()

                weather = await fetch_weather(lat, longi)

                if country[0] == "Russian Federation":
                    traffic = await fetch_traffic(get_region_code(city[0]))
                else:
                    traffic = "Информация о трафике недоступна за пределами РФ"
                
                final_audio_url = None
                chosen_title = alarm.music_style
                
                if alarm.music_style == "AI":
                    
                    music_instruction = (
                        f"Пользователь доверил тебе выбор музыки. Выбери ОДИН трек из предложенного списка, "
                        f"который лучше всего подходит под настроение этого утра: [{songs_list_str}]."
                    )
                else:
                    
                    music_instruction = (
                        f"Пользователь сам выбрал трек: '{alarm.music_style}'. "
                        f"Ты ОБЯЗАН вернуть это же название в поле `chosen_song_title`."
                    )

                
                context_prompt = (
                    f"Ты — умный ИИ-секретарь. Составь утреннюю сводку для пользователя.\n"
                    f"Имя: {user_name}.\n"
                    f'Информация о пользователе:{user_preferences}\n'
                    f"Планы на утро: '{alarm.description}'.\n"
                    f"Погода на улице: {weather}.\n"
                    f"Ситуация с пробками: {traffic}.\n"
                    f'Треки которые пользователь уже слышал (не повторяй их):{history}'
                    f"{music_instruction}"
                )
                
                
                response = client.models.generate_content(
                    model='gemini-3.1-flash-lite',
                    contents=context_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiMorningResponse,
                        temperature=0.7
                    ),
                )
                
                ai_data = GeminiMorningResponse.model_validate_json(response.text)
                
                track_title_to_find = ai_data.chosen_song_title.strip() if alarm.music_style == "AI" else alarm.music_style
                
                track_query = select(TrackData).where(TrackData.track == track_title_to_find)
                track_result = await session.execute(track_query)
                track = track_result.scalar_one_or_none()
                
                if track:
                    final_audio_url = track.play_url
                else:
                    print(f"-! Server error: track '{track_title_to_find}' not found.")
                    final_audio_url = "https://huggingface.co/datasets/YLMJprojectadminister/YLMJ_libroary/resolve/main/audio/Believer — Imagine Dragons.mp3"

                alarm.weather_info = weather
                alarm.traffic_info = traffic
                alarm.ai_advice = f"{ai_data.greeting}{ai_data.action_advice}"
                alarm.audio_url = final_audio_url
                alarm.is_ready = True  

                await session.commit()
                print(f"-- Server info: alarm with id {alarm.id} get ready now!")
                
            except Exception as e:
                print(f"-! Server error: alarm wih id {alarm.id} has an error: {e}")

async def save_user_description(user_id: int, user_description: str):
    async with async_session() as session:
        query = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await session.execute(query)
        prefs = result.scalar_one_or_none()
        
        if prefs:
            prefs.user_description = user_description
            current_prefs = prefs
        else: 
            new_prefs = UserPreferences(user_id=user_id, user_description=user_description)
            session.add(new_prefs)
            current_prefs = new_prefs
            
        await session.commit()          
        await session.refresh(current_prefs)  
        return current_prefs

#lifespan settings
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = AsyncIOScheduler(timezone='UTC')
    scheduler.add_job(check_and_prepare_alarms, 'interval', minutes=1)
    scheduler.start()
    yield
    scheduler.shutdown()

#app definition/api settings
app = FastAPI(title="YLMJ", lifespan=lifespan)
client = genai.Client(api_key=GEMINI_API_KEY)

#api endpoints
@app.get('/api/heathcheck')
async def healthcheck():
    return{'status':'-- Server status: live'}

@app.post("/api/preferences")
async def update_preferences(user_description: str, user_id: int): 
    if not user_description.strip():
        raise HTTPException(status_code=400, detail="-! Server error: write at least")
    await save_user_description(user_id=user_id, user_description=user_description)
    return {"status": "-- Server status: success", "message": "Preferences up to date sucsessfully"}

@app.post("/api/alarms/create", status_code=201)
async def create_alarm(data: AlarmCreateSchema):

    async with async_session() as session:
        new_alarm = Alarm(
            user_id=data.user_id,
            alarm_time=data.alarm_time,
            description=data.description,
            music_style=data.music_style,
            is_ready=False  
        )
        session.add(new_alarm)
        await session.commit()
        return {"status": "-- Server status: created sucsessfully", "alarm_id": new_alarm.id}

@app.post("/api/auth/login")
async def login(data: AuthRequest):
    if not data.username.strip() or not data.password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="-! Server error: You have not filled in all the fields."
        )
    safe_pass = data.password[:70]
    async with async_session() as session:
        query = select(User).where(User.username == data.username)
        user = await session.scalar(query)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="-! Server error: An account with this name not already created.")
        if not verify_password(safe_pass, user.password_hash):  
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="-! Server error: invalid password"
                ) 
        return {
            "status": "-- Server status: success",
            "user_id": user.id,
            "username": user.username,
            "latitude": user.latitude,
            "longitude": user.longitude,
            "city": user.city,
            "country": user.country     
        }
        
@app.post("/api/auth/register")
async def register(data: RegRequest):
    if not data.username.strip() or not data.password.strip() or not data.country.strip() or not data.city.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="-! Server error: You have not filled in all the fields."
        )
    safe_pass = data.password[:70]
    async with async_session() as session:
        query = select(User).where(User.username == data.username)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        if user is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="-! Server error: An account with this name has already been created."
            )
        else:
            latitude, longitude = await get_cordinates(data.city, data.country)
            user = User(
                username=data.username,
                password_hash=get_password_hash(safe_pass),  
                login_count=1,
                latitude = latitude,
                longitude = longitude,
                city = data.city,
                country = data.country            
            )
            session.add(user)
        await session.commit()
        await session.refresh(user)
        return {
            "status": "-- Server status: success",
            "user_id": user.id,
            "username": user.username,
            "latitude": user.latitude,
            "longitude": user.longitude,
            "city": user.city,
            "country": user.country     
        }

@app.get('/api/alarms/get', response_model=AlarmFullResponseSchema)
async def get_alarm(id:int):
    async with async_session() as session:
        query = select(Alarm).where(Alarm.id == id)
        info = await session.scalar(query)
        if info is not None:
            response = AlarmFullResponseSchema(
                alarm_id = info.id,
                user_id = info.user_id,
                alarm_time = info.alarm_time,
                description = info.description,
                weather = info.weather_info,
                traffic = info.traffic_info,
                ai_advice = info.ai_advice,
                audio_url = info.audio_url
                )
            return response
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"-! Server error: Alarm with id {id} not found"
            )

#initializing app
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
