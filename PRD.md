# Podcast Summary Bot - Product Requirements Document

> **⚠️ IMPORTANT FOR AI ASSISTANTS:**
> Always read PLANNING.md at the start of every new conversation, check TASKS.md before starting your work, mark completed tasks to TASKS.md immediately, and add newly discovered tasks to TASKS.md when found.

---

## 1. Executive Summary

**Project Name:** Podcast Summary Bot  
**Version:** 1.5  
**Last Updated:** February 5, 2026

A lightweight automation bot that monitors specific Apple Podcasts shows weekly, detects new episodes, generates AI-powered summaries from transcripts, and delivers structured briefings via Telegram. Designed for busy professionals who want to stay informed about key podcast content without listening to full episodes.

---

## 2. Problem Statement

Professionals interested in product management, venture capital, startups, and growth often follow multiple podcasts but lack the time to listen to all episodes. Currently, there's no automated way to:
- Get notified when specific podcasts release new episodes
- Receive concise, structured summaries of episode content
- Access key guest information and takeaways without full episode consumption

---

## 3. Solution Overview

An automated bot that runs weekly (Thursdays) to:
1. Check RSS feeds of specified podcasts for new episodes
2. Extract episode metadata (title, guests, description)
3. Fetch or generate transcripts
4. Create AI-powered structured summaries using OpenAI GPT
5. Deliver formatted summaries via Telegram bot

---

## 4. Target Podcasts

| # | Podcast Name | Focus Area | Episode Detection | Transcript Method |
|---|--------------|------------|-------------------|-------------------|
| 1 | Lenny's Podcast: Product \| Career \| Growth | Product Management | Dropbox Archive (newest file) | Dropbox Archive (same file) |
| 2 | Sub Club by RevenueCat | Mobile App Monetization | RSS Feed | Apple Podcasts Episode Highlights |
| 3 | The Twenty Minute VC (20VC) | Venture Capital | RSS Feed | Whisper AI Transcription |

**Note:** Lightcone Podcast was removed from monitoring. Lenny's Podcast uses Dropbox for both episode detection AND transcript (single source of truth).

---

## 5. Functional Requirements

### 5.1 Episode Detection (FR-001)
- **Requirement:** System shall check RSS feeds of all target podcasts for new episodes
- **Frequency:** Weekly (configurable, default: Thursdays)
- **Storage:** Minimal - store only last processed episode ID per podcast (or filename for Dropbox-sourced podcasts)
- **Comparison:** Compare latest RSS entry against stored episode ID
- **Dropbox Detection:** For Lenny's Podcast, Dropbox archive is used for both episode detection AND transcript acquisition. The newest `.txt` file (sorted by modified date) determines the latest episode. This eliminates both RSS (Substack 403 errors) and Apple Podcasts scraping dependencies.
- **Dropbox Navigation:** Uses retry logic (3 attempts with exponential backoff) and `domcontentloaded` wait strategy instead of `networkidle` to handle Dropbox's continuous background network activity in CI environments.

### 5.2 Metadata Extraction (FR-002)
- **Requirement:** Extract the following from new episodes:
  - Show name
  - Episode title
  - Episode publication date
  - Episode description
  - Guest names (parsed from title/description)
  - Episode URL
  - Audio URL (for transcript generation if needed)

### 5.3 Guest Information (FR-003)
- **Requirement:** Extract guest names and information from episode description
- **LinkedIn Links:** Extract only if present in episode description/show notes
- **Fallback:** If no LinkedIn link provided, use guest name + brief description from show notes
- **Note:** No external LinkedIn searching - only use what's explicitly provided in the episode metadata

### 5.4 Transcript Acquisition (FR-004)
- **Requirement:** Obtain episode transcript using podcast-specific methods
- **Sources:** 
  - **Sub Club**: Scrape from Apple Podcasts episode page "Episode Highlights" section
  - **Lenny's Podcast**: Download from Dropbox archive (newest file by modified date - same file used for episode detection)
  - **20VC**: Transcribe audio using OpenAI Whisper API (with chunking for files >25MB)
- **Handling:** If transcript acquisition fails, set transcript to "Transcript not found" (no description fallback)
- **Character Limit:** 100,000 characters max for summarization (~25k tokens)

### 5.5 AI Summary Generation (FR-005)
- **Requirement:** Generate structured summary using OpenAI GPT-4o
- **Input:** Episode transcript only
- **Fallback Behavior:** If transcript is "Transcript not found", summary shows "Transcript not found" (no description-based summary)
- **Summary Structure (bullet-point format):**
  1. One-screen overview (6-10 bullets)
  2. Key points by topic
  3. Claims & evidence
  4. Actionable takeaways mentioned
  5. Experiments / AB tests / tactics described
  6. Workflow described (step-by-step processes)
- **Rules:** Only use information explicitly stated in transcript, no assumptions, mark unclear details as "unclear"

### 5.6 Telegram Delivery (FR-006)
- **Requirement:** Send formatted message to specified Telegram chat
- **Message Format:**
  ```
  🎙️ NEW EPISODE ALERT
  
  📺 Show: [Show Name]
  📌 Episode: [Episode Title]
  📅 Published: [Date]
  👤 Guest(s): [Names with LinkedIn search links]
  
  📝 SUMMARY
  [AI-generated structured summary]
  
  🔗 Listen: [Episode URL]
  ```
- **Handling:** Split long messages if exceeding Telegram's 4096 character limit

### 5.7 Scheduled Execution (FR-007)
- **Requirement:** Automated weekly execution
- **Platform:** GitHub Actions (free tier)
- **Schedule:** Every Thursday at 09:00 UTC (configurable)
- **Manual Trigger:** Support for on-demand execution

---

## 6. Non-Functional Requirements

### 6.1 Performance
- Complete full check cycle within 5 minutes
- Handle temporary network failures with retry logic (3 attempts)

### 6.2 Reliability
- Graceful degradation if one podcast fails (continue with others)
- Error notifications via Telegram for failures

### 6.3 Cost
- Must operate within free tiers:
  - GitHub Actions: 2,000 minutes/month (free for public repos)
  - OpenAI API: Pay-per-use (estimated <$5/month)
  - Telegram Bot API: Free

### 6.4 Security
- API keys stored as GitHub Secrets
- No sensitive data logged
- Minimal data retention (only last episode IDs)

### 6.5 Maintainability
- Modular architecture for easy podcast addition/removal
- Configuration via environment variables or config file
- Comprehensive logging for debugging

---

## 7. Data Storage

### 7.1 Episode Tracking (Minimal Storage)
```json
{
  "podcasts": {
    "lennys-podcast": {
      "last_episode_id": "episode-guid-or-url",
      "last_episode_title": "Episode Title",
      "last_checked": "2026-01-21T09:00:00Z"
    }
  }
}
```

### 7.2 Storage Location
- Primary: JSON file in repository (updated via GitHub Actions commit)
- Alternative: GitHub Gist or environment variable

---

## 8. Technical Constraints

| Constraint | Mitigation |
|------------|------------|
| No official Apple Podcasts API | Use RSS feeds (reliable, public) |
| Substack RSS blocks GitHub Actions IPs | Use Dropbox archive for Lenny's (single source for detection + transcript) |
| Apple Podcasts scraping unreliable | Eliminated for Lenny's - use Dropbox instead |
| Dropbox pages have continuous network activity | Use `domcontentloaded` instead of `networkidle`, wait for specific file selectors, retry with exponential backoff |
| Transcript scraping may fail | Set transcript to "Transcript not found" |
| LinkedIn links not always in description | Use guest name + description only (no external lookup) |
| Free hosting limitations | Use GitHub Actions (generous free tier) |
| Telegram message size limit (4096 chars) | Split messages into parts |

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Episode detection accuracy | 100% |
| Summary delivery success rate | >99% |
| Time from episode release to notification | <24 hours (weekly check) |
| Monthly operational cost | <$5 |

---

## 10. Future Enhancements (Out of Scope v1.0)

- [ ] Support for additional podcast platforms (Spotify, etc.)
- [ ] Custom summary length preferences
- [ ] Multiple Telegram recipients/channels
- [ ] Web dashboard for configuration
- [ ] Email delivery option
- [ ] Real-time notifications (instead of weekly)

---

## 11. Glossary

| Term | Definition |
|------|------------|
| RSS | Really Simple Syndication - standard feed format for podcasts |
| Whisper | OpenAI's speech-to-text AI model |
| GitHub Actions | CI/CD platform with free scheduled job execution |

---

## 12. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.5 | 2026-02-05 | Update | Fixed Dropbox navigation timeouts in GitHub Actions. Added retry logic (3 attempts with exponential backoff), changed from `networkidle` to `domcontentloaded` wait strategy, added specific file selector waiting (`a[href*=".txt"]`). |
| 1.4 | 2026-01-27 | Update | Replaced Apple Podcasts scraping with Dropbox-only approach for Lenny's Podcast - now uses Dropbox for both episode detection AND transcript acquisition (single source of truth). Added `use_dropbox_for_detection` config flag, tracks by filename instead of GUID. |
| 1.3 | 2026-01-23 | Update | Added Apple Podcasts scraping for Lenny's Podcast episode detection (Substack RSS 403 workaround), added `use_apple_for_detection` config flag, Telegram delivery via channel |
| 1.2 | 2026-01-22 | Update | Fixed Sub Club RSS feed URL, added audio chunking for 20VC (>25MB files), updated summary prompt to structured bullet-point format, increased transcript limit to 100k chars, replaced async Telegram with direct HTTP requests, removed description fallback completely |
| 1.1 | 2026-01-21 | Update | Implemented podcast-specific transcript strategies (Sub Club, Lenny's, 20VC), removed Lightcone podcast, updated fallback to "Transcript not found" |
| 1.0 | 2026-01-21 | Initial | Initial PRD creation |
