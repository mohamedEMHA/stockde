#!/usr/bin/env python3   python reddit_to_medium_bot.py           python redditarti.py 
# -*- coding: utf-8 -*-

"""
Reddit to Medium Automation Bot

Αυτό το bot παρακολουθεί οικονομικά subreddits, εντοπίζει trending topics,
δημιουργεί άρθρα με τη χρήση του OpenAI API και τα δημοσιεύει αυτόματα στο Medium.
"""

import sqlite3
import time
import json
import os
import logging
import requests
import random
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import schedule
from typing import Dict, Optional, List

try:
    import google.generativeai as genai
except ImportError:
    print("Η βιβλιοθήκη 'google-generativeai' δεν είναι εγκατεστημένη. Τρέξτε: pip install google-generativeai")
    genai = None

try:
    from fake_useragent import UserAgent
except ImportError:
    print("Η βιβλιοθήκη 'fake-useragent' δεν είναι εγκατεστημένη. Τρέξτε: pip install fake-useragent")
    UserAgent = None

try:
    import praw
except ImportError:
    print("Η βιβλιοθήκη 'praw' δεν είναι εγκατεστημένη. Τρέξτε: pip install praw")
    praw = None


# --- ΡΥΘΜΙΣΕΙΣ BOT ---

# 1. API Keys & Credentials (ΣΥΜΠΛΗΡΩΣΕ ΤΑ ΔΙΚΑ ΣΟΥ)
GEMINI_API_KEY = "AIzaSyBSQl6NhHL9DRRRKL4TwpeL9y6256kr9s8" # Το API key σου από το Gemini
TELEGRAM_BOT_TOKEN = "8422686468:AAEHJnMSo27qFHiydYTesLbpBR2qFUlP29k"
TELEGRAM_CHAT_ID = "7795749542"

# 1.5. Ρυθμίσεις Email (ΣΥΜΠΛΗΡΩΣΕ ΤΑ ΔΙΚΑ ΣΟΥ)
SMTP_SERVER = "smtp.gmail.com"  # Π.χ., "smtp.gmail.com" για Gmail
SMTP_PORT = 587                 # Π.χ., 587 για TLS
EMAIL_ADDRESS = "mopatch4@gmail.com" # Η διεύθυνση email σου
EMAIL_PASSWORD = "jkcv dpsi tynm dsgf"   # Ο κωδικός εφαρμογής (App Password) σου
RECIPIENT_EMAIL = "elitewavecons@gmail.com" # Το email που θα λαμβάνει τα άρθρα

# 2. Ρυθμίσεις Reddit & Ανάλυσης
REDDIT_CLIENT_ID = "Q1Hjek8JIBVq1IfkM97K6A"
REDDIT_CLIENT_SECRET = "cvQqjOq5D_aW7KfA4Dy96AzyJyiOZQ"
REDDIT_USER_AGENT = "script:content.finder:v2.1 (by /u/Sea-Field-7160)"
REDDIT_USERNAME = "Sea-Field-7160"
REDDIT_PASSWORD = "cegexev876@A"

SUBREDDITS = [
    'stocks', 'StockMarket', 'investing', 'SecurityAnalysis', 'wallstreetbets',
    'ValueInvesting', 'DividendInvesting', 'ETFs', 'options', 'pennystocks',
    'Daytrading', 'CanadianInvestor', 'UKInvesting',
    'investingforbeginners', 'Superstonk', 'algotrading', 'SPACs',
    'RobinHoodPennyStocks', 'dividends', 'financialindependence', 'SecurityAnalysis',
    'StockMarket', 'trading', 'ValueInvesting'
]
POST_FETCH_LIMIT = 50  # Αριθμός posts προς ανάκτηση από κάθε subreddit
MIN_ENGAGEMENT = 50    # Ελάχιστο άθροισμα upvotes/comments για να ληφθεί υπόψη ένα post

# 3. Ρυθμίσεις Ανάλυσης & Triggers
TOPIC_WINDOW_HOURS = 24  # Χρονικό παράθυρο για τον εντοπισμό trend (π.χ. 24 ώρες)
TRIGGER_POST_COUNT = 3   # Πρέπει ένα θέμα να εμφανιστεί σε τουλάχιστον 3 posts
TRIGGER_ENGAGEMENT = 100 # Κάθε ένα από αυτά τα posts πρέπει να έχει τουλάχιστον 100 engagement

# 4. Ρυθμίσεις Δημοσίευσης
ARTICLES_PER_DAY = 1 # Πόσα άρθρα να δημιουργεί την ημέρα
RUN_HOUR_START = 8  # Ώρα έναρξης (π.χ. 8 π.μ.)
RUN_HOUR_END = 22 # Ώρα λήξης (π.χ. 10 μ.μ.)
 
# 5. Γενικές Ρυθμίσεις
DB_PATH = "articlesbot.db"
LOG_FILE = "reddit_to_telegram_bot.log"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
ENABLE_FILE_LOGGING = True  # Αλλάξτε σε False για να απενεργοποιήσετε το logging σε αρχείο .log

# --- Ρύθμιση Logging ---
log_handlers = [logging.StreamHandler()]
if ENABLE_FILE_LOGGING:
    log_handlers.append(logging.FileHandler(LOG_FILE, encoding='utf-8'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

class RedditToMediumBot:
    def __init__(self):
        self.db_path = DB_PATH
        self.gemini_model = None

        if genai and GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                logging.info("🤖 Το μοντέλο Gemini AI αρχικοποιήθηκε με επιτυχία.")
            except Exception as e:
                logging.error(f"❌ Αποτυχία αρχικοποίησης του Gemini AI: {e}")
        else:
            logging.info("ℹ️ Η λειτουργία AI είναι απενεργοποιημένη (λείπει βιβλιοθήκη ή API key).")

        self._init_database()

    def send_telegram_message(self, text: str):
        """Στέλνει μήνυμα στο Telegram."""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code != 200:
                logging.error(f"Telegram API Error: {response.text}")
        except requests.RequestException as e:
            logging.error(f"Telegram request failed: {e}")

    def _init_database(self):
        """Αρχικοποιεί τη βάση δεδομένων SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Πίνακας για τα posts που συλλέγονται
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reddit_posts (
                id TEXT PRIMARY KEY,
                subreddit TEXT,
                title TEXT,
                content TEXT,
                upvotes INTEGER,
                comments INTEGER,
                engagement INTEGER,
                url TEXT,
                created_utc REAL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Αφαίρεση πίνακα 'articles' και σχετικών ελέγχων, καθώς δεν δημιουργούμε άρθρα πλέον.

        conn.commit()
        conn.close()
        logging.info("Η βάση δεδομένων αρχικοποιήθηκε με επιτυχία.")

    def fetch_reddit_posts(self):
        """Συλλέγει hot posts από τα καθορισμένα subreddits."""
        logging.info("🔎 Έναρξη συλλογής posts από το Reddit...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Επιλογή: χρήση επίσημου API μέσω PRAW αν είναι διαθέσιμο, αλλιώς anonymous requests
        reddit_client_available = (
            praw is not None and all([
                REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, REDDIT_USERNAME, REDDIT_PASSWORD
            ])
        )

        new_posts_count = 0

        if reddit_client_available:
            try:
                reddit = praw.Reddit(
                    client_id=REDDIT_CLIENT_ID,
                    client_secret=REDDIT_CLIENT_SECRET,
                    user_agent=REDDIT_USER_AGENT,
                    username=REDDIT_USERNAME,
                    password=REDDIT_PASSWORD
                )
                logging.info("Χρήση PRAW για συλλογή posts.")
                for subreddit in SUBREDDITS:
                    try:
                        for post in reddit.subreddit(subreddit).hot(limit=POST_FETCH_LIMIT):
                            engagement = getattr(post, 'score', 0) + getattr(post, 'num_comments', 0)
                            if engagement < MIN_ENGAGEMENT or getattr(post, 'stickied', False):
                                continue
                            cursor.execute("SELECT id FROM reddit_posts WHERE id=?", (post.id,))
                            if cursor.fetchone():
                                continue
                            cursor.execute('''
                                INSERT INTO reddit_posts (id, subreddit, title, content, upvotes, comments, engagement, url, created_utc)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                post.id,
                                post.subreddit.display_name,
                                post.title,
                                getattr(post, 'selftext', '') or '',
                                getattr(post, 'score', 0),
                                getattr(post, 'num_comments', 0),
                                engagement,
                                f"https://reddit.com{getattr(post, 'permalink', '')}",
                                float(getattr(post, 'created_utc', time.time()))
                            ))
                            new_posts_count += 1
                    except Exception as e:
                        logging.error(f"Σφάλμα στο PRAW κατά τη λήψη από r/{subreddit}: {e}")
                    time.sleep(random.uniform(2, 5))
            except Exception as e:
                logging.error(f"Αποτυχία αρχικοποίησης PRAW ή authentication: {e}. Εναλλαγή σε anonymous requests.")
                reddit_client_available = False

        if not reddit_client_available:
            # --- Anonymous fallback μέσω requests ---
            ua = UserAgent() if UserAgent else None
            headers = {'User-Agent': ua.random if ua else REDDIT_USER_AGENT}
            logging.info(f"Χρήση User-Agent: {headers['User-Agent']}")

            for subreddit in SUBREDDITS:
                try:
                    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={POST_FETCH_LIMIT}"
                    response = requests.get(url, headers=headers, timeout=15)
                    response.raise_for_status()
                    data = response.json()['data']['children']

                    for post_data in data:
                        post = post_data['data']
                        engagement = post.get('ups', 0) + post.get('num_comments', 0)
                        if engagement < MIN_ENGAGEMENT or post.get('stickied'):
                            continue
                        cursor.execute("SELECT id FROM reddit_posts WHERE id=?", (post.get('id'),))
                        if cursor.fetchone():
                            continue
                        cursor.execute('''
                            INSERT INTO reddit_posts (id, subreddit, title, content, upvotes, comments, engagement, url, created_utc)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            post.get('id'), post.get('subreddit'), post.get('title'), post.get('selftext', ''),
                            post.get('ups', 0), post.get('num_comments', 0), engagement, post.get('permalink'), post.get('created_utc', time.time())
                        ))
                        new_posts_count += 1
                except requests.RequestException as e:
                    logging.error(f"Σφάλμα δικτύου κατά τη λήψη από r/{subreddit}: {e}")
                except Exception as e:
                    logging.error(f"Απρόσμενο σφάλμα στο r/{subreddit}: {e}")
                
                # --- ΒΕΛΤΙΩΣΗ: Τυχαία παύση μεταξύ των subreddits ---
                time.sleep(random.uniform(2, 5))

        conn.commit()
        conn.close()
        logging.info(f"✅ Ολοκληρώθηκε η συλλογή. Προστέθηκαν {new_posts_count} νέα posts.")
        return new_posts_count

    def analyze_for_trends(self) -> Optional[str]:
        """Αναλύει τα posts για να εντοπίσει trending topics που πληρούν τα κριτήρια."""
        logging.info("📊 Ανάλυση για εντοπισμό trending topics...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Εύρεση θεμάτων από τις τελευταίες 24 ώρες
        time_threshold = datetime.now() - timedelta(hours=TOPIC_WINDOW_HOURS)
        time_threshold_utc = time_threshold.timestamp()

        cursor.execute("""
            SELECT title FROM reddit_posts
            WHERE created_utc >= ? AND engagement >= ?
        """, (time_threshold_utc, TRIGGER_ENGAGEMENT))

        posts = cursor.fetchall()
        if not posts:
            logging.info("Δεν βρέθηκαν πρόσφατα posts που να πληρούν τα κριτήρια engagement.")
            return None

        titles = [post[0] for post in posts]
        topic = None

        # Χρήση Gemini για ομαδοποίηση και εντοπισμό του κυρίαρχου θέματος
        if self.gemini_model:
            try:
                prompt = """
                Analyze the following list of Reddit post titles from finance subreddits and identify the single most dominant and recurring topic.
                The topic must be a descriptive phrase of at least 3 words.
                Filter out generic, single-word terms like "stocks", "market", "investing". Focus on specific entities, events, or concepts.

                Post Titles:
                - {titles_placeholder}

                What is the single most discussed topic? Respond with only the descriptive topic phrase.
                """.format(titles_placeholder="\n- ".join(titles))

                response = self.gemini_model.generate_content(prompt)
                topic = response.text.strip()

                # --- ΒΕΛΤΙΩΣΗ: Αυστηρός έλεγχος για την ποιότητα του topic ---
                # Απορρίπτουμε topics με λιγότερες από 3 λέξεις.
                if len(topic.split()) < 3:
                    logging.warning(f"Το AI επέστρεψε ένα πολύ σύντομο topic: '{topic}'. Θα αγνοηθεί.")
                    topic = None
                # -----------------------------------------------------------

                # Αφαιρέθηκε ο έλεγχος διπλοτύπων έναντι του πίνακα 'articles'.
            except Exception as e:
                logging.error(f"Σφάλμα κατά την ανάλυση με Gemini: {e}")
                topic = None

        if not topic: # Fallback αν το AI απέτυψε ή δεν υπάρχει θέμα
            logging.info("Η ανάλυση από AI δεν επέστρεψε κάποιο θέμα. Δεν θα χρησιμοποιηθεί fallback.")

        conn.close()

        if topic:
            logging.info(f"🔥 Trending Topic Εντοπίστηκε: {topic}")
        return topic

    # Συνάρτηση δημιουργίας headlines έχει αφαιρεθεί

    def _clean_text(self, text: str) -> str:
        """Αφαιρεί markdown χαρακτήρες και καθαρίζει το κείμενο για το email."""
        if not text:
            return ""
        # Αφαίρεση **bold** και *italic*
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        # Αφαίρεση λιστών με - ή * στην αρχή της γραμμής
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
        return text

    def send_article_via_email(self, article_data: Dict[str, str]) -> bool:
        """Στέλνει το άρθρο μέσω email."""
        logging.info(f"📧 Προετοιμασία αποστολής email στο {RECIPIENT_EMAIL}...")
    
        if not all([SMTP_SERVER, SMTP_PORT, EMAIL_ADDRESS, EMAIL_PASSWORD, RECIPIENT_EMAIL]):
            logging.error("❌ Οι ρυθμίσεις email δεν είναι πλήρεις. Παράλειψη αποστολής email.")
            return False
    
        try:
            # Δημιουργία του HTML περιεχομένου του email
            html_content = f"""
            <html>
            <head>
                <style>
                    /* ... (no changes in style) ... */
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f4f7; margin: 0; padding: 20px; }}
                    .container {{ max-width: 700px; margin: auto; background: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
                    h1 {{ font-size: 28px; color: #1a1a1a; margin-bottom: 10px; }}
                    h2 {{ font-size: 22px; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 30px; }}
                    p {{ font-size: 16px; color: #555; }}
                    .introduction {{ font-style: italic; color: #444; border-left: 3px solid #3498db; padding-left: 15px; margin-bottom: 25px; }}
                    .conclusion {{ background-color: #ecf0f1; padding: 20px; border-radius: 5px; margin-top: 30px; border-top: 3px solid #3498db; }}
                    .subtitle {{ font-size: 20px; color: #555; margin-bottom: 20px; font-weight: 400; }}
                    .tags {{ font-size: 0.9em; color: #7f8c8d; margin-top: 20px; }}
                    .tag-item {{ background-color: #e0e0e0; color: #555; padding: 3px 8px; border-radius: 12px; display: inline-block; margin-right: 5px; font-size: 13px; }}
                    .social-section {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 30px; border-top: 3px solid #1da1f2; }}
                    .image-prompt-section {{ background-color: #fffbe6; padding: 20px; border-radius: 5px; margin-top: 30px; border-left: 4px solid #f0ad4e; }}
                    .toc-section {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin-top: 25px; margin-bottom: 25px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>{self._clean_text(article_data.get('title', 'No Title'))}</h1>
                    <h2 class="subtitle">{self._clean_text(article_data.get('subtitle', ''))}</h2>
                    <div class="introduction">
                        <p>{self._clean_text(article_data.get('introduction', ''))}</p>
                    </div>
            """

            # Προσθήκη πίνακα περιεχομένων (sub-headlines)
            sections = article_data.get('sections', [])
            if sections:
                html_content += '<div class="toc-section">'
                html_content += '<h3>Table of Contents</h3><ul>'
                for section in sections:
                    html_content += f"<li>{self._clean_text(section.get('heading', ''))}</li>"
                html_content += '</ul></div>'

            html_content += """
            """
            for section in article_data.get('sections', []):
                heading = self._clean_text(section.get('heading', ''))
                content = self._clean_text(section.get('content', ''))
                html_content += f"<h2>{heading}</h2><p>{content.replace(chr(10), '<br>')}</p>"
    
            html_content += f"""
                    <div class="conclusion">
                        <h2>Conclusion</h2>
                        <p>{self._clean_text(article_data.get('conclusion', ''))}</p>
                    </div>
                    <div class="tags">
                        <b>Tags:</b> {''.join([f'<span class="tag-item">#{tag}</span>' for tag in article_data.get('tags', [])])}
                    </div>
            """

            # Προσθήκη των social media posts
            social_posts = article_data.get('social_posts', {})
            if social_posts:
                html_content += '<div class="social-section">'
                html_content += '<h2>Social Media Posts</h2>'
                if 'x' in social_posts:
                    html_content += f"<h3>X (Twitter)</h3><p>{self._clean_text(social_posts['x'])}</p>"
                if 'facebook' in social_posts:
                    html_content += f"<h3>Facebook</h3><p>{self._clean_text(social_posts['facebook'])}</p>"
                if 'instagram' in social_posts:
                    html_content += f"<h3>Instagram</h3><p>{self._clean_text(social_posts['instagram'])}</p>"
                html_content += '</div>'

            # Προσθήκη του Image Prompt
            image_prompt = article_data.get('image_prompt')
            if image_prompt:
                html_content += '<div class="image-prompt-section">'
                html_content += '<h2>🎨 Image Prompt (for DALL-E/Midjourney)</h2>'
                html_content += f"<p><i>{self._clean_text(image_prompt)}</i></p>"
                html_content += '</div>'

            html_content += """
                </div>
            </body>
            </html>
            """
    
            msg = MIMEMultipart()
            msg['From'] = EMAIL_ADDRESS
            msg['To'] = RECIPIENT_EMAIL
            msg['Subject'] = f"New Article: {article_data.get('title', 'No Title')}"
            msg.attach(MIMEText(html_content, 'html'))
    
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.send_message(msg)
                logging.info("✅ Το άρθρο στάλθηκε με επιτυχία στο email.")
            return True
        except Exception as e:
            logging.error(f"❌ Σφάλμα κατά την αποστολή του email: {e}")
            return False

    def get_top_posts(self, limit: int = 5, hours: int = TOPIC_WINDOW_HOURS) -> List[Dict]:
        """Επιστρέφει τα Top posts βάσει engagement στο χρονικό παράθυρο."""
        logging.info("📈 Εξαγωγή Top posts για αποστολή...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            time_threshold = datetime.now() - timedelta(hours=hours)
            cursor.execute(
                """
                SELECT id, subreddit, title, upvotes, comments, engagement, url, created_utc
                FROM reddit_posts
                WHERE created_utc >= ?
                ORDER BY engagement DESC
                LIMIT ?
                """,
                (time_threshold.timestamp(), limit),
            )
            rows = cursor.fetchall()
            posts = []
            for row in rows:
                pid, subreddit, title, upvotes, comments, engagement, url, created_utc = row
                link = url if (url and str(url).startswith("http")) else f"https://reddit.com{url or ''}"
                posts.append({
                    "id": pid,
                    "subreddit": subreddit,
                    "title": title,
                    "upvotes": upvotes,
                    "comments": comments,
                    "engagement": engagement,
                    "url": link,
                    "created_utc": created_utc,
                })
            return posts
        except Exception as e:
            logging.error(f"❌ Αποτυχία εξαγωγής Top posts: {e}")
            return []
        finally:
            conn.close()

    def send_top_posts_via_telegram(self, posts: List[Dict]) -> None:
        """Στέλνει τα Top posts στο Telegram ως σύνοψη."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logging.info("ℹ️ Παράλειψη: Λείπουν ρυθμίσεις Telegram.")
            return
        if not posts:
            logging.info("ℹ️ Δεν υπάρχουν posts για αποστολή στο Telegram.")
            return

        lines = []
        lines.append(f"📊 Top {len(posts)} posts τελευταίων {TOPIC_WINDOW_HOURS} ωρών:")
        for i, p in enumerate(posts, 1):
            title = p.get('title', '')
            engagement = p.get('engagement', 0)
            sub = p.get('subreddit', '-')
            url = p.get('url', '')
            up = p.get('upvotes', 0)
            cm = p.get('comments', 0)
            lines.append(f"{i}. <b>{self._clean_text(title)[:180]}</b> ({sub}) — 👍 {up} • 💬 {cm} • 🔥 {engagement}\n{url}")
        message = "\n\n".join(lines)
        self.send_telegram_message(message)
        logging.info("✅ Εστάλησαν τα Top posts μέσω Telegram.")

    def send_top_posts_via_email(self, posts: List[Dict]) -> bool:
        """Στέλνει τα Top posts μέσω email σε απλό HTML."""
        if not all([SMTP_SERVER, SMTP_PORT, EMAIL_ADDRESS, EMAIL_PASSWORD, RECIPIENT_EMAIL]):
            logging.info("ℹ️ Παράλειψη: Λείπουν ρυθμίσεις email.")
            return False
        if not posts:
            logging.info("ℹ️ Δεν υπάρχουν posts για αποστολή μέσω email.")
            return False

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html = []
        html.append(f"""
            <html><head><style>
                body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }}
                .container {{ max-width: 700px; margin: auto; padding: 20px; }}
                .post {{ border-bottom: 1px solid #eaeaea; padding: 12px 0; }}
                .title a {{ text-decoration: none; color: #1a1a1a; font-weight: 600; }}
                .meta {{ color: #555; font-size: 14px; }}
            </style></head><body><div class="container">
            <h2>📊 Top {len(posts)} Reddit Finance Posts (τελευταίες {TOPIC_WINDOW_HOURS} ώρες)</h2>
            <p class="meta">Αποστολή: {date_str}</p>
        """)
        for p in posts:
            created_utc = p.get('created_utc') or 0
            try:
                created_str = datetime.fromtimestamp(float(created_utc)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                created_str = "-"
            html.append(f"""
                <div class="post">
                    <div class="title"><a href="{p.get('url','')}" target="_blank">{self._clean_text(p.get('title',''))}</a></div>
                    <div class="meta">Subreddit: r/{p.get('subreddit','-')} • 👍 {p.get('upvotes',0)} • 💬 {p.get('comments',0)} • 🔥 {p.get('engagement',0)} • {created_str}</div>
                </div>
            """)
        html.append("</div></body></html>")
        html_content = "".join(html)
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_ADDRESS
            msg['To'] = RECIPIENT_EMAIL
            msg['Subject'] = f"Top {len(posts)} Reddit Finance Posts"
            msg.attach(MIMEText(html_content, 'html'))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.send_message(msg)
            logging.info("✅ Εστάλησαν τα Top posts μέσω email.")
            return True
        except Exception as e:
            logging.error(f"❌ Σφάλμα αποστολής email για Top posts: {e}")
            return False

    # Συνάρτηση δημιουργίας υπότιτλου έχει αφαιρεθεί

    # Συνάρτηση δημιουργίας sub-headlines έχει αφαιρεθεί

    # Συνάρτηση δημιουργίας introductions έχει αφαιρεθεί

    # Συνάρτηση generate_article έχει αφαιρεθεί

    def run_fetch_job(self):
        """Εκτελεί μόνο τη συλλογή των posts από το Reddit."""
        logging.info("--- 📂 Έναρξη κύκλου συλλογής posts ---")
        
        # 1. Συλλογή νέων posts και έλεγχος αν υπάρχουν νέα δεδομένα
        new_posts_count = self.fetch_reddit_posts()

        # 2. Αποστολή Top 5 posts μέσω Telegram/Email
        try:
            top_posts = self.get_top_posts(limit=5, hours=TOPIC_WINDOW_HOURS)
            if top_posts:
                self.send_top_posts_via_telegram(top_posts)
                self.send_top_posts_via_email(top_posts)
            else:
                logging.info("ℹ️ Δεν βρέθηκαν posts για αποστολή (παράθυρο χρόνου/κριτήρια).")
        except Exception as e:
            logging.error(f"❌ Σφάλμα κατά την αποστολή Top posts: {e}")

        logging.info("--- ✅ Ο κύκλος συλλογής posts ολοκληρώθηκε ---")

    def run_analysis_and_generation_job(self):
        """Απενεργοποιημένη λειτουργία: η δημιουργία/αποστολή άρθρου έχει αφαιρεθεί."""
        logging.info("⏸️ Παράλειψη: η λειτουργία δημιουργίας/αποστολής άρθρου είναι απενεργοποιημένη.")
        return

    # Συνάρτηση σύνθεσης πλήρους άρθρου έχει αφαιρεθεί

def run_bot_continuously():
    """Κύρια συνάρτηση εκτέλεσης του bot."""

    # Προαιρετικές ειδοποιήσεις για credentials που αφορούν άρθρα/Telegram/Email
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD or not RECIPIENT_EMAIL:
        missing.append("EMAIL credentials")
    if missing:
        logging.info(f"ℹ️ Θα εκτελεστεί μόνο συλλογή posts. Λείπουν: {', '.join(missing)}")

    # Δημιουργία του bot
    bot = RedditToMediumBot()

    # --- ΝΕΑ ΛΟΓΙΚΗ ΜΕ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ ---
    # 1. Προγραμματισμός συλλογής posts
    schedule.every(90).minutes.do(bot.run_fetch_job)
    logging.info("🕒 Προγραμματίστηκε η συλλογή posts κάθε 90 λεπτά.")

    logging.info("🚀 Το bot ξεκίνησε σε συνεχή λειτουργία μόνο για συλλογή posts.")
    print("🚀 Το bot τρέχει 24/7. Πατήστε Ctrl+C για έξοδο.")

    # Εκτέλεση της συλλογής μία φορά κατά την εκκίνηση
    bot.run_fetch_job()  # Κάνει fetch τα posts

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Έλεγχος κάθε λεπτό για εκκρεμείς εργασίες
        except KeyboardInterrupt:
            bot.send_telegram_message("🛑 Το bot <b>redditarti.py</b> τερματίστηκε από τον χρήστη (KeyboardInterrupt).")
            logging.info("🛑 Το bot τερματίζεται από τον χρήστη.")
            break
        except Exception as e:
            logging.critical(f"Κρίσιμο σφάλμα στον κύριο βρόχο: {e}")
            bot.send_telegram_message(f"🔥 Κρίσιμο σφάλμα στο <b>redditarti.py</b>: {e}")
            time.sleep(300)  # Αναμονή 5 λεπτών πριν την επανάληψη σε περίπτωση κρίσιμου σφάλματος

if __name__ == "__main__":
    run_bot_continuously()