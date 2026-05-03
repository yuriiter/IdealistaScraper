import os
import time
from seleniumbase import SB

# Define a BRAND NEW folder for this profile so we don't use the burnt one
USER_DATA_DIR = os.path.join(os.getcwd(), "idealista_profile")

def run_scraper():
    print(f"Launching Stealth Browser with profile: {USER_DATA_DIR}...")
    
    # Removed incognito=True
    # Added user_data_dir=USER_DATA_DIR
    with SB(uc=True, 
            user_data_dir=USER_DATA_DIR, 
            browser="chrome", 
            binary_location="/usr/bin/google-chrome-stable") as sb:
        
        print("Targeting Idealista...")
        sb.driver.get("https://www.idealista.com/en/")
        
        # Wait for the page to load and see if DataDome intercepts
        time.sleep(5)
        
        # Check if DataDome blocked us
        if "datadome" in sb.get_page_source().lower() or "vouch" in sb.get_current_url():
            print("\n🚨 BLOCK DETECTED 🚨")
            print("Please solve the CAPTCHA manually in the browser window right now.")
            
            # Loop and wait until you solve the captcha and the URL changes back to normal
            while "datadome" in sb.get_page_source().lower() or "vouch" in sb.get_current_url():
                time.sleep(2)
                
            print("\n✅ Captcha solved! DataDome accepted us.")
            print("The clearance cookie is now saved to your 'idealista_profile' folder.")
            time.sleep(3) # Give the actual Idealista page time to load
        else:
            print("\n✅ SUCCESS: We got in without a captcha.")
            print("Our saved profile/cookie worked!")
            
        # Get the title to verify
        print(f"Page Title: {sb.get_title()}")
        sb.save_screenshot("idealista_success.png")
        
        print("Closing in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    run_scraper()
