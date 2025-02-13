import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from requests.exceptions import SSLError
import json
import shutil
import sys
import time
import logging

# Step 1: Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(filename='gfr.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Create a logger
logger = logging.getLogger(__name__)

# Define the lock file path
lock_file = script_dir + 'rover.lock'

# Step 2: Construct the path to the configuration file
config_path = os.path.join(script_dir, 'rover_config.json')

# Step 3: Load the configuration file
def load_config(config_file):
    with open(config_file, 'r') as file:
        return json.load(file)

# Load the configuration
config = load_config(config_path)

# Access the configuration values
base_url = config["base_url"]
user_id = config["user_id"]
password = config["password"]
client_cert_path = config["client_cert_path"]
root_cert_path = config["root_cert_path"]
client_key_path = config["client_key_path"]
incoming_HL7_folder_path = config["incoming_HL7_folder_path"]
incoming_xml_folder_path = config["incoming_xml_folder_path"]
incomingMuleFolder = config["incomingMuleFolder"]
app_name = config["app_name"]
app_version = config["app_version"]
mule_log_file = config["mule_log_file"]

def is_locked():
    """Check if the lock file exists."""
    return os.path.exists(lock_file)

def create_lock():
    """Create the lock file."""
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))  # Store the process ID in the lock file

def remove_lock():
    """Remove the lock file."""
    os.remove(lock_file)

def check_log_for_upload(xml_file_name):
    """Check if the log file contains the specified search string in the last 1000 lines."""
    search_string = "file: " + xml_file_name + ", Successfully Uploaded"
    
    try:
        with open(mule_log_file, 'r') as file:
            # Read the last 1000 lines
            lines = file.readlines()[-1000:]  # Get the last 1000 lines
            
            for line in lines:
                if search_string in line:
                    return True
    except FileNotFoundError:
        logger.error(f"Log file '{mule_log_file}' not found.")
        return False
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False

    return False


# Step 1: Authentication
def authenticate(base_url):
    try:
        with requests.Session() as session:
            # Set the client certificate and root certificate for the session
            session.cert = (client_cert_path, client_key_path)  # Use (cert, key) if both are required
            session.verify = root_cert_path

            # Set the custom User-Agent header
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; '+ app_name +'; '+ app_version +') Gecko/20100101 Firefox/113.0'
            })

            response = session.get(base_url)

            # print(session.cookies)

            # Perform the POST request for authentication
            response = session.post(base_url+'hl7pull.aspx', data={
                'Page': 'Login',
                'Mode': 'Silent',
                'UserID': user_id,
                'Password': password
            })

            # Check response status and content
            if response.status_code == 200:
                # print(base_url)
                # print(response.status_code)
                # print(response.headers)
                # print(response.text)
                # print(session.cookies)
                if '<Authentication>AccessGranted</Authentication>' in response.text:
                    # Save cookies for later use
                    cookies = session.cookies
                    logger.info("Authentication successful.")
                    return session, cookies
                else:
                    logger.info("Authentication failed.")
                    return None, None
            else:
                logger.info(f"Authentication HTTP request failed with status code {response.status_code}.")
                return None, None

    except SSLError as e:
        logger.error(f"SSL Error: {e}")
        return None, None

def query_new_results(session, base_url, cookies, pending=False):
    data = {
        'Page': 'HL7',
        'Query': 'NewRequests'
    }
    if pending:
        data['Pending'] = 'Yes'

    response = session.post(base_url + 'hl7pull.aspx', data=data, cookies=cookies)
    
    if response.status_code == 200:

        # Parse the XML response
        root = ET.fromstring(response.text)

        # Extract the MessageCount from the root element
        message_count = root.get('MessageCount')
        if message_count is None:
            logger.info("MessageCount attribute not found in the response.")
            return False

        # Convert message_count to integer for comparison
        try:
            message_count = int(message_count)
        except ValueError:
            logger.info("MessageCount is not a valid integer.")
            return False

        # Find all Message elements
        messages = root.findall('.//Message')
        actual_count = len(messages)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f'response_{timestamp}.xml'
        file_path = os.path.join(incoming_xml_folder_path, file_name)
        
        with open(file_path, 'w') as file:
            file.write(response.text)
        logger.info(f"Response saved to {file_path}")

        # Verify the count
        if actual_count != message_count:
            logger.info(f"Mismatch: Expected {message_count} messages, but found {actual_count}.")
            return False


        # Specify the source file path and the destination file path
        source = file_path
        destination = incomingMuleFolder

        # Copy the file
        shutil.copy(source, destination)

        logger.info(f"File copied from {source} to {destination}")

        time.sleep(30)

        if check_log_for_upload(file_name):
            return True
        else:
            logger.info(f"Oscar upload failed for {file_name}.")
            return False

        # Process and save each message into HL7
        # for i, message in enumerate(messages):
        #     message_content = ET.tostring(message, encoding='unicode', method='text').strip()
            
        #     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        #     file_path = os.path.join(incoming_HL7_folder_path, f'HL7Message_{timestamp}_{i + 1}.HL7')
            
        #     with open(file_path, 'w') as file:
        #         file.write(message_content)
        #     print(f"Message {i + 1} saved to {file_path}")

    else:
        logger.info("XML fetch HTTP request failed.")
        return False

def send_acknowledgement(session, base_url, cookies, positive=True):
    ack_status = 'Positive' if positive else 'Negative'
    response = session.post(base_url + 'hl7pull.aspx', data={
        'Page': 'HL7',
        'ACK': ack_status
    }, cookies=cookies)
    
    if response.status_code == 200:
        #print(response.text)
        if '<HL7Messages/>' in response.text:
            logger.info("Acknowledgement sent.")
        elif '<HL7Messages ReturnCode="1"/>' in response.text:
            logger.info("Error processing acknowledgement.")
        elif '<HL7Messages ReturnCode="0"/>' in response.text:
            logger.info("Acknowledgement successfully processed.")
        else:
            logger.info("Unexpected response for acknowledgement.")
    else:
        logger.info("ACK HTTP request failed.")

def sign_out(session, base_url, cookies):
    response = session.post(base_url, data={
        'Logout': 'Yes'
    }, cookies=cookies)
    
    if response.status_code == 200:
        logger.info("Signed out successfully.")
    else:
        logger.info("Signout HTTP request failed.")

def main():

    if is_locked():
        logger.info("Script is already running. Exiting.")
        sys.exit(1)

    # Create a lock file
    create_lock()

    os.makedirs(incoming_HL7_folder_path, exist_ok=True)
    os.makedirs(incoming_xml_folder_path, exist_ok=True)

    session, cookies = authenticate(base_url)
    
    if session and cookies:
        status = query_new_results(session, base_url, cookies, pending=True)

        if(status == True):
            send_acknowledgement(session, base_url, cookies, positive=True)
            logger.info("positive send acknowledgement")
        else:
            send_acknowledgement(session, base_url, cookies, positive=False)
            logger.info("negative send acknowledgement")

        sign_out(session, base_url, cookies)

    # Ensure the lock file is removed after the script finishes
    remove_lock()

if __name__ == "__main__":
    main()