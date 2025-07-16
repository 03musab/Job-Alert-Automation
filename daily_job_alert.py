import requests
from bs4 import BeautifulSoup
import datetime, schedule, time, os, pickle, base64, json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import sqlite3
import hashlib
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import concurrent.futures
import random
import datetime
import os

# Configure logging to DEBUG level for detailed output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to your Edge WebDriver executable
edge_driver_path = r"C:\WebDrivers\msedgedriver.exe"

# Google API Scopes for Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

@dataclass
class Job:
    """Enhanced Job data structure to store scraped job details."""
    title: str
    company: str
    location: str
    salary: str
    link: str
    description: str
    keywords: List[str]
    skills: List[str]
    experience: str
    job_type: str
    posted_date: str
    source: str
    relevance_score: float = 0.0
    
    def to_dict(self):
        """Converts the Job object to a dictionary for easier storage/reporting."""
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'salary': self.salary,
            'link': self.link,
            'description': self.description[:500] + '...' if len(self.description) > 500 else self.description,
            'keywords': ', '.join(self.keywords),
            'skills': ', '.join(self.skills),
            'experience': self.experience,
            'job_type': self.job_type,
            'posted_date': self.posted_date,
            'source': self.source,
            'relevance_score': self.relevance_score
        }

class JobDatabase:
    """SQLite database for job tracking and deduplication."""
    
    def __init__(self, db_path="jobs.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initializes the SQLite database table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT UNIQUE,
                title TEXT,
                company TEXT,
                location TEXT,
                salary TEXT,
                link TEXT,
                description TEXT,
                keywords TEXT,
                skills TEXT,
                experience TEXT,
                job_type TEXT,
                posted_date TEXT,
                source TEXT,
                relevance_score REAL,
                found_date TEXT,
                applied BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'new'
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_job(self, job: Job):
        """
        Adds a job to the database with deduplication based on a hash of title, company, and location.
        Returns True if a new job was added, False otherwise (e.g., if it was a duplicate).
        """
        job_hash = hashlib.md5(f"{job.title}{job.company}{job.location}".encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO jobs 
                (job_hash, title, company, location, salary, link, description, 
                 keywords, skills, experience, job_type, posted_date, source, 
                 relevance_score, found_date) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job_hash, job.title, job.company, job.location, job.salary,
                job.link, job.description, ', '.join(job.keywords), 
                ', '.join(job.skills), job.experience, job.job_type,
                job.posted_date, job.source, job.relevance_score,
                datetime.datetime.now().isoformat()
            ))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Added new job to DB: {job.title} at {job.company}")
                return True
            else:
                logger.debug(f"Job already exists in DB (skipped): {job.title} at {job.company}")
                return False
        except Exception as e:
            logger.error(f"Error adding job to database: {e}")
            return False
        finally:
            conn.close()
    
    def get_new_jobs(self, limit=50):
        """Retrieves new jobs found today from the database, ordered by relevance score."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.date.today().isoformat()
        cursor.execute('''
            SELECT * FROM jobs 
            WHERE date(found_date) = date(?) 
            ORDER BY relevance_score DESC 
            LIMIT ?
        ''', (today, limit))
        jobs = cursor.fetchall()
        conn.close()
        return jobs

class JobScorer:
    """AI-powered job relevance scoring based on predefined criteria."""
    
    def __init__(self):
        # Define your ideal job criteria with different value weights
        self.preferred_keywords = {
            'high_value': [
                'marketing manager', 'digital marketing', 'growth marketing', 'product marketing', 'brand manager',
                'marketing executive', 'media sales', 'content marketing manager', 'social media manager',
                'influencer marketing', 'brand communication', 'media planning', 'campaign manager',
                'digital campaign manager', 'marketing specialist', 'brand marketing', 'media marketing'
            ],
            'medium_value': [
                'marketing', 'brand', 'digital', 'growth', 'product', 'campaign', 'media', 'content',
                'social media', 'influencer', 'communication', 'sales', 'promotion', 'advertising',
                'publicity', 'engagement', 'strategy', 'planning', 'creative', 'video marketing'
            ],
            'skills': [
                'seo', 'google ads', 'analytics', 'crm', 'social media', 'content marketing',
                'meta ads manager', 'facebook ads', 'instagram marketing', 'youtube studio',
                'influencer marketing', 'brand positioning', 'campaign execution', 'lead generation',
                'client management', 'video production', 'content creation', 'adobe premiere pro',
                'canva', 'whatsapp business', 'google workspace', 'presentation skills',
                'negotiation', 'pitch development', 'media planning', 'content strategy',
                'keyword optimization', 'digital promotion', 'brand deals', 'monetization'
            ],
            'experience': [
                '3-5 years', '4-6 years', '5+ years', '4+ years', 'senior', 'lead', 'executive',
                'specialist', 'coordinator', 'associate', 'manager', 'experienced', 'mid-level'
            ],
            'industries': [
                'tech', 'startup', 'saas', 'fintech', 'ecommerce', 'hospitality', 'hotels',
                'travel', 'tourism', 'media', 'advertising', 'entertainment', 'content',
                'digital agency', 'marketing agency', 'healthcare', 'beauty', 'lifestyle',
                'food & beverage', 'retail', 'fashion', 'wellness', 'events'
            ],
            'job_types': [
                'full-time', 'part-time', 'contract', 'freelance', 'remote', 'hybrid',
                'work from home', 'flexible', 'consulting', 'project-based'
            ],
            'locations': [
                'mumbai', 'bangalore', 'delhi', 'pune', 'hyderabad', 'chennai', 'gurgaon',
                'noida', 'remote', 'work from home', 'india', 'maharashtra'
            ],
            'role_levels': [
                'junior', 'senior', 'lead', 'manager', 'executive', 'specialist', 'coordinator',
                'associate', 'head', 'director', 'team lead', 'account manager'
            ],
            'specific_roles': [
                'youtube channel manager', 'content creator', 'makeup artist', 'clinic manager',
                'freelance writer', 'video editor', 'social media executive', 'brand executive',
                'marketing coordinator', 'digital marketing executive', 'content writer',
                'influencer manager', 'campaign coordinator', 'media executive'
            ],
            'companies': [
                'agency', 'startup', 'corporate', 'mnc', 'boutique', 'consultancy', 'in-house',
                'brand', 'product company', 'service company', 'digital agency', 'creative agency',
                'media house', 'production house', 'hotel chain', 'restaurant chain'
            ],
            'tools_platforms': [
                'meta business', 'facebook creator studio', 'instagram creator studio',
                'youtube analytics', 'google analytics', 'hootsuite', 'buffer', 'mailchimp',
                'hubspot', 'salesforce', 'adobe creative suite', 'final cut pro', 'davinci resolve',
                'slack', 'trello', 'asana', 'notion', 'wordpress', 'shopify', 'wix'
            ]
        }
        
        self.negative_keywords = ['intern', 'junior', 'trainee']
    
    def calculate_relevance(self, job: Job) -> float:
        """
        Calculates a relevance score (0-100) for a given job based on predefined keywords and criteria.
        """
        score = 0
        text = f"{job.title} {job.description} {job.company}".lower()

        # Title matching (highest weight)
        for keyword in self.preferred_keywords.get('high_value', []):
            if keyword in job.title.lower():
                score += 25

        # Keywords matching
        for keyword in self.preferred_keywords.get('medium_value', []):
            if keyword in text:
                score += 5

        # Skills matching
        for skill in self.preferred_keywords.get('skills', []):
            if skill in text:
                score += 3

        # Experience level
        for exp in self.preferred_keywords.get('experience', []):
            if exp in text:
                score += 8

        # Company type
        for company_type in self.preferred_keywords.get('companies', []):
            if company_type in text:
                score += 5

        # Industries matching
        for industry in self.preferred_keywords.get('industries', []):
            if industry in text:
                score += 4

        # Job types matching
        for job_type in self.preferred_keywords.get('job_types', []):
            if job_type in text:
                score += 3

        # Locations matching
        for location in self.preferred_keywords.get('locations', []):
            if location in text or location in job.location.lower():
                score += 3

        # Role levels matching
        for role_level in self.preferred_keywords.get('role_levels', []):
            if role_level in text:
                score += 3

        # Specific roles matching
        for specific_role in self.preferred_keywords.get('specific_roles', []):
            if specific_role in text:
                score += 4

        # Tools and platforms matching
        for tool in self.preferred_keywords.get('tools_platforms', []):
            if tool in text:
                score += 2

        # Salary bonus (if mentioned)
        if job.salary and any(x in job.salary.lower() for x in ['lpa', 'lakhs', 'ctc']):
            score += 10

        # Location bonus (if remote or major city)
        if any(x in job.location.lower() for x in ['remote', 'mumbai', 'bangalore', 'delhi', 'pune']):
            score += 5

        # Negative keywords penalty
        for negative in self.negative_keywords:
            if negative in text:
                score -= 15

        return min(100, max(0, score))

class EnhancedJobScraper:
    """Advanced job scraper with multiple sources and strategies."""
    
    def __init__(self):
        self.db = JobDatabase()
        self.scorer = JobScorer()
        self.session = requests.Session()
        # Expanded user-agent rotation list for better anti-blocking
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:112.0) Gecko/20100101 Firefox/112.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.128 Safari/537.36'
        ]
        self.proxies = [
            # Example proxies, replace with real proxies or proxy provider API
            'http://51.158.68.68:8811',
            'http://51.158.123.35:8811',
            'http://51.158.111.229:8811',
            'http://51.158.119.88:8811',
            'http://51.158.120.84:8811'
        ]
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/'
        })
        self.debug_dir = "debug_snapshots"
        os.makedirs(self.debug_dir, exist_ok=True)
        self.driver = self._setup_selenium()
        self.all_jobs: List[Job] = [] # Initialize list to store all scraped jobs
        self.search_terms = ['marketing manager', 'digital marketing', 'brand manager'] # Define search terms
        self.seen_urls = set() # For internal deduplication in some scrapers

    def _setup_selenium(self):
        """
        Sets up Selenium WebDriver with Edge.
        Note: Selenium is currently configured for Edge only.
        """
        logger.warning("⚠️ Warning: Using Edge browser may cause performance issues or unexpected behavior.")
        options = EdgeOptions()
        options.use_chromium = True
        options.add_argument('--headless') # Run in headless mode (no browser UI)
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # Ensure edge_driver_path is defined globally or passed correctly
        service = EdgeService(executable_path=edge_driver_path)
        
        try:
            driver = webdriver.Edge(service=service, options=options)
            logger.info("✅ Edge driver initialized successfully.")
            return driver
        except WebDriverException as e:
            logger.error(f"Edge driver initialization failed: {e}. Falling back to requests-only scraping.")
            return None

    def scrape_linkedin_jobs(self) -> List[Job]:
        """Scrape LinkedIn jobs using requests and BeautifulSoup."""
        jobs = []
        # LinkedIn scraper iterates through self.search_terms internally
        for term in self.search_terms:
            try:
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                params = {
                    'keywords': term,
                    'location': 'India',
                    'start': 0,
                    'count': 25
                }
                self.session.headers.update({'User-Agent': random.choice(self.user_agents)})
                time.sleep(random.uniform(2, 5)) # Introduce a random delay
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    job_cards = soup.find_all('div', class_='job-search-card')
                    logger.info(f"LinkedIn: Found {len(job_cards)} job cards for term '{term}'.")
                    for card in job_cards:
                        try:
                            title_elem = card.find('h3', class_='base-search-card__title')
                            company_elem = card.find('h4', class_='base-search-card__subtitle')
                            location_elem = card.find('span', class_='job-search-card__location')
                            link_elem = card.find('a', class_='base-card__full-link')
                            
                            if title_elem and company_elem and link_elem:
                                raw_data = {
                                    'title': title_elem.text.strip(),
                                    'company': company_elem.text.strip(),
                                    'location': location_elem.text.strip() if location_elem else 'India',
                                    'link': link_elem.get('href'),
                                    'description': card.text, # Full card text as description
                                    'posted_date': '', # LinkedIn guest does not easily expose posted date
                                    'source': 'LinkedIn'
                                }
                                # --- Debugging: Print extracted title and link ---
                                logger.debug(f"LinkedIn Extracted Title: '{raw_data['title']}'")
                                logger.debug(f"LinkedIn Extracted Link: '{raw_data['link']}'")
                                # --- End Debugging ---
                                job = self.extract_job_details(raw_data)
                                jobs.append(job)
                        except Exception as e:
                            logger.warning(f"Error extracting LinkedIn job card: {e}")
                            continue
                    logger.info(f"✅ Scraped {len(jobs)} jobs from LinkedIn for '{term}'.")
                else:
                    logger.warning(f"LinkedIn response status {response.status_code} for term '{term}'.")
            except Exception as e:
                logger.error(f"Error scraping LinkedIn for {term}: {e}")
        return jobs

    def extract_job_details(self, raw_data: Dict) -> Job:
        """
        Extracts, cleans, and enriches job details from raw scraped data.
        Also calculates the relevance score.
        """
        salary = raw_data.get('salary', '') # Keep original salary if provided
        if not salary and 'description' in raw_data: # Extract from description if not provided
            salary = self.extract_salary(raw_data['description'])

        experience = raw_data.get('experience', '')
        if not experience and 'description' in raw_data:
            experience = self.extract_experience(raw_data['description'])

        keywords = self.extract_keywords(raw_data.get('description', ''))
        skills = self.extract_skills(raw_data.get('description', ''))
        
        job = Job(
            title=raw_data.get('title', ''),
            company=raw_data.get('company', ''),
            location=raw_data.get('location', ''),
            salary=salary,
            link=raw_data.get('link', ''),
            description=raw_data.get('description', ''),
            keywords=keywords,
            skills=skills,
            experience=experience,
            job_type=raw_data.get('job_type', 'Full-time'), # Default job type
            posted_date=raw_data.get('posted_date', ''),
            source=raw_data.get('source', '')
        )
        job.relevance_score = self.scorer.calculate_relevance(job)
        return job

    def extract_salary(self, text: str) -> str:
        """Extracts salary information from text using regex patterns."""
        patterns = [
            r'₹?\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|ctc)',
            r'₹?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|ctc)',
            r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    def extract_experience(self, text: str) -> str:
        """Extracts experience requirements from text using regex patterns."""
        patterns = [
            r'(\d+)\s*-\s*(\d+)\s*years?',
            r'(\d+)\+?\s*years?',
            r'(fresher|entry\.level|junior|senior|lead|manager)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    def extract_keywords(self, text: str) -> List[str]:
        """Extracts relevant marketing keywords from job description."""
        marketing_keywords = [
            'digital marketing', 'content marketing', 'social media marketing',
            'email marketing', 'performance marketing', 'brand marketing',
            'product marketing', 'growth marketing', 'marketing automation',
            'campaign management', 'lead generation', 'conversion optimization'
        ]
        found_keywords = []
        text_lower = text.lower()
        for keyword in marketing_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)
        return found_keywords[:5] # Return top 5 keywords

    def extract_skills(self, text: str) -> List[str]:
        """Extracts technical skills from job description."""
        skills_list = [
            'google ads', 'facebook ads', 'google analytics', 'seo', 'sem',
            'hubspot', 'salesforce', 'mailchimp', 'hootsuite', 'canva',
            'photoshop', 'figma', 'excel', 'powerpoint', 'sql', 'python',
            'html', 'css', 'wordpress', 'shopify', 'magento'
        ]
        found_skills = []
        text_lower = text.lower() # Corrected: used text_lower instead of undefined skills_lower
        for skill in skills_list:
            if skill in text_lower:
                found_skills.append(skill)
        return found_skills[:5] # Return top 5 skills

    def scrape_internshala_jobs(self, term: str) -> List[Job]:
        """
        Scrape Internshala.com using BeautifulSoup.
        Updated selectors based on the provided HTML structure.
        """
        jobs = []
        try:
            url = f"https://internshala.com/jobs/keywords-{term.replace(' ', '-')}/"
            self.session.headers.update({'User-Agent': random.choice(self.user_agents)})
            for attempt in range(2): # Retry mechanism
                try:
                    response = self.session.get(url, timeout=10)
                    response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                    break
                except Exception as e:
                    logger.warning(f"Internshala attempt {attempt+1} failed for '{term}': {e}")
                    time.sleep(2 ** attempt) # Exponential backoff
            else: # If all attempts fail
                logger.error(f"Failed to fetch Internshala page for '{term}' after multiple attempts.")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            time.sleep(random.uniform(2, 4)) # Introduce a random delay
            
            # Target the main job card container based on the provided HTML
            cards = soup.find_all('div', class_='individual_internship') 
            logger.debug(f"Internshala: found {len(cards)} cards for {term}.")
            
            if not cards:
                logger.warning(f"No job cards found on Internshala for term '{term}'.")
            
            for card in cards:
                try:
                    # Extract Title and Link
                    title_link_elem = card.find('h3', class_='job-internship-name')
                    title_a_tag = title_link_elem.find('a', class_='job-title-href') if title_link_elem else None
                    title = title_a_tag.text.strip() if title_a_tag else ''
                    link = f"https://internshala.com{title_a_tag.get('href')}" if title_a_tag and title_a_tag.get('href') else ''

                    # Extract Company Name
                    company_elem = card.find('p', class_='company-name')
                    company = company_elem.text.strip() if company_elem else ''

                    # Extract Location
                    location_p_tag = card.find('p', class_='row-1-item locations')
                    location_span_tag = location_p_tag.find('span') if location_p_tag else None
                    location = location_span_tag.get_text(strip=True) if location_span_tag else ''

                    # Extract Salary
                    salary_elem = card.find('div', class_='row-1-item')
                    salary_span_desktop = salary_elem.find('span', class_='desktop') if salary_elem else None
                    salary = salary_span_desktop.text.strip() if salary_span_desktop else ''

                    # Extract Experience
                    experience_elem = card.find('div', class_='row-1-item')
                    # Look for a span that contains text like "X year(s)" or "X year"
                    experience_span = experience_elem.find('span', string=re.compile(r'\d+\s*year')) if experience_elem else None
                    experience = experience_span.text.strip() if experience_span else ''

                    # Extract Posted Date
                    posted_date_div = card.find('div', class_='detail-row-2')
                    posted_date_span = posted_date_div.find('span', class_=re.compile(r'status-(inactive|info|success)')) if posted_date_div else None
                    posted_date = posted_date_span.text.strip() if posted_date_span else ''


                    raw_data = {
                        'title': title,
                        'company': company,
                        'location': location,
                        'salary': salary,
                        'link': link,
                        'description': card.text, # Use full card text for description
                        'posted_date': posted_date,
                        'source': 'Internshala'
                    }
                    # --- Debugging: Print extracted title and link ---
                    logger.debug(f"Internshala Extracted Title: '{raw_data['title']}'")
                    logger.debug(f"Internshala Extracted Link: '{raw_data['link']}'")
                    # --- End Debugging ---
                    job = self.extract_job_details(raw_data)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Error extracting Internshala job card: {e}")
                    # Optionally, log the problematic card's HTML for deeper inspection
                    logger.debug(f"Problematic Internshala card HTML: {card.prettify()}")
                    continue
            logger.info(f"✅ Scraped {len(jobs)} jobs from Internshala for '{term}'.")
        except Exception as e:
            logger.error(f"Error scraping Internshala for {term}: {e}")
        return jobs
    
    def debug_scraper_selectors(self, url: str, save_snapshot: bool = True) -> str:
        """
        Debug method to fetch page HTML, log status, and optionally save a snapshot.
        Useful for inspecting page structure when selectors fail.
        """
        self.session.headers.update({'User-Agent': random.choice(self.user_agents)})
        try:
            response = self.session.get(url, timeout=15)
            status = response.status_code
            length = len(response.content)
            snippet = response.text[:500]
            logger.info(f"Debug Fetch: {url} -> status {status}, content length {length}.")
            logger.debug(f"HTML Snippet (first 500 chars):\n{snippet}")
            html = response.text
            if save_snapshot:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.debug_dir, f"snapshot_{timestamp}.html")
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"Saved HTML snapshot to {filename}.")
            return html
        except Exception as e:
            logger.error(f"Error in debug_scraper_selectors for {url}: {e}")
            return ""

    def validate_scrapers(self) -> Dict[str, int]:
        """
        Validates each scraper individually by running it for a sample term
        and returning the count of jobs found.
        """
        results = {}
        term = "marketing manager"
        # Map source names to their respective scraper functions
        all_scrapers = {
            'LinkedIn': self.scrape_linkedin_jobs,
            'Internshala': self.scrape_internshala_jobs,
        }
        
        for source_name, scraper_func in all_scrapers.items():
            logger.info(f"Starting validation for {source_name} scraper...")
            try:
                # For LinkedIn, the scraper function already handles multiple terms internally
                # For others, we pass the single term.
                if source_name == 'LinkedIn':
                    # LinkedIn scraper iterates through self.search_terms internally
                    jobs = scraper_func() 
                else: # Internshala
                    jobs = scraper_func(term)
                results[source_name] = len(jobs)
                logger.info(f"Scraper validation: {source_name} returned {results[source_name]} jobs.")
            except Exception as e:
                logger.error(f"Validation for {source_name} failed: {e}")
                results[source_name] = 0
        return results

    def scrape_with_timeout(self, func, *args, timeout=30): # Increased timeout for robustness
        """Runs a scraper function with a specified timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(f"Timeout reached for {func.__name__} with args {args}.")
                return []
            except Exception as e:
                logger.error(f"Error in scrape_with_timeout for {func.__name__} with args {args}: {e}")
                return []

    def scrape_all_sources(self) -> List[Job]:
        """
        Orchestrates scraping from all configured job sources in parallel,
        deduplicates, filters, and returns high-relevance jobs.
        """
        self.all_jobs = [] # Reset for each run
        
        # Define all scrapers to run
        scrapers_to_run = {
            'LinkedIn': self.scrape_linkedin_jobs,
            'Internshala': self.scrape_internshala_jobs,
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor: # Limit concurrent workers to 2
            future_to_scraper = {}
            for source_name, scraper_func in scrapers_to_run.items():
                if source_name == 'LinkedIn':
                    # LinkedIn scraper iterates through self.search_terms internally
                    future = executor.submit(self.scrape_with_timeout, scraper_func)
                    future_to_scraper[future] = f"{source_name}"
                else: # Internshala
                    for term in self.search_terms:
                        future = executor.submit(self.scrape_with_timeout, scraper_func, term)
                        future_to_scraper[future] = f"{source_name}-{term}"

            for future in concurrent.futures.as_completed(future_to_scraper):
                scraper_info = future_to_scraper[future]
                try:
                    jobs_from_source = future.result()
                    if jobs_from_source:
                        for job in jobs_from_source:
                            self.all_jobs.append(job) # Collect all jobs before deduplication
                        logger.info(f"Collected {len(jobs_from_source)} jobs from {scraper_info}.")
                    else:
                        logger.info(f"No jobs returned from {scraper_info}.")
                except Exception as e:
                    logger.error(f"{scraper_info} generated an exception: {e}")

        logger.info(f"Total jobs scraped across all sources before deduplication: {len(self.all_jobs)}.")

        # Deduplication and filtering logic
        unique_jobs = {}
        for job in self.all_jobs:
            key = f"{job.title.lower()}_{job.company.lower()}_{job.location.lower()}" # Case-insensitive key
            # Add to DB, which handles deduplication and returns True if new
            if self.db.add_job(job):
                # If it's a new job added to DB, consider it for unique_jobs
                unique_jobs[key] = job
            elif key in unique_jobs and job.relevance_score > unique_jobs[key].relevance_score:
                # If it's a duplicate but has a higher relevance score, update it
                unique_jobs[key] = job

        filtered_jobs = list(unique_jobs.values())

        # Filter out jobs with missing or empty title or link
        filtered_jobs = [job for job in filtered_jobs if job.title and job.link]
        logger.info(f"Jobs count after initial deduplication and filtering empty title/link: {len(filtered_jobs)}.")

        # Filter high-relevance jobs
        high_relevance_jobs = [job for job in filtered_jobs if job.relevance_score >= 10]
        high_relevance_jobs.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.info(f"Jobs count after filtering by relevance_score >= 10: {len(high_relevance_jobs)}.")

        # Log the number of jobs from each source (after all filtering)
        source_counts = {}
        for job in high_relevance_jobs:
            source_counts[job.source] = source_counts.get(job.source, 0) + 1
        for source, count in source_counts.items():
            logger.info(f"Final jobs from {source}: {count}.")

        return high_relevance_jobs[:100] # Return top 100 most relevant jobs

    def __del__(self):
        """Clean up Selenium driver when the scraper object is deleted."""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                logger.info("Selenium driver quit successfully.")
            except Exception as e:
                logger.error(f"Error quitting Selenium driver: {e}")

class SmartEmailer:
    """Enhanced email system with better formatting and attachments using Gmail API."""
    
    def __init__(self):
        self.gmail_service = self.authenticate_gmail()
    
    def authenticate_gmail(self):
        """
        Authenticates with Gmail API using credentials.json and stores/loads token.pickle.
        """
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Ensure credentials.json is in the same directory or specified path
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        return build('gmail', 'v1', credentials=creds)
    
    def create_excel_report(self, jobs: List[Job]) -> str:
        """Creates an Excel report of the scraped jobs."""
        filename = f"jobs_report_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        job_data = [job.to_dict() for job in jobs]
        df = pd.DataFrame(job_data)
        
        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Jobs', index=False)
                workbook = writer.book
                worksheet = writer.sheets['Jobs']
                # Auto-adjust column width
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    # Set a reasonable max width to prevent excessively wide columns
                    worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50) 
            logger.info(f"Excel report created: {filename}.")
            return filename
        except Exception as e:
            logger.error(f"Error creating Excel report: {e}")
            return ""
    
    def build_smart_html_email(self, jobs: List[Job]) -> str:
        """
        Builds an intelligent HTML email with job insights and top job matches.
        """
        if not jobs:
            logger.info("No jobs to include in the email report.")
            return """
            <!DOCTYPE html>
            <html>
            <body>
                <h2>🔍 Daily Job Hunt Report</h2>
                <p>No new jobs found matching your criteria today.</p>
                <p>The job hunter is still running and will continue searching!</p>
            </body>
            </html>
            """
        
        total_jobs = len(jobs)
        avg_relevance = sum(job.relevance_score for job in jobs) / len(jobs) if jobs else 0
        high_relevance_jobs = [job for job in jobs if job.relevance_score >= 60]
        
        company_counts = {}
        salary_jobs = []
        remote_jobs = []
        source_counts = {}
        skill_counts = {}
        experience_levels = {}
        
        for job in jobs:
            company_counts[job.company] = company_counts.get(job.company, 0) + 1
            if job.salary:
                salary_jobs.append(job)
            if 'remote' in job.location.lower():
                remote_jobs.append(job)
            source_counts[job.source] = source_counts.get(job.source, 0) + 1
            for skill in job.skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
            exp_key = job.experience.lower()
            if 'fresher' in exp_key or 'entry' in exp_key:
                experience_levels['Entry Level'] = experience_levels.get('Entry Level', 0) + 1
            elif 'senior' in exp_key or 'lead' in exp_key or 'manager' in exp_key:
                experience_levels['Senior Level'] = experience_levels.get('Senior Level', 0) + 1
            else:
                experience_levels['Mid Level'] = experience_levels.get('Mid Level', 0) + 1
        
        top_companies = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Ensure Internshala jobs are included in top_jobs if available
        internshala_jobs = [job for job in jobs if job.source == 'Internshala']
        if internshala_jobs:
            # Take top 8 overall, and add up to 2 Internshala jobs if they are not already in top 8
            temp_top_jobs = sorted(jobs, key=lambda x: x.relevance_score, reverse=True)
            top_jobs = []
            internshala_added_count = 0
            for job in temp_top_jobs:
                if len(top_jobs) < 8:
                    top_jobs.append(job)
                elif job.source == 'Internshala' and internshala_added_count < 2 and job not in top_jobs:
                    top_jobs.append(job)
                    internshala_added_count += 1
                if len(top_jobs) >= 10: # Cap at 10 jobs for email
                    break
            # If still less than 10, add more Internshala jobs if available
            if len(top_jobs) < 10 and internshala_jobs:
                for job in internshala_jobs:
                    if job not in top_jobs and len(top_jobs) < 10:
                        top_jobs.append(job)
        else:
            top_jobs = sorted(jobs, key=lambda x: x.relevance_score, reverse=True)[:10]

        logger.info("Job sources in email report:")
        for source, count in source_counts.items():
            logger.info(f"  {source}: {count} jobs")

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Daily Job Intelligence Report</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #4CAF50;
                    color: white;
                    text-align: center;
                    padding: 1em;
                    border-radius: 5px;
                }}
                .summary-stats {{
                    display: flex;
                    justify-content: space-between;
                    margin-top: 20px;
                    flex-wrap: wrap; /* Allow wrapping on smaller screens */
                }}
                .stat-card {{
                    background-color: #f4f4f4;
                    border-radius: 5px;
                    padding: 10px;
                    text-align: center;
                    flex: 1;
                    min-width: 120px; /* Ensure cards don't get too small */
                    margin: 5px; /* Add margin for spacing */
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #4CAF50;
                }}
                .insights {{
                    margin-top: 20px;
                }}
                .tag-container {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 5px;
                    margin-bottom: 10px;
                }}
                .tag {{
                    background-color: #e0e0e0;
                    padding: 5px 10px;
                    border-radius: 20px;
                    font-size: 14px;
                }}
                .job-card {{
                    background-color: #f9f9f9;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 15px;
                    margin-bottom: 15px;
                }}
                .job-title {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #4CAF50;
                }}
                .job-company {{
                    font-weight: bold;
                }}
                .job-meta {{
                    font-size: 14px;
                    color: #666;
                    margin: 5px 0;
                }}
                .job-meta span {{
                    margin-right: 10px; /* Spacing between meta items */
                    display: inline-block; /* Allow wrapping */
                }}
                .job-description {{
                    font-size: 14px;
                    margin-top: 10px;
                }}
                .btn {{
                    display: inline-block;
                    padding: 8px 15px;
                    background-color: #4CAF50;
                    color: white;
                    text-decoration: none;
                    border-radius: 3px;
                    font-size: 14px;
                    margin-top: 10px;
                }}
                .footer {{
                    margin-top: 20px;
                    text-align: center;
                    font-size: 14px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🧠 Daily Job Intelligence Report</h1>
                <p>{datetime.date.today().strftime('%B %d, %Y')}</p>
            </div>
            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-number">{total_jobs}</div>
                    <div class="stat-label">New Jobs</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(high_relevance_jobs)}</div>
                    <div class="stat-label">High Relevance</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{avg_relevance:.0f}%</div>
                    <div class="stat-label">Avg Relevance</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(salary_jobs)}</div>
                    <div class="stat-label">With Salary</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(remote_jobs)}</div>
                    <div class="stat-label">Remote</div>
                </div>
            </div>
            <div class="insights">
                <h2>📊 Market Insights</h2>
                <h3>🏢 Top Hiring Companies</h3>
                <div class="tag-container">
                    {' '.join(f'<span class="tag">{c} ({n})</span>' for c, n in top_companies)}
                </div>
                <h3>🛠️ In-Demand Skills</h3>
                <div class="tag-container">
                    {' '.join(f'<span class="tag">{s} ({n})</span>' for s, n in top_skills)}
                </div>
                <h3>📱 Job Sources</h3>
                <div class="tag-container">
                    {' '.join(f'<span class="tag">{src} ({cnt})</span>' for src, cnt in top_sources)}
                </div>
                <h3>👨‍💼 Experience Levels</h3>
                <div class="tag-container">
                    {' '.join(f'<span class="tag">{lvl} ({cnt})</span>' for lvl, cnt in experience_levels.items())}
                </div>
            </div>
            <h2>🎯 Top Job Matches</h2>
            {''.join(f"""
            <div class="job-card">
                <div class="job-title"><a href="{job.link}" target="_blank" style="color: #4CAF50; text-decoration: none;">{job.title}</a></div>
                <div class="job-company">{job.company}</div>
                <div class="job-meta">
                    <span>📍 {job.location}</span>
                    {f'<span>💰 {job.salary}</span>' if job.salary else ''}
                    {f'<span>👨‍💼 {job.experience}</span>' if job.experience else ''}                    
                    <span>🔗 {job.source}</span>
                    <span>🎯 {job.relevance_score:.0f}% Match</span>
                </div>
                <div class="job-description">{job.description[:200]}{"..." if len(job.description)>200 else ""}</div>
                <div class="tag-container">
                    {' '.join(f'<span class="tag">{s}</span>' for s in job.skills[:5])}
                </div>
                <p><a href="{job.link}" class="btn" target="_blank">Apply Now</a></p>
            </div>
            """ for job in top_jobs)}
            <div class="footer">
                <h3>🤖 AI-Powered Job Intelligence</h3>
                <p>Scanned {total_jobs} jobs from {len(top_sources)} sources.</p>
                <p>Next scan: {(datetime.datetime.now() + datetime.timedelta(hours=12)).strftime('%I:%M %p')}</p>
            </div>
        </body>
        </html>
        """
        return html

    def send_email(self, subject: str, html_content: str, attachment_path: Optional[str] = None):
        """Sends an email with HTML content and an optional attachment using Gmail API."""
        message = MIMEMultipart()
        message['to'] = ', '.join(['musabimp.0@gmail.com', 'Faiza.ansari25@gmail.com']) # Recipient email addresses
        message['subject'] = subject
        message.attach(MIMEText(html_content, 'html'))
        
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as f:
                    mime_base = MIMEBase('application', 'octet-stream')
                    mime_base.set_payload(f.read())
                    encoders.encode_base64(mime_base)
                    mime_base.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"')
                    message.attach(mime_base)
                logger.info(f"Attached file: {os.path.basename(attachment_path)} to email.")
            except Exception as e:
                logger.error(f"Error attaching file {attachment_path}: {e}")
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        try:
            self.gmail_service.users().messages().send(userId='me', body={'raw': raw}).execute()
            logger.info("📧 Email sent successfully!")
        except Exception as e:
            logger.error(f"Error sending email: {e}")

# =================== 👇 Main Automation Runner 👇 ===================

def run_job_alert():
    """
    Main function to run the job scraping and email alert process.
    """
    logger.info("🔍 Starting daily job hunt...")
    scraper = EnhancedJobScraper()
    
    # Optional validation step (uncomment to run for debugging scraper functionality)
    # logger.info("Running scraper validation...")
    # validation_results = scraper.validate_scrapers()
    # for source, count in validation_results.items():
    #     logger.info(f"Validation: {source} found {count} jobs.")

    jobs = scraper.scrape_all_sources() # Call the new orchestration method
    
    if not jobs:
        logger.info("📊 Found 0 new jobs matching criteria today. No email will be sent.")
        # An email with "No new jobs" message will still be sent by build_smart_html_email
        # if the jobs list is empty, which is good.
    
    emailer = SmartEmailer()
    html = emailer.build_smart_html_email(jobs)
    excel_file = emailer.create_excel_report(jobs)
    subject = f"🧠 {len(jobs)} New Job Matches – {datetime.date.today().strftime('%b %d, %Y')}"
    emailer.send_email(subject, html, attachment_path=excel_file)
    
    # Clean up the generated Excel file after sending
    if os.path.exists(excel_file):
        try:
            os.remove(excel_file)
            logger.info(f"Cleaned up Excel report: {excel_file}.")
        except Exception as e:
            logger.error(f"Error deleting Excel file {excel_file}: {e}")

    logger.info("🤖 Super Job Agent finished its run.")

# =================== ⏰ Scheduler Setup ===================

# Schedule the job alert to run twice daily
schedule.every().day.at("09:00").do(run_job_alert)
schedule.every().day.at("18:00").do(run_job_alert)

# High-frequency scheduler (e.g., every 30 seconds) - use with caution!
# This can lead to IP blocking from job sites due to excessive requests.
# Uncomment only if you understand the risks and have measures to handle rate limits/proxies.
# schedule.every(30).seconds.do(run_job_alert)

if __name__ == "__main__":
    logger.info("🚀 Starting Super Job Agent scheduler...")
    run_job_alert() # Run once immediately on startup
    while True:
        schedule.run_pending()
        time.sleep(1) # Sleep for 1 second to avoid busy-waiting

        #Let me know if you want a more powerful or custom-built solution!
