import requests
import yagmail
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Hugging Face Inference API
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")  # Replace with your Hugging Face API token

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging

websites = [
    {"url": "https://vergabemarktplatz.brandenburg.de/VMPCenter/common/project/search.do?method=showExtendedSearch&fromExternal=true#eyJjcHZDb2RlcyI6W10sImNvbnRyYWN0aW5nUnVsZXMiOlsiVk9MIiwiVk9CIiwiVlNWR1YiLCJTRUtUVk8iLCJPVEhFUiJdLCJwdWJsaWNhdGlvblR5cGVzIjpbIkV4QW50ZSIsIlRlbmRlciIsIkV4UG9zdCJdLCJkaXN0YW5jZSI6MCwicG9zdGFsQ29kZSI6IiIsIm9yZGVyIjoiMCIsInBhZ2UiOiIxIiwic2VhcmNoVGV4dCI6InZlcnBmbGVndW5nIiwic29ydEZpZWxkIjoicmFuayJ9", "keywords": ["catering","mittag"]},
]

# Email configuration
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHES_FILE = os.path.join(SCRIPT_DIR, "matches.json")
TEXT_PARTS_FILE = "extracted_text_parts.json"

def clear_matches_file():
    """Clear the matches.json file."""
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "w") as file:
            json.dump({}, file, indent=4)
        print(f"{MATCHES_FILE} has been cleared.")
    else:
        print(f"{MATCHES_FILE} does not exist. Creating a new empty file.")
        with open(MATCHES_FILE, "w") as file:
            json.dump({}, file, indent=4)

def load_previous_matches():
    """Load previously found matches from a file."""
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "r") as file:
            return json.load(file)
    return {}

def save_matches(matches):
    """Save matches to a file."""
    with open(MATCHES_FILE, "w") as file:
        json.dump(matches, file, indent=4)

def save_text_parts(text_parts):
    """Save extracted text parts to a file."""
    with open(TEXT_PARTS_FILE, "w") as file:
        json.dump(text_parts, file, indent=4)

def query_huggingface_api(extracted_data, keywords, max_length=512):
    """
    Query the Hugging Face API to check for relevance of extracted titles.
    Returns a list of relevant matches with their titles and dates.
    """
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}
    relevant_matches = []

    for i, data in enumerate(extracted_data):
        text = data["title"]
        date = data.get("date", "No Date")
        link = data.get("link", "No Link")

        print(f"Checking text {i+1}/{len(extracted_data)}: {text[:50]}...")

        # Truncate or pad the text
        truncated_text = text[:max_length]

        payload = {
            "inputs": truncated_text,
            "parameters": {"candidate_labels": keywords}
        }

        try:
            response = requests.post(HUGGINGFACE_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

            scores = result.get("scores", [])
            if any(score > 0.01 for score in scores):
                print(f"Relevant Match Found: {truncated_text}")
                relevant_matches.append({"title": truncated_text, "date": date, "link": link, "result": result})
        except Exception as e:
            print(f"Error querying Hugging Face API for text {i+1}: {e}")

    return relevant_matches


import time

def extract_titles_with_selenium(url):
    """
    Extract titles, corresponding dates, and links directly from a dynamically rendered webpage using Selenium.
    Returns an array of dictionaries containing the title, date, and link.
    """
    extracted_data = []
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        time.sleep(5)  # Allow time for the page to load fully

        # Handle cookies popup if necessary
        try:
            WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'alle akzeptieren')]"))
            ).click()
            print("Cookies popup dismissed.")
        except Exception:
            print("No cookies popup found.")

        # Check if elements are inside an iframe
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"Found {len(iframes)} iframes on the page.")
        for iframe in iframes:
            driver.switch_to.frame(iframe)
            if driver.find_elements(By.CLASS_NAME, "title"):
                print("Found 'tender' elements inside an iframe.")
                break
            driver.switch_to.default_content()

        # Wait for elements to load
        title_elements = WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "word-break"))
        )
        print("title:" + str(title_elements))
        
        date_elements = WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "noTextDecorationLink"))
        )
        print("date:" + str(date_elements))
        link_elements =  WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "noTextDecorationLink"))
        )
        print("links:" + str(link_elements))

        print(f"Found {len(title_elements)} titles, {len(date_elements)} dates, and {len(link_elements)} links.")

        for title_element, date_element, link_element in zip(title_elements, date_elements, link_elements):
            try:
                title = title_element.text.strip()
                link = link_element.get_attribute("href")[29:-21]
                date = ""
                extracted_data.append({"title": title, "date": date, "link": link})
                print(f"Extracted: {title}, {date}, {link}")
            except Exception as e:
                print(f"Error extracting data: {e}")

    except Exception as e:
        print(f"Error loading the page: {e}")
    finally:
        driver.quit()

    return extracted_data


def send_email(new_matches):
    """Send an email notification with titles, dates, and links."""
    subject = "Neue Ausschreibungen verfügbar!!"
    body = "Die folgenden neuen Übereinstimmungen wurden gefunden:\n\n"

    for match in new_matches:
        title = match.get("title", "No Title")
        date = match.get("date", "No Date")
        link = match.get("link", "No Link")
        body += f"Title: {title}\nLink: {link}\n\n"

    try:
        yag = yagmail.SMTP(EMAIL_ADDRESS, EMAIL_PASSWORD)
        yag.send("Henrik.Hemmer@flc-group.de", subject, body)
        print("Email sent!")
    except Exception as e:
        print(f"Failed to send email: {e}")


def main():
    """Main function to check websites and send emails."""
    previous_matches = load_previous_matches()
    print("Previous Matches:", previous_matches)
    new_matches = []

    for site in websites:
        url = site["url"]
        keywords = site["keywords"]

        # Extract all titles and dates
        extracted_data = extract_titles_with_selenium(url)
        save_text_parts(extracted_data)

        # Check each title for relevance
        matches = query_huggingface_api(extracted_data, keywords)

        # Determine new matches
        if url not in previous_matches:
            previous_matches[url] = []

        for match in matches:
            if match not in previous_matches[url]:
                new_matches.append(match)
                previous_matches[url].append(match)

    # Send an email if there are new matches
    if new_matches:
        send_email(new_matches)

    # Save the updated matches to the file
    save_matches(previous_matches)

if __name__ == "__main__":
    main()
