import os
import time
import argparse
import yaml
import sys
import csv
import random
import requests
import datetime
import re
import json
from bs4 import BeautifulSoup
from seleniumbase import SB

# --- CONFIGURATION ---
USER_DATA_DIR = os.path.join(os.getcwd(), "idealista_profile")
TRANSACTION_MAP = {"buy": "vendita-case", "rent-flat": "affitto-case", "rent-room": "affitto-stanze"}

def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

def download_listing_images(image_urls, listing_id, base_img_folder):
    listing_folder = os.path.join(base_img_folder, str(listing_id))
    os.makedirs(listing_folder, exist_ok=True)
    
    saved_paths =[]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    for i, url in enumerate(image_urls[:15]):
        try:
            target_url = url.replace("WEB_DETAIL-M-L", "WEB_DETAIL")
            response = requests.get(target_url, headers=headers, timeout=10)
            if response.status_code == 200:
                file_name = f"{i+1}.jpg"
                path = os.path.join(listing_folder, file_name)
                with open(path, "wb") as f:
                    f.write(response.content)
                saved_paths.append(f"images/{listing_id}/{file_name}")
            time.sleep(random.uniform(0.3, 0.8))
        except Exception as e:
            print(f"      ⚠️ Image {i} failed for {listing_id}: {e}")
            
    return f"images/{listing_id}/"

# --- PARSING LOGIC (NOW USING BEAUTIFULSOUP) ---

def extract_card_data(article_soup):
    try:
        item_id = article_soup.get("data-element-id")
        if not item_id: return None
        
        link_el = article_soup.select_one(".item-link")
        title = link_el.text.strip() if link_el else ""
        url = link_el.get("href") if link_el else ""
        
        # Ensure URL is complete
        if url and not url.startswith("http"):
            url = "https://www.idealista.it" + url
            
        img_el = article_soup.select_one("picture img")
        thumb = img_el.get("src") if img_el else ""
        
        price_el = article_soup.select_one(".item-price")
        price = price_el.text.strip() if price_el else ""
        
        rooms = ""
        size = ""
        details = article_soup.select(".item-detail")
        if details:
            if len(details) > 0: rooms = details[0].text.strip()
            if len(details) > 1: size = details[1].text.strip()

        return {
            "id": item_id,
            "title": title,
            "url": url,
            "price": price,
            "rooms": rooms,
            "size": size,
            "main_image_url": thumb
        }
    except Exception as e:
        print(f"      ⚠️ Extract card error: {e}")
        return None

def extract_deep_details(html_source):
    details = {
        "full_description": "",
        "all_features": "",
        "address": "",
        "advertiser_type": "",
        "advertiser_name": "",
        "last_updated": "",
        "latitude": "",
        "longitude": "",
        "phone": "",
        "image_urls":[]
    }
    try:
        soup = BeautifulSoup(html_source, "html.parser")
        
        # 1. Description
        desc_el = soup.select_one(".adCommentsLanguage p")
        if desc_el:
            details['full_description'] = desc_el.text.strip()
            
        # 2. Features
        feature_elements = soup.select(".details-property_features ul li")
        feats =[el.text.strip() for el in feature_elements if el.text.strip()]
        details['all_features'] = " | ".join(feats)

        # 3. Full Address
        address_elements = soup.select(".header-map-list")
        if address_elements:
            details['address'] = " - ".join([el.text.strip() for el in address_elements if el.text.strip()])

        # 4. Advertiser Type (Private vs Agency)
        adv_type_el = soup.select_one(".professional-name .name")
        if adv_type_el:
            details['advertiser_type'] = adv_type_el.text.strip()

        # 5. Advertiser Name
        adv_name_el = soup.select_one(".advertiser-name")
        if adv_name_el:
            details['advertiser_name'] = adv_name_el.text.strip()

        # 6. Last Updated Date
        updated_el = soup.select_one(".time-since-last-modification")
        if updated_el:
            details['last_updated'] = updated_el.text.strip()

        # 7. Coordinates (Regex trick to pull lat/lng from the static map URL)
        coord_match = re.search(r'center=([\d\.\-]+)(?:%2C|,)([\d\.\-]+)', html_source)
        if coord_match:
            details['latitude'] = coord_match.group(1)
            details['longitude'] = coord_match.group(2)

        # 8. Phone Number (Extracted after click)
        phone_els = soup.select(".hidden-contact-phones_text, a[href^='tel:']")
        for el in phone_els:
            txt = el.text.strip()
            # If it contains digits and isn't the Idealista support number
            if any(char.isdigit() for char in txt) and "02 36" not in txt and "0236" not in txt:
                details['phone'] = txt
                break

        # 9. IMAGE EXTRACTION (Regex Bypass)
        pattern = re.compile(r"var adMultimediasInfo = (\{.*?\});", re.DOTALL)
        match = pattern.search(html_source)
        if match:
            js_block = match.group(1)
            
            urls = re.findall(r'imageDataService["\']?\s*:\s*["\']([^"\']+)["\']', js_block)
            if not urls:
                urls = re.findall(r'["\']?(https://img\d\.idealista\.it/[^"\']+(?:jpg|webp))["\']?', js_block)
            
            clean_urls =[]
            for u in urls:
                if u not in clean_urls:
                    clean_urls.append(u)
                    
            details['image_urls'] = clean_urls
            
    except Exception as e:
        print(f"      ⚠️ Deep parse error: {e}")
    return details

# --- MAIN ENGINE ---

def run_system(urls, scenario_name, deep_scrape=False):
    root_folder = os.path.join("scraped_data", f"{scenario_name}_{get_timestamp()}")
    img_root = os.path.join(root_folder, "images")
    os.makedirs(img_root, exist_ok=True)
    csv_path = os.path.join(root_folder, "listings.csv")

    with SB(uc=True, user_data_dir=USER_DATA_DIR, browser="chrome") as sb:
        cdp_active = False

        for start_url in urls:
            current_url = start_url
            while current_url:
                print(f"\n🌐 Search Page: {current_url}")
                
                # Activate CDP Mode exactly once. Use native CDP sb.open() afterwards.
                if not cdp_active:
                    sb.activate_cdp_mode(current_url)
                    cdp_active = True
                else:
                    sb.open(current_url)
                    
                time.sleep(random.uniform(7, 12))
                
                html_source = sb.get_page_source()
                
                if "geo.captcha-delivery.com" in html_source.lower():
                    print("🚨 CAPTCHA DETECTED! Solve it now.")
                    while "geo.captcha-delivery.com" in sb.get_page_source().lower(): 
                        time.sleep(2)
                        
                    # Re-grab source after captcha is solved
                    html_source = sb.get_page_source()

                # Parse the page with BeautifulSoup
                soup = BeautifulSoup(html_source, "html.parser")
                cards = soup.select("article.item")
                print(f"   --> Found {len(cards)} listing cards on page.")
                
                page_data_list =[]

                # Grab the Next Page URL safely
                next_btn = soup.select_one(".pagination li.next a")
                if next_btn:
                    next_url = next_btn.get("href")
                    if next_url and not next_url.startswith("http"):
                        next_url = "https://www.idealista.it" + next_url
                else:
                    next_url = None

                # Extract basic data using Soup elements
                for card in cards:
                    item = extract_card_data(card)
                    if item:
                        page_data_list.append(item)

                # Deep Scrape sequentially
                if deep_scrape and page_data_list:
                    for item in page_data_list:
                        print(f"   🔎 Deep Scrape: {item['id']}")
                        sb.open(item['url'])
                        time.sleep(random.uniform(4, 7))
                        
                        # Stealthily click the "See Phone" button using JS to avoid mouse-tracking bots
                        try:
                            if sb.is_element_present(".see-phones-btn"):
                                sb.execute_script("document.querySelector('.see-phones-btn').click();")
                                time.sleep(random.uniform(1.5, 2.5)) # Wait for AJAX phone number to load
                        except:
                            pass
                        
                        deep_html = sb.get_page_source()
                        deep_info = extract_deep_details(deep_html)
                        
                        # Apply deep details to the item
                        item['description'] = deep_info['full_description']
                        item['all_features'] = deep_info['all_features']
                        item['address'] = deep_info['address']
                        item['advertiser_type'] = deep_info['advertiser_type']
                        item['advertiser_name'] = deep_info['advertiser_name']
                        item['last_updated'] = deep_info['last_updated']
                        item['latitude'] = deep_info['latitude']
                        item['longitude'] = deep_info['longitude']
                        item['phone'] = deep_info['phone']
                        
                        if deep_info['image_urls']:
                            item['images_folder'] = download_listing_images(
                                deep_info['image_urls'], item['id'], img_root
                            )
                        item.pop('main_image_url', None)
                elif not deep_scrape and page_data_list:
                    for item in page_data_list:
                        if item.get('main_image_url'):
                            item['images_folder'] = download_listing_images(
                                [item['main_image_url']], item['id'], img_root
                            )
                        item.pop('main_image_url', None)

                # Save Batch
                if page_data_list:
                    file_exists = os.path.isfile(csv_path)
                    with open(csv_path, "a", newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=page_data_list[0].keys())
                        if not file_exists: writer.writeheader()
                        writer.writerows(page_data_list)
                    print(f"✅ Saved {len(page_data_list)} listings.")

                current_url = next_url 

            time.sleep(random.uniform(30, 60))

# --- CLI & SETUP ---

def build_search_urls(conf):
    tx_path = TRANSACTION_MAP.get(conf.get('transaction_type', 'buy'), "vendita-case")
    filters = conf.get("url_filters", "").strip("/")
    filter_segment = f"{filters}/" if filters else ""

    # 1. Explicit full search URL override (pagination is still handled automatically)
    if conf.get('search_url'):
        return [conf['search_url']]

    # 2. Geo-shape based search (custom drawn area / polygon)
    if conf.get('shape'):
        shape = conf['shape'].strip()
        return [f"https://www.idealista.it/aree/{tx_path}/{filter_segment}?shape={shape}"]

    # 3. Province based search
    if conf.get('provinces') == 'all':
        with open("provinces.txt", "r") as f:
            prov_list = [l.strip().lower() for l in f if l.strip()]
    else:
        prov_list = conf.get('provinces', [])

    return [f"https://www.idealista.it/{tx_path}/{p}-provincia/{filter_segment}" for p in prov_list]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", required=True)
    args = parser.parse_args()

    with open(args.config, "r") as f:
        conf = yaml.safe_load(f)

    urls = build_search_urls(conf)
    scenario_filename = os.path.splitext(os.path.basename(args.config))[0]

    run_system(urls, scenario_filename, deep_scrape=conf.get('deep_scrape', False))

if __name__ == "__main__":
    main()
