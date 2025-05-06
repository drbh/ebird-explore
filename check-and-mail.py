import os
import csv
import json
from ebird.api import get_nearby_observations
from dotenv import load_dotenv
from datetime import datetime
import requests

# Load environment variables
load_dotenv()

EBIRD_API_KEY = os.getenv("EBIRD_API_KEY", None)
SENDINBLUE_API_KEY = os.getenv("SENDINBLUE_API_KEY", None)
RECIPIENTS_EMAIL = os.getenv("RECIPIENTS_EMAIL", None)
SENDER_NAME = os.getenv("SENDER_NAME", None)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", None)
LLM_API_KEY = os.getenv("LLM_API_KEY", None)

if EBIRD_API_KEY is None or SENDINBLUE_API_KEY is None:
    # throw an error if the API key is not set
    raise ValueError("EBIRD_API_KEY environment variable not set.")

# RECIPIENTS_EMAIL must be a list
if RECIPIENTS_EMAIL is None:
    # throw an error if the recipient email is not set
    raise ValueError("RECIPIENTS_EMAIL environment variable not set.")

# make sure it can be split by commas
if "," in RECIPIENTS_EMAIL:
    RECIPIENTS_EMAIL = RECIPIENTS_EMAIL.split(",")
else:
    RECIPIENTS_EMAIL = [RECIPIENTS_EMAIL]


print(RECIPIENTS_EMAIL)


# Location settings (Brooklyn, NY)
LATITUDE = 40.665535
LONGITUDE = -73.969749
SEARCH_DISTANCE_KM = 1
DAYS_BACK = 1

# File paths
LIFE_LIST_PATH = "./my_bird_lists/life_list.csv"

# Email settings
EMAIL_SUBJECT = "Birds to Add to Your Life List"
MAX_BIRDS_TO_SHOW = 10


def read_csv_file(file_path):
    """Read a CSV file and return data as a list of dictionaries"""
    data = []
    try:
        with open(file_path, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                data.append(row)
        return data
    except Exception as e:
        raise Exception(f"Error reading CSV file: {e}")


def main():
    # Load environment variables as fallback
    load_dotenv()
    ebird_key = os.environ.get("EBIRD_API_KEY", EBIRD_API_KEY)
    sendinblue_key = os.environ.get("SENDINBLUE_API_KEY", SENDINBLUE_API_KEY)

    if ebird_key == "your_ebird_api_key" or sendinblue_key == "your_sendinblue_api_key":
        print(
            "Error: Please update the API keys in the script or set environment variables."
        )
        return

    # Read life list from CSV file
    try:
        life_list = read_csv_file(LIFE_LIST_PATH)
        print(f"Successfully loaded life list with {len(life_list)} species.")
    except FileNotFoundError:
        print(f"Error: Life list file not found at {LIFE_LIST_PATH}")
        return
    except Exception as e:
        print(f"Error reading life list: {e}")
        return

    # Extract the scientific names from life list for easier comparison
    life_list_species = set(item.get("Scientific Name", "") for item in life_list)
    # Get local observations
    try:
        print(
            f"Getting birds within {SEARCH_DISTANCE_KM}km of your location for the past {DAYS_BACK} days..."
        )
        records = get_nearby_observations(
            ebird_key, LATITUDE, LONGITUDE, dist=SEARCH_DISTANCE_KM, back=DAYS_BACK
        )
        print(f"Found {len(records)} recent observations nearby.")
    except Exception as e:
        print(f"Error fetching eBird observations: {e}")
        return

    import sys

    # Find birds that aren't on your life list
    new_birds = []
    for record in records:
        sci_name = record.get("sciName")
        if sci_name and sci_name not in life_list_species:
            new_birds.append(
                {
                    "common_name": record.get("comName", "Unknown"),
                    "scientific_name": sci_name,
                    "location": record.get("locName", "Unknown"),
                    "date": record.get("obsDt", "Unknown"),
                    "count": record.get("howMany", "X"),
                    "loc_id": record.get("locId", "Unknown"),
                }
            )

    # Sort by rarity (fewer observations means potentially more valuable)
    species_counts = {}
    for bird in new_birds:
        species = bird["scientific_name"]
        species_counts[species] = species_counts.get(species, 0) + 1

    # Sort the birds by count (ascending) and then by name
    sorted_birds = sorted(
        new_birds,
        key=lambda x: (species_counts[x["scientific_name"]], x["common_name"]),
    )

    # print(sorted_birds)
    if LLM_API_KEY is not None:
        text_rep = ""
        for bird in sorted_birds:
            text_rep += (
                f"{bird['common_name']} ({bird['scientific_name']}) x {bird['count']}\n"
            )
        print(text_rep)

        prompt = (
            "These are nearby birds that are my life list, which should I seek out first and why? Also tell me any cool facts about them.\n"
            + text_rep
            + "\nPlease provide a summary of the most interesting birds and their locations."
        )

        # Generate prompt for LLM
        conversation = [
            {
                "role": "system",
                "content": "You are a helpful assistant that helps birders find new birds to add to their life list. You must be concise and informative and respond in html format.",
            },
            {
                "role": "user",
                "content": f"{prompt} {text_rep}",
            },
        ]
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LLM_API_KEY}",
            },
            data=json.dumps(
                {
                    "model": "o4-mini",
                    "messages": conversation,
                    "response_format": {"type": "text"},
                    "reasoning_effort": "medium",
                    "store": False,
                }
            ),
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return

        # Parse the response
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        print(content)
        print()

    # Create email content
    email_content = create_email_content(
        sorted_birds[:MAX_BIRDS_TO_SHOW], llm_content=content
    )

    # Send email
    for recipient in RECIPIENTS_EMAIL:
        print(f"Sending email to {recipient}...")
        send_email(sendinblue_key, recipient, EMAIL_SUBJECT, email_content)

    print("Email sent with your birding opportunities!")


def create_email_content(birds, llm_content=None):
    """Create HTML email content from the list of birds"""

    today_date = datetime.now().strftime("%B %d, %Y")

    bird_html = ""
    for i, bird in enumerate(birds, 1):
        observation_date = bird["date"]
        try:
            # Try to format the date more nicely if possible
            date_obj = datetime.strptime(observation_date, "%Y-%m-%d %H:%M")
            observation_date = date_obj.strftime("%b %d, %Y at %I:%M %p")
        except:
            pass

        bird_html += f"""
        <tr>
            <td style="padding: 16px; border-bottom: 1px solid #eee;">
                <h3 style="margin: 0 0 8px 0; color: #2c3e50;">{bird['common_name']}</h3>
                <p style="margin: 0 0 8px 0; font-style: italic; color: #7f8c8d;">{bird['scientific_name']}</p>
                <p style="margin: 0 0 8px 0;"><strong>Location:</strong> {bird['location']}</p>
                <p style="margin: 0 0 8px 0;"><strong>Last seen:</strong> {observation_date}</p>
                <p style="margin: 0 0 12px 0;"><strong>Count:</strong> {bird['count']}</p>
                <a href="https://ebird.org/hotspot/{bird['loc_id']}" 
                   style="display: inline-block; padding: 8px 16px; 
                          background-color: #27ae60; color: white; 
                          text-decoration: none; border-radius: 4px;
                          font-weight: 600;">
                    View on eBird
                </a>
            </td>
        </tr>
        """

    # No birds message
    if not bird_html:
        bird_html = """
        <tr>
            <td style="padding: 16px; text-align: center; color: #7f8c8d;">
                <p>No new birds found in your area that aren't already on your life list.</p>
                <p>Try expanding your search radius or checking back in a few days!</p>
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{EMAIL_SUBJECT}</title>
    </head>
    <body style="font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 0; background-color: #f9f9f9;">
        <div style="background-color: #2980b9; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Birds to Add to Your Life List</h1>
            <p style="margin: 8px 0 0 0; font-size: 14px;">Generated on {today_date}</p>
        </div>
        
        <div style="background-color: white; padding: 20px; border-radius: 0 0 4px 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <p style="margin-top: 0;">Here are the top birds in your area that aren't on your life list yet:</p>
            
            <p style="margin: 0 0 20px 0; font-size: 14px; color: #7f8c8d;">
                {llm_content}
            </p>

            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                {bird_html}
            </table>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #7f8c8d; font-size: 12px;">
                <p>This email was automatically generated based on your life list and recent eBird observations within {SEARCH_DISTANCE_KM}km of your location.</p>
                <p>Location: Brooklyn, NY (Latitude: {LATITUDE}, Longitude: {LONGITUDE})</p>
                <p>Time period: Past {DAYS_BACK} days</p>
                <p style="margin-top: 16px;">Happy birding!</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_email(api_key, recipientS_email, subject, html_content):
    """Send email using SendInBlue API"""

    url = "https://api.sendinblue.com/v3/smtp/email"

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": recipientS_email}],
        "subject": subject,
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()

        if response.status_code == 201:
            print("Email sent successfully!")
            print(f"Message ID: {response_data.get('messageId')}")
        else:
            print(f"Failed to send email. Status code: {response.status_code}")
            print(f"Error: {response_data}")

    except Exception as e:
        print(f"Error sending email: {e}")


if __name__ == "__main__":
    main()
