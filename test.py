import requests



def fetch_traffic_free(origin: str, destination: str) -> str:
    # 1. Получаем координаты без ключей
    orig_coords = get_coords(origin)
    dest_coords = get_coords(destination)

    if not orig_coords or not dest_coords:
        return "Ошибка: не удалось найти координаты для адресов"

    # 2. Строим маршрут через бесплатный сервер OSRM
    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{orig_coords[0]},{orig_coords[1]};{dest_coords[0]},{dest_coords[1]}"
    params = {"overview": "false"}

    score = 1
    tendency = "не меняется"
    description = "Нет данных"

    try:
        response = requests.get(osrm_url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok":
                route = data["routes"][0]
                
                # OSRM отдает время движения в секундах
                duration_sec = route["duration"]
                distance_km = route["distance"] / 1000
                
                # Расчет средней скорости на маршруте
                avg_speed = (distance_km / (duration_sec / 3600)) if duration_sec > 0 else 60

                # Оцениваем загруженность по средней скорости в городе
                if avg_speed >= 45:
                    score = 1
                    description = "Дороги свободны"
                elif avg_speed >= 30:
                    score = 4
                    description = "Местами затруднения"
                elif avg_speed >= 15:
                    score = 7
                    description = "Серьёзные пробки"
                else:
                    score = 10
                    description = "Город стоит"

    except Exception as e:
        print(f"Ошибка запроса: {e}")

    return f'Оценка пробок по 10-бальной шкале {score}, загруженность дорог {tendency}, Оценка карт: {description}'

# Вызов функции без использования API ключа
print(fetch_traffic_free("ул. Тверская, 12, Москва, Россия", "Аэропорт Шереметьево, Терминал C, Москва")) 

