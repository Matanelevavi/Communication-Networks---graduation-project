import requests
import logging
import re
import sys
from src.config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s -LOGIC- %(message)s',datefmt='%H:%M:%S', stream=sys.stdout)

class WeatherLogic:
    def __init__(self):
        #setup the API key
        self.api_key = API_KEY

    def is_english_only(self, text):
        #fails if it finds Hebrew letters. Allows English, numbers, and symbols.
        return not bool(re.search(r'[\u0590-\u05FF]', str(text)))

    #get the city coordinates and fetch the weather forecast for the next 24 hours
    def fetch_weather(self, city_name):
        if not self.is_english_only(city_name):
            return {"error": "Input Error: Please use English names only for the city."}
        try:
            #get coordinates via Geocoding API
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
            geo_res = requests.get(geo_url,timeout=HTTP_TIMEOUT).json()

            if "results" not in geo_res or not geo_res["results"]:
                return {"error": f"City Error: '{city_name}' was not found."}

            res = geo_res["results"][0]
            lat, lon = res["latitude"], res["longitude"]
            #get 24h weather data
            weather_url=(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                           f"&current_weather=true&hourly=temperature_2m,precipitation_probability&timezone=auto")
            data = requests.get(weather_url,timeout=HTTP_TIMEOUT).json()

            temps = data["hourly"]["temperature_2m"][:24]
            rain_probs =data["hourly"]["precipitation_probability"][:24]
            times = data["hourly"]["time"][:24]

            RAIN_THRESHOLD=10
            rain_alerts = []
            for i in range(len(rain_probs)):
                if rain_probs[i]>RAIN_THRESHOLD:
                    hour = times[i].split("T")[1]
                    rain_alerts.append(f"{hour} ({rain_probs[i]}%)")

            rain_summary = ", ".join(rain_alerts) if rain_alerts else "No rain expected"
            return {
                "min_temp": min(temps),
                "max_temp": max(temps),
                "current_temp": data["current_weather"]["temperature"],
                "rain_str": rain_summary,
                "city_full_name": res["name"],
                "lat": lat,
                "lon": lon,
                "error": None
            }
        except Exception as e:
            logging.error(f"Weather logic error: {e}")
            return {"error": "Connection Error: Failed to reach weather service."}

    #ask the Gemini for clothing advice based on the weather and family details
    def get_ai_recommendation(self,weather_data,profiles):
        if not weather_data or weather_data.get("error"):
            return weather_data.get("error","Unknown error")

        if not self.is_english_only(str(profiles)):
            return "Input Error: Family profiles must be in English for the AI to process"

        prompt = (f"Today in {weather_data['city_full_name']}: {weather_data['min_temp']}C to {weather_data['max_temp']}C. "
                  f"Rain: {weather_data['rain_str']} "
                  f"Family info: {profiles} "
                  f"Task: Write a short and friendly paragraph in English with clothing advice "
                  f"focus on the weather, no lists")
        if MOCK_LLM:
            return "Mock: It's a nice day! Wear light clothes\nNote: Insert an API KEY in config.py to get personalized AI recommendations!"

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=HTTP_TIMEOUT).json()

            if 'candidates' in res:
                return res['candidates'][0]['content']['parts'][0]['text']

            error_msg = res.get('error', {}).get('message', 'AI Service Error')
            return f"AI Error: {error_msg}"
        except Exception as e:
            logging.error(f"AI Connection error: {e}")
            return "Recommendation Error: Could not connect to AI advisor."

    #download the full weather data as a raw CSV file
    def download_weather_csv_report(self, city, lat, lon):
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&format=csv"
        try:
            logging.info(f"Downloading CSV weather report for {city}...")
            respo = requests.get(url,timeout=HTTP_TIMEOUT)

            if respo.status_code== 200:
                logging.info("CSV file downloaded successfully.")
                return respo.content
            else:
                logging.warning(f"Failed to download CSV. Status: {respo.status_code}")
                return None
        except Exception as e:
            logging.error(f"HTTP Download Error: {e}")
            return None