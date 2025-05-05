import os
import sys
import requests
from pathlib import Path
import re
import getpass
import argparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("EBIRD_USERNAME")
PASSWORD = os.getenv("EBIRD_PASSWORD")

if USERNAME is None or PASSWORD is None:
    raise ValueError("EBIRD_USERNAME or EBIRD_PASSWORD environment variable not set.")

def get_ebird_session(username, password):
    """
    Logs into eBird and returns the session ID.
    """
    login_url = "https://secure.birds.cornell.edu/cassso/login"
    
    # Initial request to get the form data
    session = requests.Session()
    response = session.get(login_url)
    
    if response.status_code != 200:
        print(f"Failed to access login page. Status code: {response.status_code}")
        return None
    
    # Parse the HTML to extract form data
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the execution value
    execution_input = soup.find('input', {'name': 'execution'})
    if not execution_input:
        print("Could not find execution value in the login form.")
        return None
    
    execution_value = execution_input.get('value', '')
    
    # Find the _eventId value
    event_id_input = soup.find('input', {'name': '_eventId'})
    event_id_value = event_id_input.get('value', 'submit') if event_id_input else 'submit'
    
    # Prepare login data
    login_data = {
        "username": username,
        "password": password,
        "execution": execution_value,
        "_eventId": event_id_value,
        "rememberMe": "on"  # To stay signed in
    }
    
    # Perform login
    response = session.post(login_url, data=login_data, allow_redirects=True)
    
    # Check if login was successful
    ebird_home = "https://ebird.org/home"
    response = session.get(ebird_home)
    
    # Check for session cookie
    cookies = session.cookies.get_dict()
    if 'EBIRD_SESSIONID' in cookies:
        return cookies['EBIRD_SESSIONID']
    else:
        print("Login failed. Please check your credentials.")
        return None


def download_csv(session_id, download_url, output_file):
    """
    Downloads a CSV file from eBird using the provided session ID.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    session = requests.Session()
    response = session.get(download_url, cookies={'EBIRD_SESSIONID': session_id}, headers=headers)

    if response.status_code == 200:
        output_path = Path(output_file)

        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if we got CSV content
        if 'text/csv' in response.headers.get('Content-Type', ''):
            output_path.write_bytes(response.content)
            print(f"Successfully downloaded: {output_file}")
            return True
        else:
            print(f"Warning: Response doesn't appear to be a CSV file. Content-Type: {response.headers.get('Content-Type')}")
            # Save anyway, but warn the user
            output_path.write_bytes(response.content)
            return False
    else:
        print(f"Failed to download file. HTTP Status Code: {response.status_code}")
        print("Response:", response.text)
        return False


def parse_arguments():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description='Download eBird lists with automatic login')
    
    # Create a mutually exclusive group for authentication methods
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument('--session-id', help='Directly use an existing eBird session ID')
    auth_group.add_argument('--login', action='store_true', help='Login with username and password')
    
    parser.add_argument('--output-dir', required=True, help='Directory to save downloaded files')
    parser.add_argument('--year', type=int, help='Year for the year list (default: current year)')
    parser.add_argument('--username', help='eBird username (if using --login)')
    parser.add_argument('--lists', nargs='+', choices=['life', 'year', 'month'], default=['life', 'year'],
                       help='Which lists to download (default: life and year)')
    
    return parser.parse_args()


def main():
    args = parse_arguments()
    output_dir = args.output_dir
    session_id = None
    
    # Set default year to current year if not specified
    import datetime
    current_year = args.year if args.year else datetime.datetime.now().year
    
    # Handle authentication
    if args.session_id:
        # Directly use provided session ID
        session_id = args.session_id
    
    elif args.login:
        # Get session ID by logging in
        session_id = get_ebird_session(USERNAME, PASSWORD)
        if not session_id:
            sys.exit(1)
        print(f"Successfully logged in. Your session ID is: {session_id}")
    
    # Download the requested lists
    success = True
    
    if 'life' in args.lists:
        success &= download_csv(session_id, 'https://ebird.org/lifelist?r=world&time=life&fmt=csv', 
                            os.path.join(output_dir, "life_list.csv"))
    
    if 'year' in args.lists:
        success &= download_csv(session_id, f'https://ebird.org/lifelist?r=world&time=year&year={current_year}&fmt=csv', 
                            os.path.join(output_dir, f"year_list_{current_year}.csv"))
    
    if 'month' in args.lists:
        current_month = datetime.datetime.now().month
        success &= download_csv(session_id, f'https://ebird.org/lifelist?r=world&time=month&month={current_month}&fmt=csv', 
                            os.path.join(output_dir, f"month_list_{current_month}_{current_year}.csv"))
    
    if success:
        print("All downloads completed successfully.")
    else:
        print("Some downloads may have failed. Check the output above for details.")


if __name__ == "__main__":
    main()