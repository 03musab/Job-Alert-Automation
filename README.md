# 🤖 AI-Powered Job Alert Automation

This is an advanced, automated job scraping and intelligence system designed to find the most relevant job opportunities for you. It scans multiple job portals, scores jobs based on your personal criteria using an AI-powered model, and delivers a daily intelligence report directly to your email.


*(Example of the daily email report)*

---

## ✨ Key Features

- **Multi-Source Scraping**: Gathers job listings from multiple sources like **LinkedIn** and **Internshala**.
- **AI Relevance Scoring**: Each job is analyzed and given a relevance score (0-100) based on a highly customizable set of weighted criteria (keywords, skills, experience, location, etc.).
- **Intelligent Deduplication**: Uses an SQLite database to track all found jobs, ensuring you only see new opportunities.
- **Dynamic Web Scraping**: Leverages **Selenium** for scraping jobs from modern, JavaScript-heavy websites.
- **Daily Email Intelligence Report**:
    - Beautifully formatted HTML email with at-a-glance market insights.
    - A summary of the day's findings (total jobs, high-relevance jobs, etc.).
    - Lists the top 10 most relevant job matches with key details.
- **Excel Reports**: Automatically generates and attaches a detailed Excel file of all new jobs found that day.
- **Automated & Scheduled**: Uses a scheduler to run automatically at set times (e.g., twice a day), so you never miss an opportunity.
- **Robust and Resilient**: Includes features like user-agent rotation, timeouts, and concurrent execution to handle scraping efficiently and avoid blocking.

---

## 🛠️ Tech Stack

- **Python 3.x**
- **Scraping**: Selenium, BeautifulSoup, Requests
- **Data Handling**: Pandas, SQLite
- **Email**: Google API Client (Gmail API)
- **Scheduling**: Schedule

---

## 🚀 Getting Started

Follow these steps to get the job alert system up and running on your local machine.

### 1. Prerequisites

- **Python 3.8+**
- **Microsoft Edge** (or another browser if you modify the Selenium setup)
- A **Google Account**

### 2. Clone the Repository

```bash
git clone https://github.com/your-username/Job-Alert-Automation.git
cd Job-Alert-Automation
```

### 3. Set Up a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
# Create a virtual environment
python -m venv .venv

# Activate it
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

### 4. Install Dependencies

Install all the required Python libraries from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 5. Set Up Google Gmail API Credentials

This script uses the Gmail API to send emails. You need to authorize it to send emails on your behalf.

1.  **Go to the Google Cloud Console**: https://console.cloud.google.com/
2.  **Create a new project** (or select an existing one).
3.  **Enable the Gmail API**:
   -   In the search bar, type "Gmail API" and select it.
   -   Click the "Enable" button.
4.  **Create Credentials**:
   -   Go to the "Credentials" page from the left-hand menu.
   -   Click **"+ CREATE CREDENTIALS"** and select **"OAuth client ID"**.
   -   If prompted, configure the "OAuth consent screen". Select **"External"** and fill in the required fields (app name, user support email, and developer contact information). You can skip the "Scopes" and "Test users" sections for now.
   -   For **"Application type"**, select **"Desktop app"**.
   -   Give it a name (e.g., "Job Alert Script").
   -   Click **"Create"**.
5.  **Download Credentials**:
   -   A pop-up will appear with your Client ID and Client Secret. Click **"DOWNLOAD JSON"**.
   -   Rename the downloaded file to `credentials.json` and place it in the root directory of this project.

**First-time Authentication**: The first time you run the script, a browser window will open asking you to authorize the application. Log in with your Google account and grant the necessary permissions. The script will automatically save an authentication file named `token.pickle` for future runs.

### 6. Install WebDriver

This project uses Selenium to control a web browser. You need to download the correct WebDriver for your browser. The current script is configured for **Microsoft Edge**.

1.  **Download Edge WebDriver**: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/
    *(Make sure the version of the driver matches your installed version of Edge.)*
2.  **Place the Driver**: The script currently looks for the driver at `C:\WebDrivers\msedgedriver.exe`.
    -   Create the `C:\WebDrivers` folder and place `msedgedriver.exe` inside it.
    -   Alternatively, you can modify the `edge_driver_path` variable in `daily_job_alert.py` to point to the correct location.

---

## ⚙️ Configuration

You can easily customize the script to match your job search preferences.

### Search Terms

Open `daily_job_alert.py` and modify the `search_terms` list inside the `EnhancedJobScraper` class to define the job titles you're interested in.

```python
# In EnhancedJobScraper class
self.search_terms = ['marketing manager', 'digital marketing', 'brand manager']
```

### Relevance Scoring

The core of the "AI" is in the `JobScorer` class. You can fine-tune the `preferred_keywords` dictionary to change the weight and importance of different skills, industries, job types, etc.

```python
# In JobScorer class
self.preferred_keywords = {
    'high_value': ['your high value keywords...'],
    'medium_value': ['your medium value keywords...'],
    'skills': ['your desired skills...'],
    # ... and so on
}
```

### Email Recipients

Change the email addresses in the `send_email` method of the `SmartEmailer` class.

```python
# In SmartEmailer class, send_email method
message['to'] = ', '.join(['your_email@gmail.com', 'another_email@gmail.com'])
```

---

## ▶️ How to Run

Once everything is configured, simply run the main script from your terminal:

```bash
python daily_job_alert.py
```

The script will run once immediately and then follow the schedule defined at the bottom of the file (default is 9:00 AM and 6:00 PM daily).

---

## 📂 Project Structure

```
Job-Alert-Automation/
├── .venv/                      # Virtual environment directory
├── debug_snapshots/            # Saved HTML snapshots for debugging
├── daily_job_alert.py          # The main application script
├── requirements.txt            # List of Python dependencies
├── jobs.db                     # SQLite database to store and track jobs
├── credentials.json            # (You provide this) Google API credentials
└── token.pickle                # (Auto-generated) Gmail API authentication token
```

---

## 📄 License

This project is licensed under the MIT License. See the `LICENSE.txt` file for details.

---

*This project was created to streamline and supercharge the job search process. Happy hunting!*


