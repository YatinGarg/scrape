import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
from urllib.parse import urljoin
import io
import threading
import datetime

class EbayScraper:
    # Exchange rates dictionary using double quotes for all strings
    EXCHANGE_RATES = {
        "NT$": 32.906,  # New Taiwan Dollar
        "HK$": 7.8,     # Hong Kong Dollar
        "£": 0.77,      # British Pound
        "€": 0.91,      # Euro
        "C$": 1.35,     # Canadian Dollar
        "A$": 1.5,      # Australian Dollar
        "¥": 149.0,     # Japanese Yen
        "₩": 1350.0,    # Korean Won
        "₹": 83.0,      # Indian Rupee
    }
    
    @staticmethod
    def convert_to_usd(price_str):
        """Convert any currency to USD using the static exchange rates"""
        for currency_symbol, rate in EbayScraper.EXCHANGE_RATES.items():
            if currency_symbol in price_str:
                try:
                    # Extract the numeric value
                    numeric_match = re.search(r'[\d,.]+', price_str)
                    if numeric_match:
                        amount_str = numeric_match.group(0)
                        # Clean the string and convert to float
                        amount = float(amount_str.replace(',', ''))
                        
                        if currency_symbol == "£" or currency_symbol == "€":
                            # For GBP and EUR, divide the rate (these are worth more than USD)
                            usd_amount = round(amount / rate, 1)
                        else:
                            # For other currencies, divide by rate
                            usd_amount = round(amount / rate, 1)
                            
                        # Return only the USD amount without the conversion note
                        return f"US ${usd_amount}"
                except (ValueError, TypeError) as e:
                    st.error(f"Conversion error: {e}")
                    
        # If no conversion was performed or it failed, return the original string
        return price_str
    
    def __init__(self, base_url):
        # Apply multiple URL parameters to force USD currency
        if '?' in base_url:
            # Add multiple currency parameters that eBay might use
            base_url += '&_ccy=1&_fmt=US&_dmd=1'
        else:
            base_url += '?_ccy=1&_fmt=US&_dmd=1'
            
        self.base_url = base_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.ebay.com/",
            "Accept-Currency": "USD",
            "X-Currency": "USD",
            "Currency": "USD"
        }
        self.session = requests.Session()
        self.products = []
        self.status_updates = []
        self.is_running = False
        self.progress = 0
        
        # Add cookies to appear more like a regular browser
        self.session.cookies.set("nonsession", "1", domain=".ebay.com")
        self.session.cookies.set("ebay", "%5Esbf%3D%23%5E", domain=".ebay.com")
        
        # Set multiple cookies to force USD currency
        self.session.cookies.set("dp1", "bcurrency/1", domain=".ebay.com")
        self.session.cookies.set("cid", "USD", domain=".ebay.com")
        self.session.cookies.set("apcid", "1", domain=".ebay.com")
        
        # Add location cookies for US-based browsing
        self.session.cookies.set("localization", "US", domain=".ebay.com")
        self.session.cookies.set("gl_gl", "US", domain=".ebay.com")
    
    def add_status_update(self, message):
        """Add a timestamped status update"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.status_updates.append(f"[{timestamp}] {message}")
        
    def get_page(self, url):
        """Fetch the page content with proper error handling and retries"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, headers=self.headers)
                response.raise_for_status()  # Raise exception for HTTP errors
                return response.text
            except requests.exceptions.RequestException as e:
                error_msg = f"Error fetching {url}: {e}"
                self.add_status_update(error_msg)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt + random.uniform(0, 1)  # Exponential backoff
                    retry_msg = f"Retrying in {wait_time:.2f} seconds..."
                    self.add_status_update(retry_msg)
                    time.sleep(wait_time)
                else:
                    self.add_status_update("Max retries reached. Moving on.")
                    return None
    
    def parse_product_listings(self, html_content):
        """Parse the HTML to extract product information"""
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, "html.parser")
        products_data = []
        
        # Locate product containers
        # Note: eBay's HTML structure might change over time, so these selectors may need adjustment
        product_containers = soup.select("li.s-item")
        
        for container in product_containers:
            try:
                # Extract product details
                title_elem = container.select_one(".s-item__title")
                price_elem = container.select_one(".s-item__price")
                link_elem = container.select_one("a.s-item__link")
                image_elem = container.select_one(".s-item__image-img")
                
                # Skip "Shop on eBay" items that sometimes appear
                if title_elem and "Shop on eBay" in title_elem.text:
                    continue
                
                # Get data with None checks
                title = title_elem.text.strip() if title_elem else "No Title"
                
                # Improved price extraction with currency handling
                price = "No Price"
                if price_elem:
                    price = price_elem.text.strip()
                    # Clean up price format (remove extra text sometimes included)
                    price = price.split(" to ")[0] if " to " in price else price
                    price = price.split("/")[0] if "/" in price else price
                    
                    # Enhanced NT$ detection - check for variations like "NT $" with space or lowercase "nt$"
                    if not ("NT$" in price) and ("NT $" in price or "nt$" in price or "NT" in price):
                        price = price.replace("NT $", "NT$").replace("nt$", "NT$")
                        if "NT" in price and "$" in price and not "NT$" in price:
                            price = price.replace("NT", "NT$").replace("NT$$", "NT$")
                    
                    # Check for different currency formats and convert them to USD
                    if "US $" in price or price.startswith("$"):
                        # Already in US dollars, just standardize format
                        numeric_match = re.search(r'[\d,.]+', price)
                        if numeric_match:
                            price_value = numeric_match.group(0)
                            # Convert to float and round to 1 decimal place
                            try:
                                price_float = float(price_value.replace(',', ''))
                                price_value = round(price_float, 1)
                            except ValueError:
                                pass
                            price = f"US ${price_value}"
                    else:
                        # Check for any non-USD currency and convert it
                        has_currency = any(currency in price for currency in EbayScraper.EXCHANGE_RATES.keys())
                        if has_currency:
                            # Use the conversion method
                            old_price = price
                            price = EbayScraper.convert_to_usd(price)
                            self.add_status_update(f"Converted currency: {old_price} → {price}")
                        elif "$" in price and not "US $" in price:
                            # Generic $ sign without US prefix - add it
                            price = "US " + price
                
                product_url = link_elem["href"] if link_elem and "href" in link_elem.attrs else None
                
                # More robust image URL extraction
                image_url = None
                # Look for image URLs in this order of priority
                if image_elem:
                    if "data-src" in image_elem.attrs:
                        image_url = image_elem["data-src"]
                    elif "src" in image_elem.attrs and not image_elem["src"].endswith("gif"):
                        image_url = image_elem["src"]
                
                # If still no image, try alternative selectors
                if not image_url:
                    # Try picture element with srcset
                    picture_elem = container.select_one("picture.s-item__image-img")
                    if picture_elem:
                        img_in_picture = picture_elem.select_one("img")
                        if img_in_picture and "src" in img_in_picture.attrs:
                            image_url = img_in_picture["src"]
                
                # Final fallback: search for any img tag within the item
                if not image_url:
                    all_imgs = container.select("img")
                    for img in all_imgs:
                        if "src" in img.attrs and not img["src"].endswith("gif") and "https://" in img["src"]:
                            image_url = img["src"]
                            break
                
                # Only add products with valid URLs
                if product_url:
                    products_data.append({
                        "title": title,
                        "price": price,
                        "product_url": product_url,
                        "image_url": image_url
                    })
            except Exception as e:
                self.add_status_update(f"Error extracting product data: {e}")
                continue
                
        return products_data
    
    def get_next_page_url(self, html_content, current_page_number):
        """Extract the URL for the next page if available"""
        if not html_content:
            return None
            
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Look for pagination controls
        pagination = soup.select(".pagination__items")
        if pagination:
            next_button = soup.select_one(".pagination__next")
            if next_button and "href" in next_button.attrs:
                return urljoin(self.base_url, next_button["href"])
        
        # Alternative approach: sometimes eBay uses query parameters for pagination
        # Try to construct the next page URL manually
        if "?" in self.base_url:
            base_part, query_part = self.base_url.split("?", 1)
            if "_pgn=" in query_part:
                # Replace page number in URL
                new_query = []
                for param in query_part.split("&"):
                    if "_pgn=" in param:
                        param = f"_pgn={current_page_number + 1}"
                    new_query.append(param)
                return f"{base_part}?{'&'.join(new_query)}"
            else:
                # Add page number to URL
                return f"{self.base_url}&_pgn={current_page_number + 1}"
        
        return None

    def scrape(self, max_pages=None, progress_bar=None, status_area=None):
        """Main method to scrape eBay products with Streamlit progress tracking"""
        self.is_running = True
        self.progress = 0
        self.products = []
        self.status_updates = []
        
        current_url = self.base_url
        page_number = 1
        
        try:
            self.add_status_update(f"Starting scrape for: {self.base_url}")
            self.add_status_update(f"Maximum pages to scrape: {max_pages if max_pages else 'All'}")
            
            # Update the status area
            if status_area:
                status_area.empty()
                status_area.markdown("\n".join(self.status_updates))
            
            while current_url and self.is_running:
                self.add_status_update(f"Scraping page {page_number}...")
                
                # Update the status area
                if status_area:
                    status_area.empty()
                    status_area.markdown("\n".join(self.status_updates))
                
                html_content = self.get_page(current_url)
                
                if html_content:
                    page_products = self.parse_product_listings(html_content)
                    if page_products:
                        self.products.extend(page_products)
                        self.add_status_update(f"Found {len(page_products)} products on page {page_number}. Total: {len(self.products)}")
                    else:
                        self.add_status_update(f"No products found on page {page_number}. Stopping.")
                        break
                    
                    # Update progress bar
                    if max_pages and progress_bar:
                        progress_value = min(1.0, page_number / max_pages)
                        progress_bar.progress(progress_value)
                    
                    # Update the status area
                    if status_area:
                        status_area.empty()
                        status_area.markdown("\n".join(self.status_updates))
                    
                    # Add a delay to be respectful to the website
                    delay = random.uniform(1.5, 3.5)
                    self.add_status_update(f"Waiting {delay:.2f} seconds before next request...")
                    time.sleep(delay)
                    
                    # Check if we should continue to the next page
                    if max_pages and page_number >= max_pages:
                        self.add_status_update(f"Reached maximum number of pages ({max_pages}). Stopping.")
                        break
                    
                    # Get URL for the next page
                    current_url = self.get_next_page_url(html_content, page_number)
                    page_number += 1
                else:
                    self.add_status_update("Failed to fetch page content. Stopping.")
                    break
            
            self.add_status_update(f"Scraping complete. Total products collected: {len(self.products)}")
            
            if not self.is_running:
                self.add_status_update("Scrape was stopped manually.")
            
            # Set progress to 100% when complete
            if progress_bar:
                progress_bar.progress(1.0)
            
            # Final update to the status area
            if status_area:
                status_area.empty()
                status_area.markdown("\n".join(self.status_updates))
            
            return self.products
            
        except Exception as e:
            self.add_status_update(f"Error during scraping: {e}")
            if status_area:
                status_area.empty()
                status_area.markdown("\n".join(self.status_updates))
        finally:
            self.is_running = False

# Streamlit app
def main():
    st.set_page_config(
        page_title="eBay Product Scraper",
        page_icon="🛒",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("eBay Product Scraper")
    st.markdown("Easily scrape product listings from eBay search results")
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("Scraper Settings")
        
        ebay_url = st.text_input(
            "eBay Search URL:",
            placeholder="https://www.ebay.com/sch/i.html?_nkw=smartphones",
            help="Enter the full URL from an eBay search results page"
        )
        
        max_pages = st.number_input(
            "Number of Pages to Scrape:",
            min_value=1,
            max_value=100,
            value=5,
            help="Choose how many pages to scrape (max 100)"
        )
        
        start_button = st.button("Start Scraping", type="primary", use_container_width=True)
        stop_button = st.button("Stop Scraping", type="secondary", use_container_width=True)
    
    # Main content area
    tab1, tab2 = st.tabs(["Scraper", "Instructions"])
    
    with tab1:
        # Progress tracking
        progress_container = st.container()
        with progress_container:
            progress_text = st.empty()
            progress_bar = st.empty()
            status_area = st.empty()
        
        # Results display
        results_container = st.container()
    
    with tab2:
        st.header("Instructions")
        st.markdown("""
        ### How to use this scraper:
        1. Go to eBay and perform your search
        2. Copy the URL from your browser's address bar
        3. Paste the URL in the field in the sidebar
        4. Choose how many pages to scrape
        5. Click "Start Scraping"
        6. Wait for the process to complete
        7. Download the CSV when ready
        
        ### Notes:
        - The scraper is respectful to eBay's servers and adds delays between requests
        - All prices are converted to USD for consistency
        - Be mindful of eBay's terms of service regarding automated tools
        """)
    
    # Session state
    if 'scraper' not in st.session_state:
        st.session_state.scraper = None
    if 'data_frame' not in st.session_state:
        st.session_state.data_frame = None
    if 'is_scraping' not in st.session_state:
        st.session_state.is_scraping = False
    
    # Handle start button
    if start_button and ebay_url:
        if not ebay_url.startswith("https://www.ebay.com"):
            st.sidebar.error("Please enter a valid eBay URL")
        else:
            with progress_container:
                progress_text.text("Scraping in progress...")
                progress_placeholder = progress_bar.progress(0)
                status_placeholder = status_area.empty()
                
                # Create and start the scraper
                st.session_state.scraper = EbayScraper(ebay_url)
                st.session_state.is_scraping = True
                
                # Run scraping in the main thread (Streamlit doesn't handle threading well)
                products = st.session_state.scraper.scrape(
                    max_pages=max_pages,
                    progress_bar=progress_placeholder,
                    status_area=status_placeholder
                )
                
                # When complete, display the results
                if products:
                    st.session_state.data_frame = pd.DataFrame(products)
                    st.session_state.is_scraping = False
                    progress_text.text(f"Scraping complete! Found {len(products)} products.")
                else:
                    progress_text.text("Scraping completed but no products were found.")
                    st.session_state.is_scraping = False
    
    # Handle stop button
    if stop_button and st.session_state.is_scraping:
        if st.session_state.scraper:
            st.session_state.scraper.is_running = False
            st.session_state.is_scraping = False
            progress_text.text("Scraping stopped manually.")
    
    # Display results if available
    if st.session_state.data_frame is not None:
        with results_container:
            st.header(f"Results: {len(st.session_state.data_frame)} Products")
            
            # Add CSV download button
            csv = st.session_state.data_frame.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="ebay_products.csv",
                mime="text/csv",
                type="primary"
            )
            
            # Show the data table
            st.dataframe(st.session_state.data_frame, use_container_width=True)
            
            # Sample visualization
            if not st.session_state.data_frame.empty:
                st.subheader("Price Distribution")
                # Extract numeric values from price strings
                price_data = []
                for price_str in st.session_state.data_frame['price']:
                    if isinstance(price_str, str) and "US $" in price_str:
                        try:
                            price_str = price_str.replace("US $", "").strip()
                            price_data.append(float(price_str))
                        except ValueError:
                            pass
                
                if price_data:
                    price_df = pd.DataFrame({'price': price_data})
                    st.bar_chart(price_df.groupby(pd.cut(price_df['price'], bins=10)).count())

if __name__ == "__main__":
    main()