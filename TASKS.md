# Podcast Summary Bot - Task Tracker

> **Instructions**: Check off tasks as completed. Add new tasks as discovered.

**Latest Update (v1.4):** Replaced Apple Podcasts scraping with Dropbox-only approach for Lenny's Podcast - uses Dropbox for both episode detection AND transcript (single source of truth).

---

## Milestone 1: Project Setup & Configuration ✅

- [x] Initialize Python project structure
  - [x] Create directory structure (`src/`, `config/`, `services/`, `models/`, `utils/`)
  - [x] Create `requirements.txt` with all dependencies
  - [x] Create `.env.example` with required environment variables
  - [x] Create `.gitignore` for Python project
- [x] Set up configuration module
  - [x] Create `config/settings.py` with Pydantic settings
  - [x] Create `config/podcasts.py` with podcast definitions
- [x] Verify RSS feed URLs for all 4 podcasts
  - [x] Lenny's Podcast RSS URL
  - [x] Lightcone (YC) RSS URL
  - [x] Sub Club RSS URL
  - [x] 20VC RSS URL

---

## Milestone 2: RSS Parsing & Episode Detection ✅

- [x] Implement RSS parser service
  - [x] Create `services/rss_parser.py`
  - [x] Parse RSS feed and extract episode data
  - [x] Extract: title, description, pub_date, guid, audio_url
  - [x] Handle parsing errors gracefully
- [x] Create Episode data model
  - [x] Create `models/episode.py` with Pydantic model
  - [x] Include all required fields (title, guests, etc.)
- [x] Implement guest information extraction
  - [x] Parse guest names from episode title/description
  - [x] Extract LinkedIn URLs if present in description
  - [x] Extract guest description/bio if available

---

## Milestone 3: Episode Tracking & Storage ✅

- [x] Implement episode tracker
  - [x] Create `storage/tracker.py`
  - [x] Load last episodes from JSON file
  - [x] Save updated episodes to JSON file
  - [x] Compare episodes to detect new ones
- [x] Create `last_episodes.json` initial file
- [x] Test detection of new episodes

---

## Milestone 4: Transcript Acquisition ✅

- [x] Research Apple Podcasts transcript structure
  - [x] Analyze Apple Podcasts episode page HTML
  - [x] Identify transcript element selectors
- [x] Implement podcast-specific transcript strategies
  - [x] Create strategy pattern architecture in `services/transcript.py`
  - [x] Sub Club: Scrape from Apple Podcasts "Episode Highlights" section
  - [x] Lenny's Podcast: Download from Dropbox archive (match by guest name)
  - [x] 20VC: Transcribe audio using OpenAI Whisper API
  - [x] Fallback: Set transcript to "Transcript not found" if acquisition fails
- [x] Remove Lightcone podcast from monitoring
- [x] Test transcript acquisition for each podcast

---

## Milestone 5: AI Summarization ✅

- [x] Implement OpenAI summarizer
  - [x] Create `services/summarizer.py`
  - [x] Design summary prompt template
  - [x] Implement GPT-4 API call
  - [x] Structure output (overview, key points, takeaways)
- [x] Create summary formatting utilities
  - [x] Format for Telegram markdown
  - [x] Handle long summaries (chunking)
- [x] Test and refine summary quality
  - [x] Adjust prompts based on output
  - [x] Ensure consistent formatting

---

## Milestone 6: Telegram Bot Integration ✅

- [x] Create Telegram bot via @BotFather
- [x] Implement Telegram service
  - [x] Create `services/telegram.py`
  - [x] Send formatted messages
  - [x] Handle message length limits (split if >4096 chars)
  - [x] Send error notifications
- [x] Design message template
  - [x] Include all required fields
  - [x] Use Telegram markdown formatting
- [x] Test message delivery

---

## Milestone 7: Main Orchestrator ✅

- [x] Implement main.py orchestrator
  - [x] Load configuration
  - [x] Initialize all services
  - [x] Main processing loop
  - [x] Error handling and logging
- [x] Create utility modules
  - [x] Create `utils/logger.py`
  - [x] Create `utils/helpers.py`
- [x] Test full workflow locally

---

## Milestone 8: GitHub Actions Deployment ✅

- [x] Create GitHub Actions workflow
  - [x] Create `.github/workflows/podcast-summary.yml`
  - [x] Configure cron schedule (Thursdays 09:00 UTC)
  - [x] Add manual trigger option
- [x] Configure GitHub repository
  - [x] Add secrets (OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
  - [x] Configure permissions for workflow
- [x] Implement state persistence
  - [x] Auto-commit `last_episodes.json` updates
- [x] Test deployment
  - [x] Run manual workflow dispatch
  - [x] Verify Telegram delivery
  - [x] Monitor first scheduled run

---

## Milestone 9: Testing & Polish ⏳

- [ ] Comprehensive testing
  - [ ] Test with each podcast
  - [ ] Test error scenarios
  - [ ] Test rate limiting
- [ ] Documentation
  - [ ] Update README.md with setup instructions
  - [ ] Document configuration options
  - [ ] Add troubleshooting guide
- [ ] Final review
  - [ ] Code cleanup
  - [ ] Security audit (no leaked secrets)
  - [ ] Performance optimization

---

## Discovered Tasks 📝

*Add new tasks here as they are discovered during development*

- [x] Implement podcast-specific transcript strategies (Sub Club, Lenny's, 20VC)
- [x] Remove Lightcone podcast from monitoring
- [x] Update fallback behavior to use "Transcript not found" instead of description
- [x] Fix Sub Club RSS feed URL (was wrong podcast - UI Breakfast instead of Sub Club)
- [x] Replace async Telegram with direct HTTP requests (fix event loop issues)
- [x] Add audio chunking for 20VC (Whisper 25MB limit)
- [x] Fix Dropbox file selectors for Lenny's Podcast
- [x] Update summary prompt to structured bullet-point format
- [x] Increase transcript character limit to 100,000
- [x] Remove description summary fallback completely
- [x] Fix Lenny's Podcast RSS 403 error by using Apple Podcasts scraping for episode detection
- [x] Add `use_apple_for_detection` flag to PodcastConfig
- [x] Implement `fetch_latest_episode_from_apple()` method in rss_parser.py
- [x] Update Telegram delivery to use channel instead of personal chat
- [x] Replace Apple Podcasts scraping with Dropbox-only approach for Lenny's Podcast (v1.4)
- [x] Add `use_dropbox_for_detection` flag to PodcastConfig
- [x] Implement `detect_and_fetch_latest()` method in LennysTranscriptStrategy
- [x] Add `fetch_latest_episode_from_dropbox()` method to RSSParser
- [x] Update main.py to use Dropbox detection flow when flag is set
- [x] Update episode tracker to track by filename for Dropbox-sourced episodes

---

## Completed Tasks ✅

### Dropbox-Only Episode Detection for Lenny's (v1.4)
- [x] Replaced Apple Podcasts scraping with Dropbox-only approach for Lenny's Podcast
- [x] Added `use_dropbox_for_detection` config flag to PodcastConfig
- [x] Implemented `detect_and_fetch_latest()` method in LennysTranscriptStrategy - returns episode + transcript in one step
- [x] Added `DropboxEpisodeResult` dataclass to hold episode, transcript, and filename
- [x] Added `fetch_latest_episode_from_dropbox()` method to RSSParser
- [x] Updated main.py with `_process_podcast_via_dropbox()` method for Dropbox flow
- [x] Episode tracker now uses filename (instead of GUID) for Dropbox-sourced episodes
- [x] Updated PRD.md, PLANNING.md, and TASKS.md with v1.4 changes

### Lenny's RSS Fix & Telegram Channel (v1.3)
- [x] Substack RSS returns 403 Forbidden on GitHub Actions - implemented Apple Podcasts scraping fallback for Lenny's Podcast
- [x] Added `use_apple_for_detection` config option for podcasts where RSS is blocked
- [x] RSSParser now supports scraping Apple Podcasts show page for episode detection via `fetch_latest_episode_from_apple()`
- [x] Updated Telegram delivery to use channel ID for sharing with multiple users
- [x] Updated PRD.md, PLANNING.md, and TASKS.md with v1.3 changes

### Bug Fixes & Improvements (v1.2)
- [x] Fixed Sub Club RSS feed URL (changed from `feeds.simplecast.com/4MvgQ73R` to `feeds.transistor.fm/sub-club`)
- [x] Replaced async Telegram bot with direct HTTP requests using `requests` library
- [x] Added `pydub` audio chunking for 20VC files larger than 25MB (Whisper API limit)
- [x] Fixed Dropbox CSS selectors for Lenny's Podcast transcript downloads
- [x] Fixed episode URL fallback to prevent scraping wrong content
- [x] Updated summary prompt to structured bullet-point format with 6 sections
- [x] Increased transcript character limit from 50,000 to 100,000
- [x] Removed description summary fallback - now returns "Transcript not found" only
- [x] Updated PRD.md, PLANNING.md, and TASKS.md with v1.2 changes

### Podcast-Specific Transcript Strategies (v1.1)
- [x] Removed Lightcone podcast from monitoring
- [x] Implemented strategy pattern for transcript acquisition
- [x] Sub Club: Scrape from Apple Podcasts "Episode Highlights" section using Playwright
- [x] Lenny's Podcast: Download from Dropbox archive, match files by guest name
- [x] 20VC: Transcribe audio using OpenAI Whisper API
- [x] Updated fallback behavior: Set transcript to "Transcript not found" instead of using description
- [x] Fixed event loop issues in Telegram service
- [x] Updated PRD.md and TASKS.md with changes

---

## Notes

- **Priority**: Focus on getting a working MVP first, then polish
- **Testing**: Test each milestone before moving to next
- **Commits**: Make small, focused commits with clear messages
