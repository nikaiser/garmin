#!/Users/beacon/garmin/garmin/bin python3

from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
)

from datetime import date, timedelta
import time
import sys
import logging

logging.basicConfig(level=logging.DEBUG)
start_date = date(2023, 9, 1)
end_date = date(2023, 9, 17)

today = date.today()
speed_multiplier = 3.584392177
garmin_username = 'your_garmin_username'
garmin_password = 'your_garmin_password'

garmin_date_format = "%Y-%m-%d"
influxdb_time_format = "%Y-%m-%dT%H:%M:%SZ"
gather_hrv_data = False

def get_data_from_garmin(component, command, client=None):
    try:
        result = eval(command)
    except (
        GarminConnectConnectionError,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    ) as err:
        print(f"Error occurred during Garmin Connect Client get {component}: {err}")
        quit()
    except Exception as e:  # pylint: disable=broad-except
        print(e)
        print(f"Unknown error occurred during Garmin Connect Client get {component}")
        quit()
    return result

def connect_to_garmin(username, password):
    try:
        client = Garmin(username, password)
    except (
            GarminConnectConnectionError,
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
    ) as err:
        print(f"Error occurred during Garmin Connect Client get initial client: {err}")
        quit()
    except Exception:
        print("Unknown error occurred during Garmin Connect Client get initial client")
        quit()
    client.login()
    return client

def create_line_protocol(measurement, measurement_value, datestamp, tags=None):
    tags_str = ""
    if tags:
        tags_str = ",".join([f"{k}={v}" for k, v in tags.items()])
    return f"{measurement},{tags_str} value={measurement_value} {int(time.mktime(time.strptime(datestamp, influxdb_time_format)) * 1e9)}"

def create_influxdb_daily_measurement(user_data):
    for heading, value in user_data.items():
        if value is None:
            continue
        if "minutes" in heading.lower():
            value = value / 60
        line_protocol = create_line_protocol(heading, value, user_data['current_date'])
        print(line_protocol)

def create_influxdb_multi_measurement(user_data, subset_list_of_stats, start_time_heading, date_format, timestamp_offset=False):
    temp_dict = {}
    for entry in user_data:
        activity_start = entry[start_time_heading]
        if timestamp_offset:
            timestamp = time.mktime(time.strptime(activity_start, date_format)) + 14400
        else:
            timestamp = time.mktime(time.strptime(activity_start, date_format))
        current_date = time.strftime(influxdb_time_format, time.localtime(round(timestamp)))
        for heading in subset_list_of_stats:
            try:
                temp_dict[current_date].update({heading: entry[heading]})
            except KeyError:
                temp_dict[current_date] = {heading: entry[heading]}
    for heading, inner_dict in temp_dict.items():
        for inner_heading, value in inner_dict.items():
            if value is None:
                continue
            if "speed" in inner_heading.lower():
                value = value * speed_multiplier
            line_protocol = create_line_protocol(inner_heading, value, heading)
            print(line_protocol)

client = connect_to_garmin(username=garmin_username, password=garmin_password)

activities = get_data_from_garmin("activities", "client.get_activities(0, 10)", client=client)
activity_list = ['distance', 'duration', 'averageSpeed', 'maxSpeed', 'averageHR', 'maxHR', 'averageRunningCadenceInStepsPerMinute', 'steps', 'avgStrideLength']
time_delta = end_date - start_date

create_influxdb_multi_measurement(activities, activity_list, 'startTimeLocal', '%Y-%m-%d %H:%M:%S', timestamp_offset=True)
for x in range(time_delta.days + 1):
    day = str(start_date + timedelta(days=x))
    client_get_data = f'client.get_steps_data("{day}")'
    client_get_sleep = f'client.get_sleep_data("{day}")'
    client_get_stats = f'client.get_stats("{day}")'

    step_data = get_data_from_garmin("step_data", client_get_data, client=client)
    stats = get_data_from_garmin("stats", client_get_stats, client=client)
    sleep_data = get_data_from_garmin("sleep_data", client_get_sleep, client=client)
    sleep_data_date = time.mktime(time.strptime(sleep_data['dailySleepDTO']['calendarDate'], garmin_date_format))
    daily_stats_date = time.mktime(time.strptime(stats['calendarDate'], garmin_date_format)) + 20000

    floor_data = {
        'floors_ascended': stats['floorsAscended'],
        'floors_descended': stats['floorsDescended'],
        "current_date": time.strftime(influxdb_time_format, time.localtime(daily_stats_date))
    }
    useful_daily_sleep_data = {
        'awake_minutes': sleep_data['dailySleepDTO']['awakeSleepSeconds'],
        'light_sleep_minutes': sleep_data['dailySleepDTO']['lightSleepSeconds'],
        'deep_sleep_minutes': sleep_data['dailySleepDTO']['deepSleepSeconds'],
        'total_sleep_minutes': sleep_data['dailySleepDTO']['sleepTimeSeconds'],
        'current_date': time.strftime(influxdb_time_format, time.localtime(sleep_data_date))
    }
    heart_rate = {
        "lowest_heart_rate": stats['minHeartRate'],
        "highest_heart_rate": stats['maxHeartRate'],
        "resting_heart_rate": stats['restingHeartRate'],
        "current_date": time.strftime(influxdb_time_format, time.localtime(daily_stats_date))
    }
    daily_stats = {
        "total_burned_calories": stats['totalKilocalories'],
        "current_date": time.strftime(influxdb_time_format, time.localtime(daily_stats_date)),
        "total_steps": stats['totalSteps'],
        "daily_step_goal": stats['dailyStepGoal'],
        "highly_active_minutes": stats['highlyActiveSeconds'],
        "moderately_active_minutes": stats['activeSeconds'],
        "sedentary_minutes": stats['sedentarySeconds']
    }
    if gather_hrv_data:
        client_get_hrv = f'client.get_hrv_data("{day}")'
        hrv_data = get_data_from_garmin("hrv_data", client_get_hrv, client=client)
        hrv_daily_summary = {
            "hrv_last_night_avg": hrv_data['hrvSummary']['lastNightAvg'],
            "hrv_weekly_avg": hrv_data['hrvSummary']['weeklyAvg'],
            "hrv_status": hrv_data['hrvSummary']['status'],
            "current_date": time.strftime(influxdb_time_format, time.localtime(daily_stats_date))
        }
        create_influxdb_daily_measurement(hrv_daily_summary)
    create_influxdb_daily_measurement(daily_stats)
    create_influxdb_daily_measurement(useful_daily_sleep_data)
    create_influxdb_daily_measurement(heart_rate)
    create_influxdb_daily_measurement(floor_data)
    step_list = ['steps']
    create_influxdb_multi_measurement(step_data, step_list, 'startGMT', "%Y-%m-%dT%H:%M:%S.%f")
    print(day)
    time.sleep(2.5)

print("")
