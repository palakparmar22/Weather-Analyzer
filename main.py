import os
import json
import asyncio
import aiohttp
import argparse
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone

class WeatherLogger:
    def __init__(self, api_key, data_file="weather_data.json"):
        self.api_key = api_key
        self.data_file = data_file
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.plots_dir = "plots"
        os.makedirs(self.plots_dir, exist_ok=True)
        self._init_json_file()

    def _init_json_file(self):
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w') as f:
                json.dump([], f)

    def _kelvin_to_celsius(self, kelvin):
        return round(kelvin - 273.15, 2)

    def _is_duplicate_entry(self, city, current_time):
        two_hours_ago = current_time - timedelta(hours=2)
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                for entry in data:
                    if entry['city'].lower() == city.lower():
                        entry_time = datetime.fromisoformat(entry['utc_timestamp'].replace('Z', '+00:00'))
                        if entry_time > two_hours_ago:
                            return True
        except:
            pass
        return False

    async def _fetch_weather_data(self, session: aiohttp.ClientSession, city):
        try:
            url = f"{self.base_url}?q={city}&appid={self.api_key}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    weather_data = {
                        'city': data['name'],
                        'temperature': self._kelvin_to_celsius(data['main']['temp']),
                        'description': data['weather'][0]['description'],
                        'humidity': data['main']['humidity'],
                        'utc_timestamp': datetime.now(timezone.utc).isoformat(),
                        'local_timestamp': datetime.now().isoformat()
                    }
                    return weather_data
                else:
                    print(f"Error fetching data for {city}: HTTP {response.status}")
                    return None
        except Exception as e:
            print(f"Error fetching data for {city}: {e}")
            return None

    async def fetch_and_log_weather(self, cities):
        print(f"\n Fetching weather data for {len(cities)} cities...")

        current_time = datetime.now(timezone.utc)
        valid_cities = []
        skipped_cities = []

        for city in cities:
            if not self._is_duplicate_entry(city.strip(), current_time):
                valid_cities.append(city.strip())
            else:
                skipped_cities.append(city.strip())

        if skipped_cities:
            print(f" Skipped {len(skipped_cities)} cities (logged within 2 hours): {', '.join(skipped_cities)}")

        if not valid_cities:
            print("No new cities to fetch data for.")
            return []

        # Fetch data asynchronously
        logged_data = []
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_weather_data(session, city) for city in valid_cities]
            results = await asyncio.gather(*tasks)

            for weather_data in results:
                if weather_data:
                    self._save_weather_data(weather_data)
                    logged_data.append(weather_data)
                    print(f"{weather_data['city']}: {weather_data['temperature']}°C, {weather_data['description']}")

        print(f"\n Successfully logged weather data for {len(logged_data)} cities!")
        return logged_data

    def _save_weather_data(self, weather_data):
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
        except:
            data = []

        data.append(weather_data)

        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_all_logs(self):
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                # Sort by timestamp (newest first)
                return sorted(data, key=lambda x: x['utc_timestamp'], reverse=True)
        except:
            return []
            
    def display_logs_table(self):
        logs = self.get_all_logs()
        if not logs:
            return

        print(f"\n Weather Logs ({len(logs)} entries):")
        print("=" * 100)
        print(f"{'City':<15} {'Temp (°C)':<10} {'Description':<20} {'Humidity (%)':<12} {'Timestamp':<20}")
        print("-" * 100)

        for log in logs:
            timestamp = datetime.fromisoformat(log['local_timestamp'].replace('Z', '')).strftime('%Y-%m-%d %H:%M')
            print(f"{log['city']:<15} {log['temperature']:<10} {log['description']:<20} {log['humidity']:<12} {timestamp:<20}")

    def get_city_avg_temp(self):
        logs = self.get_all_logs()
        city_temps = {}

        for log in logs:
            city = log['city']
            if city not in city_temps:
                city_temps[city] = []
            city_temps[city].append(log['temperature'])

        averages = {city: round(sum(temps) / len(temps), 2) 
                   for city, temps in city_temps.items()}

        return averages

    def get_hottest_coldest_cities(self, last_24h=False):
        logs = self.get_all_logs()

        if last_24h:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            logs = [log for log in logs 
                   if datetime.fromisoformat(log['utc_timestamp'].replace('Z', '+00:00')) > cutoff_time]
            
        if not logs:
            return None, None

        hottest = max(logs, key=lambda x: x['temperature'])
        coldest = min(logs, key=lambda x: x['temperature'])

        return hottest, coldest
    
    def plot_temp(self, city):
        logs = self.get_all_logs()
        city_logs = [log for log in logs if log['city'].lower() == city.lower()]
        if not city_logs:
            print(f"\n No data found for city: {city}")
            return

        # Sort by timestamp
        city_logs.sort(key=lambda x: x['utc_timestamp'])

        timestamps = [datetime.fromisoformat(log['local_timestamp'].replace('Z', '')) 
                     for log in city_logs]
        temperatures = [log['temperature'] for log in city_logs]

        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, temperatures, marker='o', linewidth=2, markersize=6)
        plt.title(f'Temperature Trend for {city_logs[0]["city"]}', fontsize=16, fontweight='bold')
        plt.xlabel('Date & Time', fontsize=12)
        plt.ylabel('Temperature (°C)', fontsize=12)
        plt.grid(True, alpha=0.3)

        # Format x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=max(1, len(timestamps)//10)))
        plt.xticks(rotation=45)

        for i, (timestamp, temp) in enumerate(zip(timestamps, temperatures)):
            if i % max(1, len(timestamps)//8) == 0:
                plt.annotate(f'{temp}°C', (timestamp, temp), 
                           textcoords="offset points", xytext=(0,10), ha='center')

        plt.tight_layout()

        filename = f"{city.lower().replace(' ', '_')}_temp_trend.png"
        filepath = os.path.join(self.plots_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        print(f"\n Temperature trend plot saved: {filepath}")
        plt.show()


class WeatherCLI:
    def __init__(self, api_key):
        self.weather_logger = WeatherLogger(api_key)

    def display_menu(self):
        print("\n" + "="*50)
        print(' '*15 + "WEATHER ANALYZER") 
        print("="*50)
        print("1. Fetch and log weather for cities")
        print("2. View all logs (as table)")
        print("3. Get city-wise average temperature")
        print("4. Show hottest and coldest cities (overall)")
        print("5. Show hottest and coldest cities (last 24h)")
        print("6. Plot temperature trend for a city")
        print("7. Exit")
        print("="*50)

    async def option_1(self):
        cities_input = input("\n Enter city names : ").strip()
        if not cities_input:
            print("No cities provided.")
            return

        cities = [city.strip() for city in cities_input.split(',')]
        await self.weather_logger.fetch_and_log_weather(cities)

    def option_2(self):
        logs = self.weather_logger.display_logs_table()
        if not logs :
            return

        print(f"\n Weather Logs ({len(logs)} entries):")
        print("=" * 100)
        print(f"{'City':<15} {'Temp (°C)':<10} {'Description':<20} {'Humidity (%)':<12} {'Timestamp':<20}")
        print("-" * 100)

        for log in logs:
            timestamp = datetime.fromisoformat(log['local_timestamp'].replace('Z', '')).strftime('%Y-%m-%d %H:%M')
            print(f"{log['city']:<15} {log['temperature']:<10} {log['description']:<20} {log['humidity']:<12} {timestamp:<20}")

    def option_3(self):
        averages = self.weather_logger.get_city_avg_temp()
        if not averages:
            print("\n No data available for temperature averages.")
            return

        print("\n City-wise Average Temperatures:")
        print("-" * 40)
        for city, avg_temp in sorted(averages.items()):
            print(f"{city}: {avg_temp}°C")

    def option_4(self):
        hottest, coldest = self.weather_logger.get_hottest_coldest_cities(last_24h=False)

        if not hottest or not coldest:
            print("\n No data available.")
            return

        print("\n Hottest & Coldest Cities (Overall):")
        print("-" * 45)
        print(f"Hottest: {hottest['city']} at {hottest['temperature']}°C ({hottest['description']})")
        print(f"Coldest: {coldest['city']} at {coldest['temperature']}°C ({coldest['description']})")

    def option_5(self):
        hottest, coldest = self.weather_logger.get_hottest_coldest_cities(last_24h=True)

        if not hottest or not coldest:
            print("\n No data available for the last 24 hours.")
            return

        print("\n Hottest & Coldest Cities (Last 24 Hours):")
        print("-" * 50)
        print(f"Hottest: {hottest['city']} at {hottest['temperature']}°C ({hottest['description']})")
        print(f"Coldest: {coldest['city']} at {coldest['temperature']}°C ({coldest['description']})")

    def option_6(self):
        city = input("\n Enter city name for temperature trend: ").strip()
        if not city:
            print(" No city provided.")
            return

        self.weather_logger.plot_temp(city)

    async def run(self):
        while True:
            try:
                self.display_menu()
                choice = input("\n Select an option (1-7): ").strip()

                if choice == '1':
                    await self.option_1()
                elif choice == '2':
                    self.option_2()
                elif choice == '3':
                    self.option_3()
                elif choice == '4':
                    self.option_4()
                elif choice == '5':
                    self.option_5()
                elif choice == '6':
                    self.option_6()
                elif choice == '7':
                    print("\n Thank you for using Weather Analyzer!!")
                    break
                else:
                    print("\n Invalid option. Please select 1-9.")

                input("\n Press Enter to continue...")

            except Exception as e:
                print(f"\n An error occurred: {e}")
                input("\n Press Enter to continue...")

def main():
    parser = argparse.ArgumentParser(description="Asynchronous Weather Logger & Analyzer")
    parser.add_argument('--api-key', help='OpenWeatherMap API key')
    parser.add_argument('--cities', help='Comma-separated list of cities to fetch weather for')
    parser.add_argument('--plot', help='Generate temperature trend plot for specified city')

    args = parser.parse_args()

    if args.api_key and args.cities:
        print(args.cities)
        weather_cli = WeatherCLI(args.api_key)
        cities = [city.strip() for city in args.cities.split(',')]
        asyncio.run(weather_cli.weather_logger.fetch_and_log_weather(cities))
    
    elif args.api_key and args.plot:
        weather_cli = WeatherCLI(args.api_key)
        weather_cli.weather_logger.plot_temp(args.plot)

    else:
        load_dotenv()
        api_key = os.getenv("API_KEY")
        weather_cli = WeatherCLI(api_key)
        asyncio.run(weather_cli.run())

if __name__ == "__main__":
    main()
