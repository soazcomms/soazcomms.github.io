from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Setup headless Chrome
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Path to matching ChromeDriver version
driver = webdriver.Chrome(options=chrome_options)

try:
    url = "https://www.winer.org/Site/Weather.php"
    driver.get(url)
    time.sleep(3)  # allow JS to load content

    page_text = driver.page_source

    # Look for "Sky Brightness" and extract the value that follows it
    keyword = "Sky Brightness"
    if keyword in page_text:
        before, after = page_text.split(keyword, 1)
        value = after.split("</td>")[1].split(">")[-1].strip()
        print(f"✅ Sky Brightness: {value}")
    else:
        print("❌ Sky Brightness not found.")

except Exception as e:
    print("💥 Error:", e)

finally:
    driver.quit()
