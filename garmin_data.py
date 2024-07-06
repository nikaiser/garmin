#!/usr/bin/env python3

from garminconnect import Garmin
from datetime import date, timedelta, datetime
import time
import logging

# Configure logging
logging.basicConfig(filename='/tmp/garmin_script_run.log', level=logging.DEBUG, format='%(asctime)s %(message)s')

logging.info("Script started.")

# Path to the directory where your OAuth tokens are stored
token_store = '/home/xubuntu/garmin'  # Update this to the path of your token directory
start_date = date(2023, 9, 1)
end_date = date(2023, 9, 5)  # Reduced date range for testing
garmin_timestamp_format = "%Y-%m-%d %H:%M:%S"
influxdb_time_format = "%Y-%m-%dT%H:%M:%SZ"

def init_garmin(token_store):
    try:
        garmin_client = Garmin()
        garmin_client.login(token_store)  # Use the login method with the token directory
        logging.info("Successfully connected to Garmin using tokens")
        return garmin_client
    except Exception as err:
        logging.error(f"Error connecting to Garmin using token: {err}")
        return None

def get_data_from_garmin(client, command):
    try:
        logging.info(f"Executing command: {command}")
        return eval(command)
    except Exception as e:
        logging.error(f"Error: {e}")
        quit()

def create_line_protocol(measurement, value, timestamp):
    # Parse the timestamp from Garmin format to InfluxDB format
    garmin_time = datetime.strptime(timestamp, garmin_timestamp_format)
    influxdb_time = garmin_time.strftime(influxdb_time_format)
    epoch_time = int(garmin_time.timestamp() * 1e9)  # Convert to nanoseconds
    return f"{measurement} value={value} {epoch_time}"

client = init_garmin(token_store)
if client is None:
    quit()

try:
    activities = get_data_from_garmin(client, "client.get_activities(0, 10)")
    activity_list = ['distance', 'duration', 'averageSpeed', 'maxSpeed', 'averageHR', 'maxHR', 'averageRunningCadenceInStepsPerMinute', 'steps', 'avgStrideLength']

    for activity in activities:
        timestamp = activity['startTimeLocal']
        for measurement in activity_list:
            if measurement in activity:
                line_protocol = create_line_protocol(measurement, activity[measurement], timestamp)
                print(line_protocol)
                logging.info(f"Data: {line_protocol}")

    time_delta = end_date - start_date
    for x in range(time_delta.days + 1):
        day = str(start_date + timedelta(days=x))
        logging.info(f"Fetching step data for day: {day}")
        step_data = get_data_from_garmin(client, f'client.get_steps_data("{day}")')
        for step in step_data:
            timestamp = step['startGMT']
            line_protocol = create_line_protocol('steps', step['steps'], timestamp)
            print(line_protocol)
            logging.info(f"Step data: {line_protocol}")
        time.sleep(2.5)
except Exception as e:
    logging.error(f"Script encountered an error: {e}")

logging.info("Script finished execution.")
