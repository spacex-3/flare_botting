import os
import random
import time
import logging
from dotenv import load_dotenv

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DiscourseAutoRead:
    def __init__(self, url, username=None, password=None, cookie_str=None):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.cookie_str = cookie_str
        self.driver = None

    def start(self):
        """Main entry point"""
        try:
            # Setup Chrome options
            options = uc.ChromeOptions()
            
            headless = os.getenv('HEADLESS', 'true').lower() == 'true'
            if headless:
                options.add_argument('--headless=new')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--start-maximized')
            options.add_argument('--lang=zh-CN,zh,en-US,en')
            
            logger.info("Launching undetected Chrome...")
            self.driver = uc.Chrome(
                options=options,
                use_subprocess=True,
                version_main=None
            )
            self.driver.set_page_load_timeout(60)
            
            user_agent = self.driver.execute_script("return navigator.userAgent")
            logger.info(f"User-Agent: {user_agent}")
            
            # Perform login
            if self.username and self.password:
                self.login_with_credentials()
            elif self.cookie_str:
                self.login_with_cookies()
            else:
                raise Exception("No authentication method provided")
            
            # Read posts
            self.read_posts()
            
        except Exception as e:
            logger.error(f"Error: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()

    def login_with_credentials(self):
        """Login using username and password"""
        login_url = f"{self.url}/login"
        logger.info(f"Navigating to {login_url}...")
        self.driver.get(login_url)
        
        time.sleep(5)
        self.handle_cloudflare()
        
        try:
            wait = WebDriverWait(self.driver, 30)
            username_field = wait.until(
                EC.presence_of_element_located((By.ID, "login-account-name"))
            )
            logger.info("Login form detected.")
            
            username_field.clear()
            username_field.send_keys(self.username)
            logger.info(f"Filled username: {self.username[:3]}***")
            time.sleep(0.5)
            
            password_field = self.driver.find_element(By.ID, "login-account-password")
            password_field.clear()
            password_field.send_keys(self.password)
            logger.info("Filled password: ***")
            time.sleep(0.5)
            
            login_button = self.driver.find_element(By.ID, "login-button")
            login_button.click()
            logger.info("Clicked login button.")
            
            login_timeout = int(os.getenv('LOGIN_TIMEOUT', '60'))
            logger.info(f"Waiting for login (timeout: {login_timeout}s)...")
            
            time.sleep(3)
            self.handle_cloudflare()
            
            try:
                wait = WebDriverWait(self.driver, login_timeout)
                wait.until(EC.presence_of_element_located((By.ID, "current-user")))
                logger.info("Login successful! User avatar detected.")
            except TimeoutException:
                raise Exception("Login failed: timeout waiting for user avatar")
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise

    def login_with_cookies(self):
        """Login using cookies"""
        logger.info("Using cookie-based authentication...")
        
        self.driver.get(self.url)
        time.sleep(3)
        self.handle_cloudflare()
        
        for chunk in self.cookie_str.split(';'):
            if '=' in chunk:
                name, value = chunk.strip().split('=', 1)
                if name and value:
                    try:
                        self.driver.add_cookie({'name': name, 'value': value})
                    except Exception as e:
                        logger.warning(f"Failed to add cookie {name}: {e}")
        
        logger.info("Cookies added. Refreshing page...")
        self.driver.refresh()
        time.sleep(3)
        self.handle_cloudflare()
        
        try:
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.ID, "current-user")))
            logger.info("Cookie login successful!")
        except TimeoutException:
            raise Exception("Cookie login failed")

    def handle_cloudflare(self):
        """Handle Cloudflare challenge if present"""
        try:
            title = self.driver.title
            if "Just a moment" in title or "Cloudflare" in title:
                logger.info("Cloudflare challenge detected. Waiting...")
                
                for i in range(30):
                    time.sleep(2)
                    new_title = self.driver.title
                    if "Just a moment" not in new_title and "Cloudflare" not in new_title:
                        logger.info("Cloudflare challenge passed!")
                        return
                    logger.info(f"Still waiting for Cloudflare... ({i+1}/30)")
                
                logger.warning("Cloudflare challenge timeout")
        except Exception as e:
            logger.info(f"Cloudflare check: {e}")

    def read_posts(self):
        """Read unread posts"""
        logger.info("Starting to read posts...")
        
        max_topics = int(os.getenv('MAX_TOPICS', 10))
        count = 0
        
        while count < max_topics:
            target_page = f"{self.url}/unread"
            logger.info(f"Navigating to {target_page}")
            self.driver.get(target_page)
            
            time.sleep(3)
            self.handle_cloudflare()
            
            try:
                wait = WebDriverWait(self.driver, 15)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".topic-list")))
                logger.info("Topic list loaded.")
            except TimeoutException:
                logger.warning("No topic list found.")
                break
            
            badge = self.get_first_unread_badge()
            if not badge:
                logger.info("No more unread topics. All caught up!")
                break
            
            logger.info(f"Reading topic ({count+1}/{max_topics})...")
            
            try:
                badge.click()
                time.sleep(2)
                
                if self.check_topic_error():
                    logger.error("Topic load error detected")
                    continue
                
                self.simulate_reading()
                count += 1
                logger.info(f"Finished reading topic {count}/{max_topics}")
                
            except Exception as e:
                logger.error(f"Failed to read topic: {e}")
                continue
        
        logger.info(f"Completed reading {count} topics.")

    def get_first_unread_badge(self):
        """Find the first unread badge"""
        selectors = [
            "a.badge.badge-notification.unread-posts",
            ".badge-posts.badge-notification",
            "a.badge-posts[href*='?u=']",
            ".topic-list-item .badge-notification.new-posts",
        ]
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    if elem.is_displayed():
                        logger.info(f"Found unread badge: {selector}")
                        return elem
            except Exception:
                continue
        
        try:
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, ".topic-list-item a.badge-notification"
            )
            for elem in elements:
                if elem.is_displayed():
                    return elem
        except Exception:
            pass
        
        return None

    def check_topic_error(self):
        """Check if topic failed to load"""
        error_texts = ["无法加载", "连接问题", "error"]
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            for error in error_texts:
                if error in page_text.lower():
                    return True
        except Exception:
            pass
        return False

    def simulate_reading(self):
        """Simulate reading by scrolling"""
        logger.info("Simulating reading...")
        
        viewport_height = self.driver.execute_script("return window.innerHeight")
        scroll_step = min(400, viewport_height - 100)
        
        start_time = time.time()
        max_time = 300
        bottom_count = 0
        
        while (time.time() - start_time) < max_time:
            pause = random.uniform(3.5, 5.0)
            time.sleep(pause)
            
            scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_y = self.driver.execute_script("return window.scrollY")
            
            if (scroll_y + viewport_height) >= (scroll_height - 50):
                bottom_count += 1
                if bottom_count >= 3:
                    logger.info("Reached bottom of topic.")
                    break
            else:
                bottom_count = 0
            
            self.driver.execute_script(f"window.scrollBy(0, {scroll_step})")
            time.sleep(0.5)
        
        time.sleep(random.uniform(4, 6))
        logger.info("Finished reading topic.")


def main():
    configs = []
    
    if os.getenv('TARGET_URL'):
        configs.append({
            'url': os.getenv('TARGET_URL'),
            'username': os.getenv('USERNAME'),
            'password': os.getenv('PASSWORD'),
            'cookie': os.getenv('COOKIE_STRING')
        })
    
    if os.getenv('TARGET_URL_2'):
        configs.append({
            'url': os.getenv('TARGET_URL_2'),
            'username': os.getenv('USERNAME_2'),
            'password': os.getenv('PASSWORD_2'),
            'cookie': os.getenv('COOKIE_STRING_2')
        })
    
    if not configs:
        logger.error("No TARGET_URL found.")
        return
    
    for cfg in configs:
        logger.info(f"Starting auto-read for: {cfg['url']}")
        try:
            bot = DiscourseAutoRead(
                url=cfg['url'],
                username=cfg.get('username'),
                password=cfg.get('password'),
                cookie_str=cfg.get('cookie')
            )
            bot.start()
        except Exception as e:
            logger.error(f"Error processing {cfg['url']}: {e}")


if __name__ == "__main__":
    main()
