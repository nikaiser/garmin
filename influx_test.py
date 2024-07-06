from influxdb_client import InfluxDBClient

client = InfluxDBClient(url="http://2009-macbookpro:8086", token="YOUR_INFLUX_TOKEN", org="homenet")
query_api = client.query_api()

query = 'from(bucket:"garmin") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "distance_mycollector")'
result = query_api.query(query)

for table in result:
    for record in table.records:
        print(record)