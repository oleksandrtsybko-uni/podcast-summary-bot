"""
Transcript acquisition service with podcast-specific strategies.
Uses different methods based on podcast: scraping, Dropbox download, or Whisper transcription.
"""

import re
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path
from datetime import datetime

import httpx
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
from openai import OpenAI

from ..models.episode import Episode, Guest
from ..config.podcasts import PodcastConfig
from ..config.settings import get_settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DropboxEpisodeResult:
    """Result from Dropbox-based episode detection."""
    episode: Episode
    transcript: str
    filename: str  # Used for tracking (instead of GUID)

# Lenny's Podcast Dropbox archive URL
LENNYS_DROPBOX_URL = "https://www.dropbox.com/scl/fo/yxi4s2w998p1gvtpu4193/AMdNPR8AOw0lMklwtnC0TrQ?rlkey=j06x0nipoti519e0xgm23zsn9&e=1&st=ahz0fj11&dl=0"


class TranscriptStrategy(ABC):
    """Abstract base class for transcript acquisition strategies."""
    
    @abstractmethod
    def fetch_transcript(
        self,
        episode: Episode,
        podcast: PodcastConfig,
        browser: Optional[Page] = None
    ) -> Optional[str]:
        """
        Fetch transcript for an episode.
        
        Args:
            episode: Episode to fetch transcript for
            podcast: Podcast configuration
            browser: Optional Playwright page (for strategies that need it)
        
        Returns:
            Transcript text if found, None otherwise
        """
        pass


class SubClubTranscriptStrategy(TranscriptStrategy):
    """Scrapes transcripts from Apple Podcasts Episode Highlights section."""
    
    def fetch_transcript(
        self,
        episode: Episode,
        podcast: PodcastConfig,
        browser: Optional[Page] = None
    ) -> Optional[str]:
        """Fetch transcript from Apple Podcasts Episode Highlights section."""
        if not browser:
            logger.error("Sub Club strategy requires browser instance")
            return None
        
        try:
            # Find episode URL
            episode_url = self._find_episode_url(episode, browser)
            if not episode_url:
                logger.warning(f"Could not find episode URL for: {episode.title}")
                return None
            
            # Navigate to episode page
            logger.info(f"Fetching Sub Club transcript from: {episode_url}")
            browser.goto(episode_url, wait_until="networkidle", timeout=30000)
            browser.wait_for_timeout(3000)  # Wait for content to load
            
            # Look for "Episode Highlights" section
            transcript = self._extract_from_highlights(browser)
            
            if transcript:
                logger.info(f"Successfully extracted Sub Club transcript ({len(transcript)} chars)")
                return transcript
            else:
                logger.warning("No transcript found in Episode Highlights section")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching Sub Club transcript: {e}")
            return None
    
    def _find_episode_url(self, episode: Episode, browser: Page) -> Optional[str]:
        """Find the specific episode URL on Apple Podcasts."""
        # If we already have a specific episode URL with Apple, use it
        if episode.episode_url and 'apple.com' in episode.episode_url:
            return episode.episode_url
        
        if not episode.apple_podcasts_url:
            logger.warning("No Apple Podcasts URL configured")
            return None
        
        try:
            browser.goto(episode.apple_podcasts_url, wait_until="networkidle", timeout=30000)
            browser.wait_for_timeout(2000)
            
            episode_title_lower = episode.title.lower()
            links = browser.locator('a[href*="?i="], a[href*="/episode/"]').all()
            
            for link in links:
                try:
                    link_text = link.text_content()
                    if link_text and self._titles_match(episode_title_lower, link_text.lower()):
                        href = link.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                href = f"https://podcasts.apple.com{href}"
                            logger.info(f"Found matching episode URL: {href}")
                            return href
                except Exception:
                    continue
            
            # DO NOT fallback to show page - this causes wrong transcript to be scraped
            logger.warning(f"Could not find specific episode URL for: {episode.title}")
            return None
        except Exception as e:
            logger.debug(f"Error finding episode URL: {e}")
            return None
    
    def _extract_from_highlights(self, page: Page) -> Optional[str]:
        """Extract transcript from Episode Highlights section."""
        try:
            # Get the full page text first
            page_text = page.locator('body').text_content() or ""
            page_text_lower = page_text.lower()
            
            # Method 1: Look for "Episode Highlights" heading and extract text after it
            if 'episode highlights' in page_text_lower:
                # Try to find the Episode Highlights section
                # Split by "Episode Highlights" and get everything after
                parts = page_text.split('Episode Highlights')
                if len(parts) > 1:
                    highlights_text = parts[1]
                    # Clean up - remove common footer/nav text
                    stop_markers = ['See All', 'More Episodes', 'You Might Also Like', 'Customer Reviews', 'Top Podcasts']
                    for marker in stop_markers:
                        if marker in highlights_text:
                            highlights_text = highlights_text.split(marker)[0]
                    
                    if len(highlights_text) > 200:
                        return self._clean_transcript(highlights_text)
            
            # Method 2: Look for description section with substantial text
            description_selectors = [
                '[data-testid="episode-description"]',
                '.episode-description',
                'section[class*="description"]',
                '[class*="notes"]',
                '[class*="episode-details"]',
            ]
            
            for selector in description_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        text = element.text_content()
                        if text and len(text) > 500:  # Substantial content
                            return self._clean_transcript(text)
                except Exception:
                    continue
            
            # Method 3: Look for the main content area and extract text
            main_content = page.locator('main, [role="main"]').first
            if main_content.count() > 0:
                # Look for the episode description within main
                all_paragraphs = main_content.locator('p').all()
                long_texts = []
                for p in all_paragraphs:
                    try:
                        text = p.text_content()
                        if text and len(text) > 100:
                            long_texts.append(text)
                    except Exception:
                        continue
                
                if long_texts:
                    combined = '\n\n'.join(long_texts)
                    if len(combined) > 500:
                        return self._clean_transcript(combined)
            
            return None
        except Exception as e:
            logger.debug(f"Error extracting from highlights: {e}")
            return None
    
    def _extract_content_after_heading(self, heading_element, page: Page) -> Optional[str]:
        """Extract content that appears after a heading element."""
        try:
            # Try to get parent and all its text
            parent = heading_element.locator('..').first
            if parent.count() > 0:
                text = parent.text_content()
                # Remove the heading text itself
                if text:
                    parts = text.split('Episode Highlights', 1)
                    if len(parts) > 1:
                        return parts[1].strip()
            
            # Try next sibling
            try:
                next_sibling = heading_element.evaluate_handle('el => el.nextElementSibling')
                if next_sibling:
                    text = page.evaluate('el => el.textContent', next_sibling)
                    if text and len(text) > 200:
                        return text
            except Exception:
                pass
            
            return None
        except Exception:
            return None
    
    def _titles_match(self, title1: str, title2: str) -> bool:
        """Fuzzy title matching with normalization."""
        # Normalize both titles - replace special characters
        def normalize(s):
            s = s.lower()
            # Replace various dashes with standard hyphen
            s = s.replace('–', '-').replace('—', '-').replace('−', '-')
            # Replace smart quotes
            s = s.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"')
            # Remove extra whitespace
            s = ' '.join(s.split())
            return s
        
        t1 = normalize(title1)
        t2 = normalize(title2)
        
        if t1 == t2:
            return True
        if t1 in t2 or t2 in t1:
            return True
        
        # Compare first 5 words
        words1 = t1.split()[:5]
        words2 = t2.split()[:5]
        if words1 == words2:
            return True
        
        # Check if first 3 significant words match (skip common words)
        skip_words = {'the', 'a', 'an', 'and', 'or', 'with', 'by', 'for', 'to', 'of', 'in', 'on'}
        sig_words1 = [w for w in t1.split() if w not in skip_words][:3]
        sig_words2 = [w for w in t2.split() if w not in skip_words][:3]
        
        return sig_words1 == sig_words2
    
    def _clean_transcript(self, text: str) -> str:
        """Clean transcript text."""
        if not text:
            return ""
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()


class LennysTranscriptStrategy(TranscriptStrategy):
    """Downloads transcripts from Dropbox archive, matching by guest name."""
    
    def fetch_transcript(
        self,
        episode: Episode,
        podcast: PodcastConfig,
        browser: Optional[Page] = None
    ) -> Optional[str]:
        """Fetch transcript from Dropbox archive."""
        if not browser:
            logger.error("Lenny's strategy requires browser instance")
            return None
        
        try:
            # Get guest name from episode
            guest_name = self._extract_guest_name(episode)
            if not guest_name:
                logger.warning(f"No guest name found for episode: {episode.title}")
                return None
            
            logger.info(f"Looking for Lenny's transcript for guest: {guest_name}")
            
            # Navigate to Dropbox folder (increased timeout for slow loads)
            browser.goto(LENNYS_DROPBOX_URL, wait_until="networkidle", timeout=60000)
            browser.wait_for_timeout(5000)  # Wait for files to load
            
            # Find files in the folder
            files = self._list_dropbox_files(browser)
            if not files:
                logger.warning("No files found in Dropbox folder")
                return None
            
            # Find most recent file matching guest name
            matching_file = self._find_matching_file(files, guest_name)
            if not matching_file:
                logger.warning(f"No file found matching guest: {guest_name}")
                return None
            
            # Download and parse the file
            transcript = self._download_and_parse_file(browser, matching_file)
            return transcript
            
        except Exception as e:
            logger.error(f"Error fetching Lenny's transcript: {e}")
            return None
    
    def detect_and_fetch_latest(
        self,
        podcast: PodcastConfig,
        browser: Page
    ) -> Optional[DropboxEpisodeResult]:
        """
        Detect the latest episode from Dropbox and fetch its transcript in one step.
        Used for episode detection when RSS/Apple Podcasts are blocked.
        
        Args:
            podcast: Podcast configuration
            browser: Playwright Page instance
        
        Returns:
            DropboxEpisodeResult with episode, transcript, and filename if found
        """
        try:
            logger.info(f"Detecting latest Lenny's episode from Dropbox archive...")
            
            # Navigate to Dropbox folder
            browser.goto(LENNYS_DROPBOX_URL, wait_until="networkidle", timeout=60000)
            browser.wait_for_timeout(5000)  # Wait for files to load
            
            # Sort by Modified date (newest first)
            try:
                modified_button = browser.locator('button:has-text("Modified")').first
                if modified_button.count() > 0:
                    # Click twice to ensure descending order (newest first)
                    modified_button.click()
                    browser.wait_for_timeout(1500)
                    # Check if we need to click again for descending
                    modified_button.click()
                    browser.wait_for_timeout(2000)
                    logger.info("Sorted Dropbox files by Modified date (newest first)")
            except Exception as e:
                logger.warning(f"Could not sort by modified date: {e}")
            
            # Get files from Dropbox
            files = self._list_dropbox_files(browser)
            if not files:
                logger.warning("No files found in Dropbox folder")
                return None
            
            # Get the first file (should be newest after sorting)
            newest_file = files[0]
            logger.info(f"Newest file in Dropbox: {newest_file['name']}")
            
            # Extract guest name from filename
            guest_name = self._extract_guest_from_filename(newest_file['name'])
            if not guest_name:
                logger.warning(f"Could not extract guest name from filename: {newest_file['name']}")
                guest_name = Path(newest_file['name']).stem  # Use filename without extension
            
            logger.info(f"Detected guest: {guest_name}")
            
            # Download the transcript
            transcript = self._download_and_parse_file(browser, newest_file)
            if not transcript:
                logger.error(f"Failed to download transcript for: {newest_file['name']}")
                return None
            
            logger.info(f"Successfully downloaded transcript ({len(transcript)} chars)")
            
            # Create Episode object from Dropbox file info
            episode = Episode(
                guid=f"dropbox-{newest_file['name']}",  # Unique identifier based on filename
                podcast_id=podcast.id,
                title=f"Lenny's Podcast | {guest_name}",  # Construct title from guest name
                description="",  # No description available from Dropbox
                published_date=newest_file.get('modified_date'),  # Use file modified date if available
                episode_url=podcast.website,  # Link to podcast website
                audio_url=None,
                apple_podcasts_url=podcast.apple_podcasts_url,
                guests=[Guest(name=guest_name)],
                duration=None,
            )
            
            # Enrich episode with Apple Podcasts metadata
            logger.info("Enriching episode with Apple Podcasts metadata...")
            enriched_episode = self._enrich_from_apple_podcasts(episode, guest_name, podcast, browser)
            if enriched_episode:
                episode = enriched_episode
                logger.info(f"Enriched episode: {episode.title}")
            else:
                logger.warning("Could not enrich episode from Apple Podcasts, using Dropbox data only")
            
            return DropboxEpisodeResult(
                episode=episode,
                transcript=transcript,
                filename=newest_file['name']
            )
            
        except Exception as e:
            logger.error(f"Error detecting latest episode from Dropbox: {e}")
            return None
    
    def _enrich_from_apple_podcasts(
        self,
        episode: Episode,
        guest_name: str,
        podcast: PodcastConfig,
        browser: Page
    ) -> Optional[Episode]:
        """
        Enrich episode metadata from Apple Podcasts.
        Gets the latest episode and extracts: clean title, date, and LinkedIn URL.
        Does NOT include full description (we only need title, date, guest link).
        
        Args:
            episode: Basic episode from Dropbox
            guest_name: Guest name extracted from Dropbox filename
            podcast: Podcast configuration
            browser: Playwright Page instance
        
        Returns:
            Enriched Episode object, or None if enrichment fails
        """
        if not podcast.apple_podcasts_url:
            logger.warning("No Apple Podcasts URL configured")
            return None
        
        try:
            # Navigate to Apple Podcasts show page
            logger.info(f"Fetching Apple Podcasts metadata from: {podcast.apple_podcasts_url}")
            browser.goto(podcast.apple_podcasts_url, wait_until="networkidle", timeout=30000)
            browser.wait_for_timeout(3000)  # Wait for dynamic content
            
            # Get the first/latest episode link
            episode_links = browser.locator('a[href*="?i="]').all()
            if not episode_links:
                logger.warning("No episode links found on Apple Podcasts page")
                return None
            
            first_episode_link = episode_links[0]
            
            # Get episode URL
            episode_url = first_episode_link.get_attribute('href')
            if episode_url and not episode_url.startswith('http'):
                episode_url = f"https://podcasts.apple.com{episode_url}"
            
            # Navigate to episode page to get clean title and details
            apple_title = None
            published_date = None
            linkedin_url = None
            
            if episode_url:
                try:
                    browser.goto(episode_url, wait_until="networkidle", timeout=20000)
                    browser.wait_for_timeout(2000)
                    
                    # Extract clean episode title from the page header (not the link text)
                    title_selectors = [
                        'h1[class*="headings"]',
                        'h1[class*="title"]',
                        'h1',
                        '[data-testid="episode-title"]',
                    ]
                    for selector in title_selectors:
                        try:
                            title_elem = browser.locator(selector).first
                            if title_elem.count() > 0:
                                title_text = title_elem.text_content()
                                if title_text and len(title_text) > 10:
                                    apple_title = title_text.strip()
                                    # Remove any leading date indicators like "2D AGO"
                                    apple_title = re.sub(r'^\d+[DHM]\s+AGO\s+', '', apple_title, flags=re.IGNORECASE)
                                    break
                        except Exception:
                            continue
                    
                    # Extract published date - try multiple selectors
                    date_selectors = [
                        'time[datetime]',
                        'time',
                        '[datetime]',
                        '.episode-date',
                        '[class*="date"]',
                        '[class*="Date"]',
                    ]
                    for selector in date_selectors:
                        try:
                            date_elem = browser.locator(selector).first
                            if date_elem.count() > 0:
                                date_str = date_elem.get_attribute('datetime') or date_elem.text_content()
                                if date_str:
                                    parsed = self._parse_apple_date(date_str.strip())
                                    if parsed:
                                        published_date = parsed
                                        logger.info(f"Found date: {published_date}")
                                        break
                        except Exception:
                            continue
                    
                    # Fallback: look for date pattern in page text
                    if not published_date:
                        try:
                            # Apple sometimes shows dates like "JAN 25, 2026" near the episode info
                            page_text = browser.locator('main').first.text_content() or ""
                            # Look for date patterns
                            date_patterns = [
                                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
                                r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{1,2},?\s+\d{4}',
                            ]
                            for pattern in date_patterns:
                                match = re.search(pattern, page_text, re.IGNORECASE)
                                if match:
                                    published_date = self._parse_apple_date(match.group(0))
                                    if published_date:
                                        logger.info(f"Found date from pattern: {published_date}")
                                        break
                        except Exception:
                            pass
                    
                    # Extract LinkedIn URL from description (we only want the URL, not the text)
                    desc_selectors = [
                        '[data-testid="description"]',
                        '.product-hero-desc',
                        'section[class*="description"]',
                    ]
                    for selector in desc_selectors:
                        try:
                            desc_elem = browser.locator(selector).first
                            if desc_elem.count() > 0:
                                desc_text = desc_elem.text_content() or ""
                                # Only extract LinkedIn URL
                                linkedin_match = re.search(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+', desc_text)
                                if linkedin_match:
                                    linkedin_url = linkedin_match.group(0)
                                    logger.info(f"Found LinkedIn URL: {linkedin_url}")
                                    break
                        except Exception:
                            continue
                    
                except Exception as e:
                    logger.debug(f"Could not get episode details: {e}")
            
            # Sanity check: verify guest name appears in title
            if guest_name and apple_title:
                guest_name_lower = guest_name.lower()
                apple_title_lower = apple_title.lower()
                guest_parts = guest_name_lower.split()
                matches = sum(1 for part in guest_parts if part in apple_title_lower)
                if matches < len(guest_parts) // 2 + 1:
                    logger.warning(f"Guest name mismatch! Dropbox: '{guest_name}', Apple title: '{apple_title}'")
            
            # Create enriched episode with clean data
            enriched_guests = episode.guests
            if enriched_guests:
                # Update guest with LinkedIn URL if found
                enriched_guests = [Guest(
                    name=enriched_guests[0].name,
                    linkedin_url=linkedin_url,  # Will be None if not found
                    description=None
                )]
            
            return Episode(
                guid=episode.guid,
                podcast_id=episode.podcast_id,
                title=apple_title or episode.title,
                description="",  # Don't include description - we only need title/date/guest
                published_date=published_date or episode.published_date,
                episode_url=episode_url or episode.episode_url,
                audio_url=episode.audio_url,
                apple_podcasts_url=episode_url or episode.apple_podcasts_url,
                guests=enriched_guests,
                duration=episode.duration,
            )
            
        except Exception as e:
            logger.error(f"Error enriching from Apple Podcasts: {e}")
            return None
    
    def _parse_apple_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from Apple Podcasts."""
        if not date_str:
            return None
        
        # Try various formats
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",      # January 25, 2026
            "%B %d %Y",       # January 25 2026
            "%b %d, %Y",      # Jan 25, 2026
            "%b %d %Y",       # Jan 25 2026
            "%d %B %Y",       # 25 January 2026
            "%d %b %Y",       # 25 Jan 2026
            "%B %d",          # January 25 (assume current year)
            "%b %d",          # Jan 25 (assume current year)
        ]
        
        date_str = date_str.strip()
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no year in format, use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        
        return None
    
    def _extract_guest_from_filename(self, filename: str) -> Optional[str]:
        """Extract guest name from Dropbox filename."""
        # Remove file extension
        name = Path(filename).stem
        
        # Common patterns in Lenny's transcript filenames:
        # - "Guest Name.txt"
        # - "Guest Name - Topic.txt"
        # - "Lenny's Podcast - Guest Name.txt"
        
        # Remove common prefixes
        prefixes_to_remove = ["Lenny's Podcast - ", "Lennys Podcast - ", "LP - "]
        for prefix in prefixes_to_remove:
            if name.startswith(prefix):
                name = name[len(prefix):]
        
        # If there's a dash, take the part that looks like a name (usually first part)
        if " - " in name:
            parts = name.split(" - ")
            # Usually the guest name is the first or second part
            for part in parts:
                # A name typically has 2-4 words
                words = part.strip().split()
                if 1 <= len(words) <= 5 and all(w[0].isupper() for w in words if w):
                    return part.strip()
            # Fallback to first part
            name = parts[0]
        
        return name.strip() if name.strip() else None
    
    def _extract_guest_name(self, episode: Episode) -> Optional[str]:
        """Extract guest name from episode."""
        if episode.guests:
            # Use first guest's name
            return episode.guests[0].name
        
        # Try to extract from title (common pattern: "Topic | Guest Name")
        title = episode.title
        if '|' in title:
            parts = title.split('|')
            if len(parts) > 1:
                # Last part often contains guest name
                guest_part = parts[-1].strip()
                # Remove common suffixes like "(Company)"
                guest_part = re.sub(r'\s*\([^)]+\)\s*$', '', guest_part)
                if len(guest_part) > 2:
                    return guest_part
        
        return None
    
    def _list_dropbox_files(self, page: Page) -> list[dict]:
        """List files in Dropbox folder with modified dates."""
        files = []
        try:
            # Dropbox uses a table structure - find all rows
            # Each row contains: filename link, modified date, etc.
            file_rows = page.locator('table tbody tr').all()
            
            for row in file_rows:
                try:
                    # Get the file link
                    link = row.locator('a[href*=".txt"]').first
                    if link.count() == 0:
                        continue
                    
                    # Get the file name from the button inside the link
                    button = link.locator('button').first
                    if button.count() > 0:
                        file_name = button.text_content()
                    else:
                        file_name = link.text_content()
                    
                    href = link.get_attribute('href')
                    
                    if not file_name or not href or '.txt' not in href:
                        continue
                    
                    # Clean the file name
                    clean_name = file_name.strip()
                    if not clean_name:
                        continue
                    
                    # Try to get modified date from the row
                    modified_date = None
                    try:
                        # Dropbox shows modified date in a cell, look for time element or date text
                        date_cell = row.locator('td').nth(1)  # Usually second column
                        if date_cell.count() > 0:
                            date_text = date_cell.text_content()
                            if date_text:
                                modified_date = self._parse_dropbox_date(date_text.strip())
                    except Exception:
                        pass
                    
                    files.append({
                        'name': clean_name,
                        'url': href if href.startswith('http') else f"https://www.dropbox.com{href}",
                        'modified_date': modified_date
                    })
                except Exception:
                    continue
            
            # Fallback: try original method if table rows didn't work
            if not files:
                file_links = page.locator('table a[href*=".txt"]').all()
                for link in file_links:
                    try:
                        button = link.locator('button').first
                        if button.count() > 0:
                            file_name = button.text_content()
                        else:
                            file_name = link.text_content()
                        
                        href = link.get_attribute('href')
                        
                        if file_name and href and '.txt' in href:
                            clean_name = file_name.strip()
                            if clean_name:
                                files.append({
                                    'name': clean_name,
                                    'url': href if href.startswith('http') else f"https://www.dropbox.com{href}",
                                    'modified_date': None
                                })
                    except Exception:
                        continue
            
            # Second fallback: try to find links with scl/fo pattern
            if not files:
                file_links = page.locator('a[href*="/scl/fo/"]').all()
                for link in file_links:
                    try:
                        href = link.get_attribute('href')
                        if href and '.txt' in href:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(href)
                            path_parts = parsed.path.split('/')
                            for part in path_parts:
                                if '.txt' in part:
                                    file_name = urllib.parse.unquote(part)
                                    files.append({
                                        'name': file_name,
                                        'url': href if href.startswith('http') else f"https://www.dropbox.com{href}",
                                        'modified_date': None
                                    })
                                    break
                    except Exception:
                        continue
            
            logger.info(f"Found {len(files)} files in Dropbox folder")
            return files
        except Exception as e:
            logger.error(f"Error listing Dropbox files: {e}")
            return []
    
    def _parse_dropbox_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from Dropbox modified column."""
        if not date_str:
            return None
        
        # Dropbox uses formats like:
        # - "Jan 15, 2026"
        # - "Yesterday"
        # - "Today"
        # - "Jan 15"
        
        date_str = date_str.strip()
        
        # Handle relative dates
        if date_str.lower() == 'today':
            return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if date_str.lower() == 'yesterday':
            from datetime import timedelta
            return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Try various date formats
        formats = [
            "%b %d, %Y",  # Jan 15, 2026
            "%B %d, %Y",  # January 15, 2026
            "%b %d",      # Jan 15 (assume current year)
            "%Y-%m-%d",   # 2026-01-15
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no year in format, use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        
        return None
    
    def _find_matching_file(self, files: list[dict], guest_name: str) -> Optional[dict]:
        """Find file that matches guest name (fuzzy matching)."""
        guest_name_lower = guest_name.lower()
        guest_parts = guest_name_lower.split()
        
        best_match = None
        best_score = 0
        
        for file in files:
            file_name_lower = file['name'].lower()
            # Remove file extension for matching
            file_name_no_ext = Path(file['name']).stem.lower()
            
            # Calculate match score
            score = 0
            
            # Exact match
            if guest_name_lower in file_name_no_ext or file_name_no_ext in guest_name_lower:
                score += 10
            
            # Check if all name parts appear in filename
            matching_parts = sum(1 for part in guest_parts if part in file_name_no_ext)
            if matching_parts == len(guest_parts):
                score += 5
            elif matching_parts > 0:
                score += matching_parts
            
            if score > best_score:
                best_score = score
                best_match = file
        
        if best_match and best_score > 0:
            logger.info(f"Matched file: {best_match['name']} (score: {best_score})")
            return best_match
        
        return None
    
    def _download_and_parse_file(self, page: Page, file_info: dict) -> Optional[str]:
        """Download and parse transcript file."""
        try:
            # Navigate to file page and get raw download URL
            file_url = file_info['url']
            
            # Change dl=0 to dl=1 for direct download
            if 'dl=0' in file_url:
                file_url = file_url.replace('dl=0', 'dl=1')
            elif '?dl=' not in file_url and '&dl=' not in file_url:
                file_url = file_url + ('&dl=1' if '?' in file_url else '?dl=1')
            
            logger.info(f"Downloading file: {file_info['name']} from {file_url}")
            
            # Use httpx to download with redirect following
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                response = client.get(file_url)
                response.raise_for_status()
                
                # Determine file type and parse
                file_ext = Path(file_info['name']).suffix.lower()
                
                if file_ext == '.txt':
                    transcript = response.text
                    if transcript and len(transcript) > 100:
                        logger.info(f"Successfully downloaded transcript ({len(transcript)} chars)")
                        return transcript
                    else:
                        logger.warning(f"Downloaded content too short: {len(transcript) if transcript else 0} chars")
                        return None
                elif file_ext == '.pdf':
                    logger.warning("PDF parsing not implemented")
                    return None
                elif file_ext in ['.doc', '.docx']:
                    logger.warning("DOCX parsing not implemented")
                    return None
                else:
                    # Try as text
                    try:
                        return response.text
                    except Exception:
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading/parsing file: {e}")
            return None


class TwentyVCTranscriptStrategy(TranscriptStrategy):
    """Transcribes audio using OpenAI Whisper API with chunking for large files."""
    
    # Whisper API has a 25MB file size limit
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
    # Target chunk size (20MB to leave some headroom)
    TARGET_CHUNK_SIZE = 20 * 1024 * 1024  # 20 MB
    
    def __init__(self):
        """Initialize Whisper strategy."""
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def fetch_transcript(
        self,
        episode: Episode,
        podcast: PodcastConfig,
        browser: Optional[Page] = None
    ) -> Optional[str]:
        """Fetch transcript by transcribing audio with Whisper."""
        if not episode.audio_url:
            logger.warning(f"No audio URL for episode: {episode.title}")
            return None
        
        tmp_path = None
        chunk_paths = []
        
        try:
            logger.info(f"Transcribing 20VC audio: {episode.audio_url}")
            
            # Create temporary file for downloaded audio
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
            
            # Download audio
            logger.info("Downloading audio file...")
            with httpx.Client(timeout=600.0, follow_redirects=True) as client:
                response = client.get(episode.audio_url)
                response.raise_for_status()
                with os.fdopen(tmp_fd, 'wb') as tmp_file:
                    tmp_file.write(response.content)
            
            # Check file size
            file_size = os.path.getsize(tmp_path)
            logger.info(f"Downloaded audio file: {file_size / (1024*1024):.2f} MB")
            
            if file_size <= self.MAX_FILE_SIZE:
                # File is small enough, transcribe directly
                return self._transcribe_file(tmp_path)
            else:
                # File too large, need to chunk it
                logger.info(f"File too large ({file_size / (1024*1024):.2f} MB), splitting into chunks...")
                chunk_paths = self._split_audio(tmp_path)
                
                if not chunk_paths:
                    logger.error("Failed to split audio file")
                    return None
                
                logger.info(f"Split into {len(chunk_paths)} chunks")
                
                # Transcribe each chunk
                transcripts = []
                for i, chunk_path in enumerate(chunk_paths):
                    logger.info(f"Transcribing chunk {i+1}/{len(chunk_paths)}...")
                    chunk_transcript = self._transcribe_file(chunk_path)
                    if chunk_transcript:
                        transcripts.append(chunk_transcript)
                    else:
                        logger.warning(f"Failed to transcribe chunk {i+1}")
                
                if transcripts:
                    full_transcript = ' '.join(transcripts)
                    logger.info(f"Successfully transcribed audio ({len(full_transcript)} chars from {len(transcripts)} chunks)")
                    return self._clean_transcript(full_transcript)
                else:
                    logger.error("No chunks were transcribed successfully")
                    return None
                        
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None
        finally:
            # Clean up temporary files
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            for chunk_path in chunk_paths:
                if os.path.exists(chunk_path):
                    try:
                        os.unlink(chunk_path)
                    except Exception:
                        pass
    
    def _split_audio(self, audio_path: str) -> list[str]:
        """Split audio file into chunks under 25MB using pydub."""
        try:
            from pydub import AudioSegment
            
            # Load audio file
            audio = AudioSegment.from_mp3(audio_path)
            
            # Calculate duration and chunk count
            file_size = os.path.getsize(audio_path)
            duration_ms = len(audio)
            
            # Estimate bytes per millisecond
            bytes_per_ms = file_size / duration_ms
            
            # Calculate chunk duration to get ~20MB chunks
            chunk_duration_ms = int(self.TARGET_CHUNK_SIZE / bytes_per_ms)
            
            # Ensure minimum chunk duration of 1 minute
            chunk_duration_ms = max(chunk_duration_ms, 60 * 1000)
            
            chunk_paths = []
            start_ms = 0
            chunk_num = 0
            
            while start_ms < duration_ms:
                end_ms = min(start_ms + chunk_duration_ms, duration_ms)
                chunk = audio[start_ms:end_ms]
                
                # Export chunk to temp file
                chunk_path = tempfile.mktemp(suffix=f'_chunk{chunk_num}.mp3')
                chunk.export(chunk_path, format='mp3')
                
                # Verify chunk size
                chunk_size = os.path.getsize(chunk_path)
                if chunk_size > self.MAX_FILE_SIZE:
                    # Chunk still too large, make it smaller
                    os.unlink(chunk_path)
                    chunk_duration_ms = int(chunk_duration_ms * 0.7)
                    continue
                
                chunk_paths.append(chunk_path)
                logger.debug(f"Created chunk {chunk_num}: {chunk_size / (1024*1024):.2f} MB")
                
                start_ms = end_ms
                chunk_num += 1
            
            return chunk_paths
            
        except ImportError:
            logger.error("pydub not installed. Install with: pip install pydub")
            return []
        except Exception as e:
            logger.error(f"Error splitting audio: {e}")
            return []
    
    def _transcribe_file(self, file_path: str) -> Optional[str]:
        """Transcribe a single audio file with Whisper."""
        try:
            with open(file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            # Whisper API returns string when response_format="text"
            return transcript if isinstance(transcript, str) else str(transcript)
            
        except Exception as e:
            logger.error(f"Error transcribing file: {e}")
            return None
    
    def _clean_transcript(self, text: str) -> str:
        """Clean transcript text."""
        if not text:
            return ""
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()


class TranscriptScraper:
    """Router that uses appropriate strategy based on podcast."""
    
    def __init__(self, timeout: float = 30.0, headless: bool = True):
        """
        Initialize the transcript scraper.
        
        Args:
            timeout: Page load timeout in seconds
            headless: Run browser in headless mode
        """
        self.timeout = timeout * 1000
        self.headless = headless
        self._playwright = None
        self._browser = None
        
        # Initialize strategies
        self.strategies = {
            "sub-club": SubClubTranscriptStrategy(),
            "lennys-podcast": LennysTranscriptStrategy(),
            "20vc": TwentyVCTranscriptStrategy(),
        }
    
    def __enter__(self):
        """Context manager entry - initialize browser."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
    
    async def fetch_transcript(self, episode: Episode, podcast: PodcastConfig) -> Optional[str]:
        """Async wrapper."""
        return self.fetch_transcript_sync(episode, podcast)
    
    def fetch_transcript_sync(self, episode: Episode, podcast: PodcastConfig) -> Optional[str]:
        """
        Fetch transcript using the appropriate strategy for the podcast.
        
        Args:
            episode: Episode to fetch transcript for
            podcast: Podcast configuration
        
        Returns:
            Transcript text if found, None otherwise
        """
        strategy = self.strategies.get(podcast.id)
        if not strategy:
            logger.warning(f"No transcript strategy for podcast: {podcast.id}")
            return None
        
        # Strategies that need browser
        if podcast.id in ["sub-club", "lennys-podcast"]:
            if self._browser is None:
                # Browser not initialized - this shouldn't happen if used as context manager
                # But handle gracefully by initializing temporarily
                logger.warning("Browser not initialized, initializing temporarily")
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=self.headless)
                try:
                    return self._fetch_with_browser(strategy, episode, podcast)
                finally:
                    self._browser.close()
                    self._playwright.stop()
                    self._browser = None
                    self._playwright = None
            else:
                # Browser already initialized
                return self._fetch_with_browser(strategy, episode, podcast)
        else:
            # Strategy doesn't need browser (Whisper)
            return strategy.fetch_transcript(episode, podcast, None)
    
    def _fetch_with_browser(self, strategy, episode, podcast):
        """Fetch transcript with browser."""
        context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            return strategy.fetch_transcript(episode, podcast, page)
        finally:
            page.close()
            context.close()
