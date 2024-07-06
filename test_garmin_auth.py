#!/usr/bin/env python3

from garminconnect import Garmin
import os

# Path to the directory where your OAuth tokens are stored
token_store = '/home/xubuntu/garmin'  # Update this to the path of your token directory

def init_garmin(token_store):
    try:
        garmin_client = Garmin()
        garmin_client.login(token_store)  # Use the login method with the token directory
        print("Successfully connected to Garmin using tokens")
        return garmin_client
    except Exception as err:
        print(f"Error connecting to Garmin using token: {err}")
        return None

client = init_garmin(token_store)
if client is not None:
    print("Garmin client initialized successfully")
else:
    print("Failed to initialize Garmin client")
