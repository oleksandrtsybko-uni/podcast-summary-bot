# 🎙️ Podcast Summary Bot

An automated bot that monitors your favorite podcasts, detects new episodes, generates AI-powered summaries, and delivers them to Telegram.

## Features

- 📡 **RSS Feed Monitoring** - Automatically checks podcast feeds for new episodes
- 📝 **Transcript Extraction** - Uses podcast-specific methods: Dropbox archive (Lenny's), Apple Podcasts scraping (Sub Club), or Whisper AI transcription (20VC)
- 🤖 **AI Summaries** - Generates structured summaries using OpenAI GPT-4
- 📱 **Telegram Delivery** - Sends beautifully formatted summaries to your Telegram
- ⏰ **Scheduled Runs** - Runs automatically via GitHub Actions (Thursdays at 09:00 UTC)
- 💰 **Low Cost** - Operates within free tiers (~$1-3/month for OpenAI)

## Monitored Podcasts

| Podcast | Category | Transcript Source |
|---------|----------|-------------------|
| Lenny's Podcast | Product Management | Dropbox Archive |
| Sub Club by RevenueCat | Mobile App Monetization | Apple Podcasts (Episode Highlights) |
| The Twenty Minute VC | Venture Capital | Whisper AI Transcription |

## Quick Start

### 1. Prerequisites

- Python 3.11+
- OpenAI API key
- Telegram Bot Token

### 2. Clone & Install

```bash
git clone <your-repo-url>
cd Podcast_summary_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for transcript scraping)
playwright install chromium
```

### 3. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials
# - OPENAI_API_KEY: Get from https://platform.openai.com/api-keys
# - TELEGRAM_BOT_TOKEN: Get from @BotFather on Telegram
# - TELEGRAM_CHAT_ID: Get from @userinfobot on Telegram
```

### 4. Test Locally

```bash
# Test Telegram connection
python -m src.main test

# Run full check (will process new episodes)
python -m src.main

# Force process a specific podcast (for testing)
python -m src.main force lennys-podcast
```

## Deployment (GitHub Actions)

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. Configure Secrets

Go to your repository → Settings → Secrets and variables → Actions

Add these secrets:
- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 3. Enable Workflow

The workflow runs automatically every Thursday at 09:00 UTC.

To test manually:
1. Go to Actions tab
2. Select "Podcast Summary Bot"
3. Click "Run workflow"

## Project Structure

```
Podcast_summary_bot/
├── src/
│   ├── main.py              # Entry point & orchestration
│   ├── config/
│   │   ├── settings.py      # Environment configuration
│   │   └── podcasts.py      # Podcast definitions
│   ├── services/
│   │   ├── rss_parser.py    # RSS feed parsing
│   │   ├── transcript.py    # Apple Podcasts transcript scraping
│   │   ├── summarizer.py    # OpenAI GPT summarization
│   │   └── telegram.py      # Telegram bot messaging
│   ├── models/
│   │   └── episode.py       # Data models
│   ├── storage/
│   │   └── tracker.py       # Episode tracking
│   └── utils/
│       ├── logger.py        # Logging setup
│       └── helpers.py       # Utility functions
├── data/
│   └── last_episodes.json   # Tracks last processed episodes
├── .github/workflows/
│   └── podcast-summary.yml  # GitHub Actions workflow
├── requirements.txt
├── .env.example
└── README.md
```

## Configuration

### Adding New Podcasts

Edit `src/config/podcasts.py`:

```python
PodcastConfig(
    id="my-podcast",
    name="My Podcast Name",
    rss_url="https://example.com/feed.xml",
    apple_podcasts_url="https://podcasts.apple.com/...",
    category="Category"
)
```

### Changing Schedule

Edit `.github/workflows/podcast-summary.yml`:

```yaml
schedule:
  - cron: '0 9 * * 4'  # Current: Thursday 09:00 UTC
  # Examples:
  # '0 9 * * 1'  - Monday 09:00 UTC
  # '0 9 * * 1,4' - Monday and Thursday 09:00 UTC
  # '0 */6 * * *' - Every 6 hours
```

## Telegram Message Format

```
🎙️ NEW EPISODE ALERT

📺 Show: Lenny's Podcast
📌 Episode: How to Build Products Users Love
📅 Published: January 20, 2026
👤 Guest(s): John Doe (CEO at TechCorp)

📝 SUMMARY

**Overview**
A comprehensive discussion about product development...

**Key Topics Discussed**
• User research methods
• Product-market fit
...

🔗 Listen to Episode
```

## Troubleshooting

### Bot not sending messages?
1. Verify `TELEGRAM_BOT_TOKEN` is correct
2. Ensure bot has been started (send /start to your bot)
3. Check `TELEGRAM_CHAT_ID` (use @userinfobot to get your ID)
4. Run `python -m src.main test` to verify connection

### No transcripts being fetched?
- **Sub Club**: Make sure Playwright browsers are installed: `playwright install chromium`. Transcripts are in "Episode Highlights" section.
- **Lenny's Podcast**: Transcripts are downloaded from Dropbox archive. Ensure guest name matches file name in archive.
- **20VC**: Requires audio URL from RSS feed. Whisper API will transcribe the audio file.
- If transcripts aren't found, the bot will fall back to description-based summaries

### GitHub Actions failing?
1. Check that all secrets are configured
2. Review workflow logs for specific errors
3. Ensure repository has Actions enabled

## Cost Estimation

| Service | Monthly Cost |
|---------|-------------|
| GitHub Actions | Free |
| OpenAI GPT-4 | ~$1-3 |
| Telegram | Free |
| **Total** | **~$1-3** |

## License

MIT License - Feel free to modify and use for personal projects.

---

📚 **Documentation**: See `PRD.md`, `PLANNING.md`, and `TASKS.md` for detailed project documentation.
