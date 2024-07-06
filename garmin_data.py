#!/usr/bin/env python3
from garminconnect import Garmin
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, date, timedelta
import pytz
import json
import os
import time
import logging

# Load configuration
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

# Configure logging
logging.basicConfig(filename=config['log_file'], level=logging.DEBUG, format='%(asctime)s %(message)s')
logging.info("Script started.")

TIMEZONE = pytz.timezone(config['timezone'])

def init_garmin(config):
    try:
        garmin_client = Garmin()
        garmin_client.login(tokenstore=config['garmin_auth']['token_store'])
        logging.info("Successfully connected to Garmin using tokens")
        return garmin_client
    except Exception as err:
        logging.error(f"Error connecting to Garmin using token: {err}")
        return None

# When using the config
config = load_config()
garmin_client = init_garmin(config)

influxdb_token = os.environ.get('INFLUX_TOKEN')
if not influxdb_token:
    raise ValueError("INFLUXDB_TOKEN environment variable is not set")

# Use this token when initializing the InfluxDB client
client = InfluxDBClient(
    url=config['influxdb']['url'],
    token=influxdb_token,
    org=config['influxdb']['org']
)

def utc_to_local(timestamp):
    utc_time = pytz.utc.localize(timestamp)
    return utc_time.astimezone(TIMEZONE)

def convert_to_influx_timestamp(timestamp):
    if isinstance(timestamp, (int, float)):
        return int(timestamp * 1e9)
    elif isinstance(timestamp, str):
        try:
            dt = datetime.strptime(timestamp, config['garmin_timestamp_format'])
            return int(dt.timestamp() * 1e9)
        except ValueError:
            pass
    elif isinstance(timestamp, datetime):
        return int(timestamp.timestamp() * 1e9)
    return None

def get_data_from_garmin(client, command, retries=3):
    for attempt in range(retries):
        try:
            logging.info(f"Executing command: {command}")
            return eval(f"client.{command}")
        except Exception as e:
            logging.error(f"Error: {e}. Attempt {attempt + 1} of {retries}")
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff

def process_data_for_influxdb(data, measurement, tags=None):
    points = []
    for entry in data:
        timestamp = convert_to_influx_timestamp(entry.get('timestamp') or entry.get('startTimeLocal') or entry.get('startGMT'))
        if timestamp is None:
            continue
        
        point = Point(measurement)
        for tag_key, tag_value in (tags or {}).items():
            point = point.tag(tag_key, tag_value)
        
        for key, value in entry.items():
            if key not in ['timestamp', 'startTimeLocal', 'startGMT'] and isinstance(value, (int, float, str)):
                point = point.field(key, value)
        
        point = point.time(timestamp, WritePrecision.NS)
        points.append(point)
    return points

def get_activities(client, start_date, end_date):
    activities = get_data_from_garmin(client, f"get_activities(start_date='{start_date}', end_date='{end_date}')")
    return [{k: v for k, v in activity.items() if k in config['activity_measurements'] + ['startTimeLocal']} 
            for activity in activities]

def get_steps(client, date):
    return get_data_from_garmin(client, f'get_steps_data("{date}")')

def get_heart_rate_data(client, date):
    return get_data_from_garmin(client, f'get_heart_rates("{date}")')["heartRateValues"]

def get_sleep_data(client, date):
    sleep_data = get_data_from_garmin(client, f'get_sleep_data("{date}")')
    if sleep_data and 'sleepStages' in sleep_data:
        return [{
            'timestamp': datetime.fromtimestamp(stage['startTimeInSeconds']),
            'stage': stage['stage'],
            'durationInSeconds': stage['durationInSeconds']
        } for stage in sleep_data['sleepStages']]
    return []

def get_last_fetch_date():
    try:
        with open(config['last_fetch_file'], 'r') as f:
            return datetime.strptime(f.read().strip(), '%Y-%m-%d').date()
    except FileNotFoundError:
        return datetime.strptime(config['start_date'], '%Y-%m-%d').date()

def save_last_fetch_date(fetch_date):
    with open(config['last_fetch_file'], 'w') as f:
        f.write(fetch_date.strftime('%Y-%m-%d'))

def write_to_influxdb(data):
    client = InfluxDBClient(url=config['influxdb']['url'], token=config['influxdb']['token'], org=config['influxdb']['org'])
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    write_api.write(config['influxdb']['bucket'], config['influxdb']['org'], data)
    
    client.close()

def main():
    garmin_client = init_garmin()
    if garmin_client is None:
        return

    try:
        last_fetch_date = get_last_fetch_date()
        end_date = date.today()
        
        while last_fetch_date <= end_date:
            logging.info(f"Fetching data for date: {last_fetch_date}")
            
            activities = get_activities(garmin_client, last_fetch_date, last_fetch_date)
            steps = get_steps(garmin_client, last_fetch_date)
            heart_rate = get_heart_rate_data(garmin_client, last_fetch_date)
            sleep = get_sleep_data(garmin_client, last_fetch_date)
            
            all_data = []
            all_data.extend(process_data_for_influxdb(activities, 'activity', {'device': 'garmin'}))
            all_data.extend(process_data_for_influxdb(steps, 'steps', {'device': 'garmin'}))
            all_data.extend(process_data_for_influxdb(heart_rate, 'heart_rate', {'device': 'garmin'}))
            all_data.extend(process_data_for_influxdb(sleep, 'sleep', {'device': 'garmin'}))
            
            write_to_influxdb(all_data)
            
            last_fetch_date += timedelta(days=1)
            save_last_fetch_date(last_fetch_date)
            time.sleep(2.5)  # Respect rate limits
    except Exception as e:
        logging.error(f"Script encountered an error: {e}")
    
    logging.info("Script finished execution.")

if __name__ == "__main__":
    main()
