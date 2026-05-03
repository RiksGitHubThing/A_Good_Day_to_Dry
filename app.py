from pandas.core.arrays.timedeltas import truediv_object_array
import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("WEATHER_API_KEY")
try:
    if "WEATHER_API_KEY" in st.secrets:
        API_KEY = st.secrets["WEATHER_API_KEY"]
except Exception:
    pass

if not API_KEY:
    st.error("There's something wrong in my API Key")
    st.stop()

now = None
here = None

st.set_page_config(page_title="A Good Day to Dry", page_icon="☂️", layout="wide")
st.title("☂️ A Good Day to Dry")
st.write("Welcome to A Good Day to Dry, a weather app that tells you if it's a good day to dry your clothes.")

#--------FUNCTIONS--------
def get_weather(city_name):
    url = f"http://api.weatherapi.com/v1/forecast.json?key={API_KEY}&q={city_name}&days=2&aqi=no&alerts=no"    
    response = requests.get(url)

    if response.status_code == 200:
        set_now (response)
        return response.json()
    else:
        return None

def set_now(response_json_data):
    """
    Sets the global 'now' variable to the local time (as a datetime object)
    from the response JSON data, under response_json_data['location']['localtime'].
    """
    global now
    try:
        # response_json_data can be a requests.Response, check and extract JSON if needed
        if hasattr(response_json_data, 'json'):
            data = response_json_data.json()
        else:
            data = response_json_data
        localtime_str = data['location']['localtime']  # e.g., "2024-05-13 18:30"
        now = datetime.strptime(localtime_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        now = None
        st.error(f"Failed to set 'now' from localtime: {e}")

def set_here(response_json_data):
    """
    Sets the global here variable from the returned location data (rather than using the input
    which might be a post code instead).
    """
    global here
    try:
        # response_json_data can be a requests.Response, check and extract JSON if needed
        if hasattr(response_json_data, 'json'):
            data = response_json_data.json()
        else:
            data = response_json_data
        here = data['location']['name']
    except Exception as e:
        here = None
        st.error(f"Failed to set 'here' from returned data")

def move_forecast_to_dataframe(payload) -> pd.DataFrame:
    rows = []
    for day in payload["forecast"]["forecastday"]:
        rows.extend(day["hour"])
    #unpack condition object
    df = pd.DataFrame(rows)
    df["condition_text"] = df["condition"].apply(lambda c: c["text"])
    df["time"] = pd.to_datetime(df["time"])
    #st.write (df)
    results = df.apply(lambda row: get_dry_score(row["is_day"], row["temp_c"], row["wind_mph"], row["humidity"], row["precip_mm"], row["dewpoint_c"]), axis=1)
    df["Drying_Score"] = results.apply(lambda x: x[0])
    df["Score_Reason"] = results.apply(lambda x: x[1])
    df["Dealbreaker"] = results.apply(lambda x: x[2])
    df = df.sort_values("time")
    if now is None:
        set_now(payload)
    df_24 = df[df["time"] >= now].head(24)
    return df_24
    
def is_there_weather(condition_code):
    if condition_code not in (1000, 1003, 1006, 1009):
        return True
    else:
        return False

def get_dry_score(is_day, temp, wind, humidity, rain, dew_point):
    t_points = 0
    w_points = 0
    h_points = 0
    score = 0
    dealbreaker = None
    if not is_day:
        dealbreaker = "it's night time"
    if rain > 0:
        dealbreaker = "it's raining"
    if (temp - dew_point < 2):
        dealbreaker = "there's a high risk of dew. Maybe Frost too"
    if temp < 2:
        dealbreaker = "its' freezing"
    if not dealbreaker:
        t_points = temp * 1.0
        # upto 25 pts for winds up to 20mph, then negative pts over 30mph
        effective_wind = min(wind, 20)
        w_points = effective_wind * 1.25
        if wind > 30:
            w_points -= (wind - 30) * 2.5
        # 45pts for zero humidity, no points for 100%
        h_points = (100 - humidity) * 0.45

        score = t_points + w_points + h_points
    #return max 100 pts
    return round(max(0, min(100, score))), {"temp": t_points, "wind":w_points, "humidity":h_points}, dealbreaker

def get_next_good_drying_time(forecast_data):
    formatted_next = ""
    next_good_drying_time = forecast_data.loc[forecast_data["Drying_Score"] >= 30].sort_values("time")
    if next_good_drying_time.empty:
        return None
    else:
        next_time = next_good_drying_time.iloc[0]["time"]
        formatted_next_time = next_time.strftime("%H:%M") if next_time else "Unknown"
        formatted_next_date = next_time.strftime("%A, %B %d %Y") if next_time else "Unknown"
        formatted_next = (f"The next good time to dry is {formatted_next_time} on {formatted_next_date}")
    return formatted_next if formatted_next else None

def how_long_until_it_rains(forecast_data):
    next_rain_time = forecast_data.loc[forecast_data["precip_mm"] > 0].sort_values("time")
    if next_rain_time.empty:
        return 0
    else:
        next_rain = next_rain_time.iloc[0]["time"]
        dt_rain = (next_rain - now).total_seconds()
        return max(0, round(dt_rain/3600, 2))


def estimate_drying_time(dewpoint, temp, humidity, wind_mph, fabric = "M"):
    #arbitrary 90 mins for 25degC day, 30% humidity, 15mph wind
    total_mins = 90
    #check the dewpoint...
    if temp - dewpoint < 2:
         return 16.0
    #if it's cold...
    if temp < 2:
        return 16.0

    if temp < 25:
        total_mins += (25-temp) * 10

    #if it's humid...
    if humidity > 30:
        if humidity > 70:
            total_mins += (humidity - 30) * 8 
        else:
            total_mins += (humidity - 30) * 3

    #what if there's no wind?
    if wind_mph < 15:
        total_mins += (15 - wind_mph) * 8
    
    total_mins *= (0.8 if fabric == "L" else 1.6 if fabric == "H" else 1.0)
    # return number of drying hours, or 'all day'
    return min(16.0, round(total_mins / 60, 1))

def hours_until_sunset(time_now, time_sunset):
    dt = (time_sunset - time_now).total_seconds()
    return max(0, dt/3600)

def interpret_scores(element_scores):
    score = {
        "🌡️ It's really cold": element_scores['temp']/30,
        "💨 There isn't enough breeze":element_scores['wind']/25,
        "💧 The humidity is high": element_scores['humidity'] / 45
    }
    return min(score, key=score.get)
    

#=========UI Stuff =========
# st.write(move_forecast_to_dataframe(get_forecast_data("Walsall")))
MIN_GOOD_DRYING_SCORE = 50

city = st.text_input("Where are your wet pants?")

if st.button("Check the Skies"):
    data_error=False
    sun_has_set=False
    data = get_weather(city)

    if data:
        set_now(data)
        


        forecast_data = move_forecast_to_dataframe(data)
        

        #Extract data from the API response
        temp = data['current']['temp_c']
        humidity = data['current']['humidity']
        wind = data['current']['wind_mph']
        condition = data['current']['condition']['text']
        weather = is_there_weather(data['current']['condition']['code'])
        icon = data['current']['condition']['icon']
        is_day = data['current']['is_day']
        raining = data['current']['precip_mm']
        dewpoint = data['current']['dewpoint_c']        
        sunset = data['forecast']['forecastday'][0]['astro']['sunset']
        weather_now = data['current']['condition']['text']
        
        set_here(data)
        formatted_here = here.capitalize()
        formatted_now = now.strftime("%H:%M") if now else "Unknown"
        formatted_date = now.strftime("%A, %B %d %Y") if now else "Unknown"
   
        st.header(f"The current time in {formatted_here} is {formatted_now} on {formatted_date}. ")
        st.header(f"The forecast for the next hour is {weather_now}")


        remaining_day = hours_until_sunset(now, datetime.combine(now.date(), datetime.strptime(sunset, "%I:%M %p").time()))
        current_drying_score, element_scores, dealbreaker = get_dry_score(is_day, temp, wind, humidity, raining, dewpoint)
        hours_until_rain = how_long_until_it_rains(forecast_data)


        card1, card2, card3 = st.columns(3)
        with card1:
            with st.container(border=True):
                st.metric("🌡️ Temperature", f"{temp}°C")
        with card2:
            with st.container(border=True):
                st.metric("💧 Humidity", f"{humidity}%")
        with card3:
            with st.container(border=True):
                st.metric("💨 Wind Speed", f"{wind} mph")


        if dealbreaker:        
            with st.container(border=True):
                st.error(f"🚫 You can't dry now because {dealbreaker}")
        else:
            with st.container(border=True):
                st.metric("**Current Drying Score**: ", current_drying_score)
                if current_drying_score < MIN_GOOD_DRYING_SCORE:
                    st.warning(f"{interpret_scores(element_scores)}")
        if current_drying_score <= MIN_GOOD_DRYING_SCORE:
            with st.container(border=True):
                    st.info(f"⏳{get_next_good_drying_time(forecast_data)}")

        st.divider()

        if current_drying_score > MIN_GOOD_DRYING_SCORE:
            with st.container(border=True):
                st.metric ("Approximate hours of daylight left", f"{round(remaining_day, 2)} hours")
            dry_light, dry_med, dry_heavy = st.columns(3)
            est_L = estimate_drying_time(dewpoint, temp, humidity, wind, "L")
            est_M = estimate_drying_time(dewpoint, temp, humidity, wind, "M")
            est_H = estimate_drying_time(dewpoint, temp, humidity, wind, "H")
            with dry_light:
                with st.container(border=True):
                    st.metric ("Light Fabrics will dry in", f"{est_L} hours")
                    if est_L > remaining_day:
                        st.error("🚨 Not enough hours in a day!")
                    elif est_L < hours_until_rain:
                        st.error("🌧️ It's expected to rain before then")
                    elif est_L > remaining_day * 0.8:
                        st.warning("⚠️ Almost the whole day!")
                    else:
                        st.success("☀️ These should be dry in no time")
            with dry_med:
                with st.container(border=True):
                    st.metric ("Medium Fabrics will dry in", f"{est_M} hours")
                    if est_M > remaining_day:
                        st.error("🚨 Not enough hours in a day!")
                    elif est_M < hours_until_rain:
                        st.error("🌧️ It's expected to rain before then")
                    elif est_M > remaining_day * 0.8:
                        st.warning("⚠️ Almost the whole day!")
                    else:
                        st.success("☀️ These should be dry in no time")
            with dry_heavy:
                with st.container(border=True):
                    st.metric ("Heavy Fabrics will dry in", f"{est_H} hours")
                    if est_H > remaining_day:
                        st.error("🚨 Not enough hours in a day!")
                    elif est_H < hours_until_rain:
                        st.error("🌧️ It's expected to rain before then")
                    elif est_H > remaining_day * 0.8:
                        st.warning("⚠️ Almost the whole day!")
                    else:
                        st.success("☀️ These should be dry in no time")
            if (est_L >= 10 or est_M >= 10 or est_H >= 10):
                st.warning("Remember: Clothes drying for more than 10 hours will smell like a damp basement...")
    # Check if the estimated drying finish times are after sunset and show a warning if so
    try:
        warnings = []
            # sunset is expected in string format "HH:MM" or datetime
        if isinstance(sunset, str):
            # Combine date from 'now' and time from 'sunset'
            sunset_time = datetime.strptime(sunset, "%H:%M").time()
            sunset_dt = now.replace(hour=sunset_time.hour, minute=sunset_time.minute, second=0, microsecond=0)
        else:
            sunset_dt = sunset
            # Compute finish times as datetimes
            finish_L = now + pd.to_timedelta(est_L, unit="h")
            finish_M = now + pd.to_timedelta(est_M, unit="h")
            finish_H = now + pd.to_timedelta(est_H, unit="h")

            after_sunset = None
            if finish_L > sunset_dt:
                after_sunset = "Light"
            elif finish_M > sunset_dt:
                after_sunset = "Medium"
            elif finish_H > sunset_dt:
                after_sunset = "Heavy"
       

            if after_sunset:
                st.warning(f"Warning: {after_sunset} and thicker fabrics will not be dry before sunset!")
    except Exception as e:
        pass
    
    else:
        st.error("Are you sure that's a place?")
        st.stop()

    st.header(f"Forecast for the next 24 hours")
    if data_error == False:
        left_graph, mid_graph, right_graph = st.columns(3)
        with left_graph:
            with st.container(border=True):
                st.subheader("Temperature in °C")
                temp_fig = px.line(
                    forecast_data,
                    x = "time",
                    y = ["temp_c","dewpoint_c"],
                    title = None
                )
                temp_fig.update_yaxes(range=[-10, 40], title = "°C")
                temp_fig.update_xaxes(title="time")
                temp_fig.update_layout(
                    hovermode="x unified",
                    legend_title_text=None,
                    legend=dict(
                        x=0.01, xanchor="left",
                        y=0.99, yanchor="top",
                        borderwidth=0,
                    ),
                    margin=dict(l=40, r=10, t=30, b=40),  # keep right margin small
                )               
                temp_fig.update_traces(
                    selector=dict(name="temp_c"),
                    name="Temp (°C)",
                )
                temp_fig.update_traces(
                    selector=dict(name="dewpoint_c"),
                    name="Dewpoint Temp (°C)",
                )

                st.plotly_chart(
                    temp_fig, 
                    width="stretch", 
                    config = {
                    "scrollZoom": False,
                    "doubleClick": False,
                    "displayModeBar": False,
                    "staticPlot": True
                    }
                )
        with mid_graph:
            with st.container(border=True):
                st.subheader("Humidity")
                humidity_fig = px.bar(
                    forecast_data,
                    x = "time",
                    y = "humidity",
                    title = None,
                
                )
                humidity_fig.update_yaxes(range=[0,100], title = "%")
                humidity_fig.update_xaxes(title="time")
                humidity_fig.update_layout(hovermode="x unified")

                st.plotly_chart(
                    humidity_fig, 
                    width="stretch", 
                    config = {
                    "scrollZoom": False,
                    "doubleClick": False,
                    "displayModeBar": False,
                    "staticPlot": True
                    }
                )
        with right_graph:
            with st.container(border=True):
                st.subheader("Wind Speed")
                wind_fig = px.bar(
                    forecast_data,
                    x = "time",
                    y = "wind_mph",
                    title = None,
                
                )
                wind_fig.update_yaxes(range=[0,100], title = "MPH")
                wind_fig.update_xaxes(title="time")
                wind_fig.update_layout(hovermode="x unified")

                st.plotly_chart(
                    wind_fig, 
                    width="stretch", 
                    config = {
                    "scrollZoom": False,
                    "doubleClick": False,
                    "displayModeBar": False,
                    "staticPlot": True
                    }
                )
        rain_graph, score_graph = st.columns(2)
        with rain_graph:
            with st.container(border=True):
                st.subheader("Chance of Rain")
                precip_fig = px.bar(
                    forecast_data,
                    x = "time",
                    y = "chance_of_rain",
                    title = None,
                
                )
                precip_fig.update_yaxes(range=[0,100], title = "%")
                precip_fig.update_xaxes(title="time")
                precip_fig.update_layout(hovermode="x unified")

                st.plotly_chart(
                    precip_fig, 
                    width="stretch", 
                    config = {
                    "scrollZoom": False,
                    "doubleClick": False,
                    "displayModeBar": False,
                    "staticPlot": True
                    }
                )
            
        with score_graph:
            with st.container(border=True):
                st.subheader("Drying Score")
                score_fig = px.bar(
                    forecast_data,
                    x = "time",
                    y = "Drying_Score",
                    title = None,
                
                )
                score_fig.add_hline(y=70, line_dash="dash", line_color="green", 
                    annotation_text="Excellent", annotation_position="top left")

                score_fig.add_hline(y=50, line_dash="dash", line_color="orange", 
                    annotation_text="Good", annotation_position="top left")

                score_fig.add_hline(y=30, line_dash="dash", line_color="red", 
                    annotation_text="Meh", annotation_position="top left")
                score_fig.update_yaxes(range=[0,100], title = "drying score")
                score_fig.update_xaxes(title="time")
                score_fig.update_layout(hovermode="x unified")

                st.plotly_chart(
                    score_fig, 
                    width="stretch", 
                    config = {
                    "scrollZoom": False,
                    "doubleClick": False,
                    "displayModeBar": False,
                    "staticPlot": True
                    }
                )
            