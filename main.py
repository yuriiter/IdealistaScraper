import os
import time
import argparse
import yaml
import sys
import csv
import random
from seleniumbase import SB

# --- CONFIGURATION ---
USER_DATA_DIR = os.path.join(os.getcwd(), "idealista_profile")

TRANSACTION_MAP = {
    "buy": "vendita-case",
    "rent": "affitto-case"
}

# --- PARSING LOGIC ---

def extract_card_data(article):
    """Basic data visible from the search results page."""
    try:
        item_id = article.get_attribute("data-element-id")
        link_element = article.find_element("css selector", ".item-link")
        price = article.find_element("css selector", ".item-price").text.strip()
        
        return {
            "id": item_id,
            "title": link_element.text.strip(),
            "url": link_element.get_attribute("href"),
            "price": price,
            "rooms": article.find_elements("css selector", ".item-detail")[0].text if article.find_elements("css selector", ".item-detail") else "",
            "size": article.find_elements("css selector", ".item-detail")[1].text if len(article.find_elements("css selector", ".item-detail")) > 1 else "",
        }
    except:
        return None

def extract_detail_data(sb):
    """Deep data extracted from the individual property page."""
    details = {}
    try:
        # 1. Get the full description
        details['full_description'] = sb.get_text(".adCommentsLanguage p")
        
        # 2. Get features (The list items from your HTML)
        # We look for all <li> inside the features boxes
        feature_elements = sb.find_elements("css selector", ".details-property_features ul li")
        features_text = [el.text.strip() for p in feature_elements]
        details['all_features'] = " | ".join(features_text)

        # 3. Specifics (Logic based on common strings in the list)
        for f in features_text:
            if "built" in f.lower() or "costruito" in f.lower():
                details['year_built'] = f
            if "floor" in f.lower() or "piano" in f.lower():
                details['floor'] = f
            if "heating" in f.lower() or "riscaldamento" in f.lower():
                details['heating'] = f
        
        # 4. Energy Rating
        try:
            energy = sb.get_attribute(".details-property_features span[class*='icon-energy']", "class")
            details['energy_rating'] = energy.split('-')[-2].upper() if energy else "N/A"
        except:
            details['energy_rating'] = "Unknown"

    except Exception as e:
        print(f"   Warning: Could not parse all details: {e}")
    
    return details

# --- MAIN SCRAPER ENGINE ---

def run_system(urls, deep_scrape=False):
    with SB(uc=True, user_data_dir=USER_DATA_DIR, browser="chrome") as sb:
        for start_url in urls:
            current_url = start_url
            
            while current_url:
                print(f"\n🌐 Navigating to Page: {current_url}")
                sb.activate_cdp_mode(current_url)
                
                # Randomized Defensive Sleep
                time.sleep(random.uniform(5, 10))
                
                if "datadome" in sb.get_page_source().lower():
                    print("🚨 CAPTCHA! Solve it to continue...")
                    while "datadome" in sb.get_page_source().lower(): time.sleep(2)

                # Get all cards on page
                cards = sb.find_elements("css selector", "article.item")
                page_listings = []

                for card in cards:
                    basic_info = extract_card_data(card)
                    if not basic_info: continue
                    
                    if deep_scrape:
                        print(f"   🔎 Deep Scraping: {basic_info['id']}")
                        # Open detail in NEW tab to keep the search page alive (safer)
                        sb.execute_script(f"window.open('{basic_info['url']}','_blank');")
                        sb.switch_to_window(1)
                        time.sleep(random.uniform(4, 8)) # Detail page sleep
                        
                        deep_info = extract_detail_data(sb)
                        basic_info.update(deep_info)
                        
                        sb.driver.close()
                        sb.switch_to_window(0)
                        # Randomized delay between items
                        time.sleep(random.uniform(2, 5))
                    
                    page_listings.append(basic_info)

                # Save page results
                if page_listings:
                    file_exists = os.path.isfile("listings.csv")
                    with open("listings.csv", "a", newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=page_listings[0].keys())
                        if not file_exists: writer.writeheader()
                        writer.writerows(page_listings)
                    print(f"✅ Saved {len(page_listings)} items.")

                # Pagination
                try:
                    next_btn = sb.find_element("css selector", ".pagination li.next a", timeout=3)
                    current_url = next_btn.get_attribute("href")
                    print("➡️ Moving to next page...")
                except:
                    print("🏁 End of province.")
                    current_url = None
            
            # Massive sleep between provinces
            print("💤 Province complete. Cooling down...")
            time.sleep(random.uniform(20, 40))

# --- CLI & UTILS ---

def load_provinces():
    with open("provinces.txt", "r") as f:
        return [l.strip().lower() for l in f if l.strip()]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", required=True)
    args = parser.parse_args()

    with open(args.config, "r") as f:
        conf = yaml.safe_load(f)

    tx_path = TRANSACTION_MAP.get(conf.get('transaction_type', 'buy'), "vendita-case")
    filters = conf.get("url_filters", "").strip("/")
    
    prov_list = load_provinces() if conf.get('provinces') == 'all' else conf.get('provinces', [])
    
    generated_urls = [
        f"https://www.idealista.it/en/{tx_path}/{p}-provincia/{filters}/" 
        for p in prov_list
    ]

    print(f"🚀 Starting Scenario: {conf['name']}")
    print(f"🛠 Deep Scrape Mode: {conf.get('deep_scrape', False)}")
    
    run_system(generated_urls, deep_scrape=conf.get('deep_scrape', False))

if __name__ == "__main__":
    main()
