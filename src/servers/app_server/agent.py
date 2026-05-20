import os
import logging
import sys
import threading
from src.config import DATA_DIR
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s -AGENT- %(message)s', stream=sys.stdout)

class FileAgent:
    #setup the data folder to store files and create a lock to prevent file conflicts
    def __init__(self):
        self.data_folder = DATA_DIR
        self.lock = threading.Lock()

        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)

        logging.info("Agent initialized and data folder is ready.")

    #check if we already have today's forecast for the city to keep time and API calls
    def get_cached_forecast(self, city_name):
        filename = f"{city_name}_forecast.txt"
        filepath = os.path.join(self.data_folder,filename)

        if os.path.exists(filepath):
            file_timestamp = os.path.getmtime(filepath)
            file_date = date.fromtimestamp(file_timestamp)

            if file_date == date.today():
                logging.info(f"CACHE HIT: Served '{city_name}' from local storage")
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        return content.replace("DAILY RECOMMENDATION\n\n", "", 1).strip()
                except Exception as e:
                    logging.error(f"Cache read error: {e}")
                    return None
        return None

    #save a text string into a file safely using the lock
    def save_text_file(self, filename, content):
        file_path = os.path.join(self.data_folder, filename)
        try:
            with self.lock:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("DAILY RECOMMENDATION\n\n")
                    f.write(content)
            logging.info(f"Agent actively saved text to {file_path}")
        except Exception as e:
            logging.error(f"Save text error: {e}")

    #save binary data into a file safely using the lock
    def save_binary_file(self, filename,binary_data):
        file_path = os.path.join(self.data_folder,filename)
        try:
            with self.lock:
                with open(file_path, 'wb') as f:
                    f.write(binary_data)
            logging.info(f"Agent actively saved binary file to {file_path}")
        except Exception as e:
            logging.error(f"Save binary error: {e}")

    #look inside the data folder and return a formatted list of all saved files
    def get_ftp_file_list(self):
        try:
            files = os.listdir(self.data_folder)
            if not files:
                return "FTP Directory is empty"

            lines = ["--- WEATHERWEAR FTP ARCHIVE ---"]
            for file in files:
                filepath = os.path.join(self.data_folder,file)
                size_kb = os.path.getsize(filepath)/1024
                # Using a simple dash instead of folder icons
                lines.append(f"- {file} (Size: {size_kb:.1f} KB)")

            formatted_list = "\n".join(lines) + "\n"
            logging.info("Requirement 2: Agent generated custom FTP list.")
            return formatted_list
        except Exception as e:
            return f"FTP Error: {e}"

    #read a file from the folder, prevent hackers from reading files outside the folder.
    def get_ftp_file_content(self, filename):
        filename = os.path.basename(filename)
        file_path = os.path.join(self.data_folder, filename)
        try:
            if not os.path.exists(file_path):
                logging.warning(f"FTP Error: File '{filename}' not found.")
                return f"Error: The file '{filename}' does not exist in the archive."

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if filename.endswith('.csv'):
                lines = content.split('\n')
                pretty_text = f"Hourly Weather Data ({filename})\n"
                pretty_text += "="*45 + "\n"

                for line in lines:
                    line = line.strip()
                    if not line: continue

                    if line.startswith("time"):
                        pretty_text += "Date & Time         | Temp   | Rain %\n"
                        pretty_text += "-"*45 + "\n"

                    elif line.startswith("202"):
                        parts = line.split(',')
                        if len(parts)>= 3:
                            time_str = parts[0].replace("T", "  ")
                            temp = parts[1]
                            rain = parts[2]
                            pretty_text += f"{time_str} | {temp}°C | {rain}%\n"
                logging.info(f"Requirement 2: Parsed CSV beautifully for {filename}")
                return pretty_text

            logging.info(f"Requirement 2: FTP Read successful for {filename}")
            return content

        except Exception as e:
            logging.error(f"FTP Read Error: {e}")
            return f"Error reading file: {e}"