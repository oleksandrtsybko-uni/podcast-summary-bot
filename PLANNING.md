# Podcast Summary Bot - Planning Document

## 🎯 Vision

Create an intelligent, low-maintenance automation system that keeps busy professionals informed about their favorite podcasts without requiring them to listen to full episodes. The bot acts as a personal podcast research assistant, delivering concise, actionable summaries directly to Telegram.

---

## 🏗️ Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions (Scheduler)                    │
│                         Every Thursday 09:00 UTC                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Main Orchestrator                           │
│                         (Python Application)                         │
└─────────────────────────────────────────────────────────────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
    │   RSS    │   │ Transcript│   │    AI    │   │ Telegram │
    │  Parser  │   │  Scraper  │   │Summarizer│   │   Bot    │
    └──────────┘   └──────────┘   └──────────┘   └──────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Podcast │   │  Apple   │   │  OpenAI  │   │ Telegram │
    │RSS Feeds │   │ Podcasts │   │   GPT-4  │   │   API    │
    └──────────┘   │   Web    │   └──────────┘   └──────────┘
                   └──────────┘
```

### Component Architecture

```
src/
├── main.py                 # Entry point & orchestration
├── config/
│   ├── __init__.py
│   ├── settings.py         # Environment & configuration
│   └── podcasts.py         # Podcast definitions (RSS URLs, etc.)
├── services/
│   ├── __init__.py
│   ├── rss_parser.py       # RSS feed fetching & parsing
│   ├── transcript.py       # Transcript acquisition
│   ├── summarizer.py       # OpenAI GPT integration
│   └── telegram.py         # Telegram bot messaging
├── models/
│   ├── __init__.py
│   └── episode.py          # Data models (Episode, Podcast)
├── storage/
│   ├── __init__.py
│   └── tracker.py          # Episode tracking (JSON file)
└── utils/
    ├── __init__.py
    ├── logger.py           # Logging configuration
    └── helpers.py          # Utility functions
```

### Data Flow

1. **Trigger**: GitHub Actions cron triggers `main.py`
2. **Load State**: Read `last_episodes.json` for previously processed episodes
3. **Fetch Feeds**: 
   - **Standard podcasts**: Parse RSS feeds
   - **Lenny's Podcast**: Check Dropbox for newest `.txt` file (returns episode + transcript together)
4. **Detect New**: Compare latest episodes against stored IDs (or filenames for Dropbox-sourced podcasts)
5. **Process New Episodes**:
   - Extract metadata (title, guests, description)
   - Attempt transcript acquisition (skipped for Lenny's - already have it from Dropbox)
   - Generate AI summary
   - Format Telegram message
6. **Deliver**: Send to Telegram
7. **Update State**: Write new episode IDs/filenames to `last_episodes.json`
8. **Commit**: GitHub Actions commits updated state file

---

## 🛠️ Technology Stack

### Core Runtime
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Excellent AI/ML libraries, simple async support |
| Runtime | GitHub Actions | Free cron jobs, native Git integration |

### Dependencies
| Package | Purpose | Version |
|---------|---------|---------|
| `feedparser` | RSS feed parsing | ^6.0 |
| `openai` | GPT-4o API for summaries + Whisper for transcription | ^1.0 |
| `requests` | Telegram HTTP API calls | ^2.32 |
| `httpx` | Async HTTP client | ^0.27 |
| `beautifulsoup4` | HTML parsing (Apple Podcasts transcripts) | ^4.12 |
| `playwright` | Browser automation for transcript scraping (with retry logic for Dropbox) | ^1.40 |
| `pydub` | Audio chunking for Whisper (files >25MB) | ^0.25 |
| `pydantic` | Data validation & settings | ^2.0 |
| `python-dotenv` | Local env management | ^1.0 |

### External Services
| Service | Purpose | Cost |
|---------|---------|------|
| GitHub Actions | Scheduled execution | Free (public repos) |
| OpenAI API | GPT-4 summaries | ~$0.01-0.05/episode |
| Telegram Bot API | Message delivery | Free |
| Apple Podcasts Web | Transcript scraping | Free |

---

## 🔧 Required Tools & Accounts

### Development
- [ ] Python 3.11+ installed locally
- [ ] Git for version control
- [ ] VS Code / Cursor IDE

### Services (Free Accounts Required)
- [ ] **GitHub Account** - Repository & Actions
- [ ] **OpenAI Account** - API key for GPT-4 and Whisper
- [ ] **Telegram Account** - Create bot via @BotFather

### API Keys Needed
| Key | Source | Storage |
|-----|--------|---------|
| `OPENAI_API_KEY` | platform.openai.com | GitHub Secrets |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | GitHub Secrets |
| `TELEGRAM_CHAT_ID` | Your chat/channel ID | GitHub Secrets |

*Note: Whisper API used for 20VC podcast audio transcription. Sub Club and Lenny's use web scraping/Dropbox.*

---

## 📡 Podcast Feed Sources & Detection Methods

| Podcast | Episode Detection | RSS/Source URL | Transcript Method |
|---------|-------------------|----------------|-------------------|
| Lenny's Podcast | Dropbox Archive (newest file) | N/A - Uses Dropbox directly | Dropbox Archive (same file as detection) |
| Sub Club | RSS Feed | `https://feeds.transistor.fm/sub-club` | Apple Podcasts Episode Highlights |
| 20VC | RSS Feed | `https://thetwentyminutevc.libsyn.com/rss` | Whisper AI (audio transcription with chunking) |

*Note: Lenny's Podcast uses Dropbox archive for BOTH episode detection AND transcript acquisition. The newest `.txt` file (by modified date) is used. This eliminates both Substack RSS (403 errors) and Apple Podcasts scraping dependencies. Sub Club RSS corrected from simplecast to transistor.fm.*

### Dropbox Navigation Strategy

The Dropbox transcript fetcher uses a robust navigation approach to handle CI environment challenges:

1. **Wait Strategy**: Uses `domcontentloaded` instead of `networkidle` - Dropbox pages have continuous background network activity (analytics, streaming updates) that prevents `networkidle` from completing
2. **Element Waiting**: Waits for actual file selectors (`a[href*=".txt"], table tbody tr`) rather than arbitrary timeouts
3. **Retry Logic**: 3 attempts with exponential backoff (5s, 10s delays) on timeout failures
4. **Explicit Error Handling**: Catches `PlaywrightTimeoutError` specifically for informative logging

---

## 🔐 Security Considerations

1. **Secrets Management**: All API keys stored in GitHub Secrets, never in code
2. **Minimal Permissions**: GitHub Actions uses minimal required permissions
3. **No PII Storage**: Only episode IDs and titles stored, no user data
4. **Rate Limiting**: Respectful API usage with appropriate delays

---

## 📊 Cost Estimation (Monthly)

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| GitHub Actions | ~10 min/week | $0 (free tier) |
| OpenAI GPT-4o + Whisper | ~3 summaries/week + audio transcription | ~$2-5 |
| Telegram | Unlimited messages | $0 |
| **Total** | | **~$2-5/month** |

*Note: Whisper costs included for 20VC audio transcription (~$0.006/min)*

---

## 🚀 Deployment Strategy

### Phase 1: Local Development
- Develop and test all components locally
- Use `.env` file for API keys
- Manual trigger for testing

### Phase 2: GitHub Actions Integration
- Create workflow file (`.github/workflows/podcast-summary.yml`)
- Configure secrets in repository settings
- Test with manual workflow dispatch

### Phase 3: Production
- Enable scheduled cron trigger
- Monitor first few runs
- Adjust summary prompts based on output quality

---

## 📝 Configuration Schema

```python
# config/podcasts.py
PODCASTS = [
    {
        "id": "lennys-podcast",
        "name": "Lenny's Podcast",
        "rss_url": "https://www.lennyspodcast.com/rss/",
        "website": "https://www.lennyspodcast.com",
        "category": "Product Management"
    },
    # ... more podcasts
]
```

```yaml
# Environment Variables
OPENAI_API_KEY: "sk-..."
TELEGRAM_BOT_TOKEN: "123456:ABC..."
TELEGRAM_CHAT_ID: "-100123456789"
SUMMARY_MODEL: "gpt-4-turbo-preview"
CHECK_DAY: "thursday"
CHECK_HOUR: 9
TIMEZONE: "UTC"
```

---

## 🧪 Testing Strategy

1. **Unit Tests**: Core functions (RSS parsing, guest extraction)
2. **Integration Tests**: API interactions (mocked)
3. **End-to-End**: Manual test run with real feeds
4. **Monitoring**: Telegram error notifications for failures

---

## 📅 Milestone Overview

1. **M1**: Project setup & basic RSS parsing
2. **M2**: Episode tracking & new episode detection
3. **M3**: Transcript acquisition
4. **M4**: AI summarization with OpenAI
5. **M5**: Telegram bot integration
6. **M6**: GitHub Actions deployment
7. **M7**: Testing & polish

See `TASKS.md` for detailed task breakdown.
