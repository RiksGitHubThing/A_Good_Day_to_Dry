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
    df["Drying_Score"] = df.apply(lambda row: get_dry_score(row["is_day"], row["temp_c"], row["wind_mph"], row["humidity"], row["precip_mm"], row["dewpoint_c"]), axis=1)
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
    if (not is_day or rain or (temp-dew_point < 2)):
        score = 0
    else:
        #np points if it's too cold, but 1pt per deg above that
        if temp < 2:
            return 0
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
    return round(max(0, min(100, score)))



    score = max (0, min(100, score));

    return round(score)

def get_next_good_drying_time(forecast_data):
    formatted_next = ""
    next_good_drying_time = forecast_data.loc[forecast_data["Drying_Score"] >= 60].sort_values("time")
    if next_good_drying_time.empty:
        next_time = None
    else:
        next_time = next_good_drying_time.iloc[0]["time"]
        formatted_next_time = next_time.strftime("%H:%M") if now else "Unknown"
        formatted_next_date = next_time.strftime("%A, %B %d %Y") if now else "Unknown"
        formatted_next = (f"The next good time to dry is {formatted_next_time} on {formatted_next_date}")
    return formatted_next if formatted_next else None

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
#=========UI Stuff =========
# st.write(move_forecast_to_dataframe(get_forecast_data("Walsall")))
city = st.text_input("Where are your wet pants?")

if st.button("Check the Skies"):
    data_error=False
    sun_has_set=False
    data = get_weather(city)

    if data:
        set_now(data)
        set_here(data)
        formatted_here = here.capitalize()
        formatted_now = now.strftime("%H:%M") if now else "Unknown"
        formatted_date = now.strftime("%A, %B %d %Y") if now else "Unknown"
   
        st.header(f"The current time in {formatted_here} is {formatted_now} on {formatted_date}")


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
        # Fix for retrieving sunset time from forecastday,
        # which is a list with one or more days (usually forecastday[0] is today)
        sunset = data['forecast']['forecastday'][0]['astro']['sunset']
        #st.write (forecast_data)
        if not is_day:
            st.warning(f"##  🌕 Erm... Look out the window. It's night time")
        st.divider()
        current_drying_score = get_dry_score(is_day, temp, wind, humidity, raining, dewpoint)

        if current_drying_score >= 60:
            st.info ("**NOW** is a good time to dry!")
        else:
            st.info(get_next_good_drying_time(forecast_data))

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
        if (not is_day or raining > 2 or temp <=0 or current_drying_score >75):
            score_card, issue_card = st.columns(2)
            with score_card:
                with st.container(border=True):
                    st.metric ("Current Drying Score", current_drying_score)
            with issue_card:
                with st.container(border=True):
                    st.metric("You might want to watch out for...", "It's night" if not is_day else "It's raining" if raining > 0 else "It's freezing" if temp <= 2 else "Crispy Washing" if current_drying_score > 75 else "eldritch abominations")
        else:
            with st.container(border=True):
                    st.metric ("Current Drying Score", current_drying_score)
        st.divider()
        if current_drying_score > 30:
            dry_light, dry_med, dry_heavy = st.columns(3)
            est_L = estimate_drying_time(dewpoint, temp, humidity, wind, "L")
            est_M = estimate_drying_time(dewpoint, temp, humidity, wind, "M")
            est_H = estimate_drying_time(dewpoint, temp, humidity, wind, "H")
            with dry_light:
                with st.container(border=True):
                    st.metric ("Light Fabrics will dry in", f"{est_L} hours")
            with dry_med:
                with st.container(border=True):
                    st.metric ("Medium Fabrics will dry in", f"{est_M} hours")
            with dry_heavy:
                with st.container(border=True):
                    st.metric ("Heavy Fabrics will dry in", f"{est_H} hours")
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
                    y = "wind_kph",
                    title = None,
                
                )
                wind_fig.update_yaxes(range=[0,100], title = "Kph")
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
                st.subheader("Precipitation")
                precip_fig = px.bar(
                    forecast_data,
                    x = "time",
                    y = "precip_mm",
                    title = None,
                
                )
                precip_fig.update_yaxes(range=[0,4], title = "mm")
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
            