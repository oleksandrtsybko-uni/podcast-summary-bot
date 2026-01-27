"""
RSS feed parser service.
Fetches and parses podcast RSS feeds to extract episode information.
Also supports Apple Podcasts scraping as an alternative to RSS.
"""

import re
import feedparser
import httpx
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from email.utils import parsedate_to_datetime

from ..config.podcasts import PodcastConfig
from ..models.episode import Episode, Guest
from ..utils.logger import get_logger
from ..utils.helpers import clean_html, extract_linkedin_urls, extract_guest_names_from_title

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from .transcript import LennysTranscriptStrategy, DropboxEpisodeResult

logger = get_logger(__name__)

# Browser-like headers to avoid being blocked by Substack and other services
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


class RSSParser:
    """Parses RSS feeds to extract podcast episode data."""
    
    def __init__(self):
        """Initialize the RSS parser."""
        self._cached_feed = None  # For feedparser direct fetch fallback
    
    def fetch_latest_episode(self, podcast: PodcastConfig) -> Optional[Episode]:
        """
        Fetch the latest episode from a podcast's RSS feed.
        
        Args:
            podcast: Podcast configuration
        
        Returns:
            Episode object if successful, None otherwise
        """
        self._cached_feed = None  # Reset cached feed
        
        try:
            logger.info(f"Fetching RSS feed for {podcast.name}: {podcast.rss_url}")
            
            # Fetch RSS content with httpx for better encoding handling
            feed_content = self._fetch_rss_content(podcast.rss_url)
            if not feed_content:
                logger.error(f"Could not fetch RSS content for {podcast.name}")
                return None
            
            # Check if we should use cached feed from feedparser direct method
            if feed_content == "__FEEDPARSER_DIRECT__" and self._cached_feed:
                feed = self._cached_feed
                logger.info(f"Using feedparser direct fetch for {podcast.name}")
            else:
                # Parse the fetched content
                feed = feedparser.parse(feed_content)
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"RSS parsing warning for {podcast.name}: {feed.bozo_exception}")
            
            if not feed.entries:
                logger.warning(f"No entries found in RSS feed for {podcast.name}")
                return None
            
            # Get the first (latest) entry
            entry = feed.entries[0]
            
            # Parse the episode
            episode = self._parse_entry(entry, podcast)
            
            logger.info(f"Fetched latest episode: {episode.title}")
            return episode
            
        except Exception as e:
            logger.error(f"Error fetching RSS feed for {podcast.name}: {e}")
            return None
    
    def _fetch_rss_content(self, url: str) -> Optional[str]:
        """
        Fetch RSS content with explicit encoding handling.
        Uses multiple methods to handle different RSS sources.
        
        Args:
            url: RSS feed URL
        
        Returns:
            RSS content as string, or None if failed
        """
        # Method 1: Try with httpx and browser headers
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url, headers=BROWSER_HEADERS)
                response.raise_for_status()
                
                # Try to decode with UTF-8, falling back to latin-1
                try:
                    content = response.content.decode('utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"UTF-8 decode failed, trying latin-1 for {url}")
                    content = response.content.decode('latin-1')
                
                return self._clean_rss_content(content)
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(f"Got 403 from {url}, trying feedparser direct method")
                # Method 2: Try feedparser's built-in fetching (uses different user-agent handling)
                return self._fetch_with_feedparser(url)
            logger.error(f"HTTP error fetching RSS from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching RSS content from {url}: {e}")
            # Try fallback method
            return self._fetch_with_feedparser(url)
    
    def _fetch_with_feedparser(self, url: str) -> Optional[str]:
        """
        Fallback method using feedparser's built-in URL handling.
        Returns the raw feed object which can be passed to parse().
        """
        try:
            # feedparser can fetch directly with custom agent
            feed = feedparser.parse(
                url, 
                agent="Mozilla/5.0 (compatible; PodcastBot/1.0; +https://github.com)"
            )
            
            if feed.bozo and not feed.entries:
                logger.error(f"Feedparser failed for {url}: {feed.bozo_exception}")
                return None
            
            # Return a marker that indicates we should use the feed object directly
            # Store the feed in a class variable for later use
            self._cached_feed = feed
            return "__FEEDPARSER_DIRECT__"
            
        except Exception as e:
            logger.error(f"Feedparser direct fetch failed for {url}: {e}")
            return None
    
    def _clean_rss_content(self, content: str) -> str:
        """Clean RSS content by replacing problematic characters."""
        # Replace problematic characters that can cause XML parsing issues
        replacements = {
            '\u2014': '-',  # em dash
            '\u2013': '-',  # en dash
            '\u2018': "'",  # left single quote
            '\u2019': "'",  # right single quote
            '\u201c': '"',  # left double quote
            '\u201d': '"',  # right double quote
            '\u2026': '...',  # ellipsis
        }
        for old, new in replacements.items():
            content = content.replace(old, new)
        return content
    
    def fetch_recent_episodes(self, podcast: PodcastConfig, count: int = 5) -> list[Episode]:
        """
        Fetch recent episodes from a podcast's RSS feed.
        
        Args:
            podcast: Podcast configuration
            count: Number of episodes to fetch
        
        Returns:
            List of Episode objects
        """
        self._cached_feed = None  # Reset cached feed
        
        try:
            logger.info(f"Fetching RSS feed for {podcast.name}")
            
            # Fetch RSS content with httpx for better encoding handling
            feed_content = self._fetch_rss_content(podcast.rss_url)
            if not feed_content:
                logger.error(f"Could not fetch RSS content for {podcast.name}")
                return []
            
            # Check if we should use cached feed from feedparser direct method
            if feed_content == "__FEEDPARSER_DIRECT__" and self._cached_feed:
                feed = self._cached_feed
            else:
                feed = feedparser.parse(feed_content)
            
            if not feed.entries:
                logger.warning(f"No entries found in RSS feed for {podcast.name}")
                return []
            
            episodes = []
            for entry in feed.entries[:count]:
                episode = self._parse_entry(entry, podcast)
                episodes.append(episode)
            
            logger.info(f"Fetched {len(episodes)} episodes from {podcast.name}")
            return episodes
            
        except Exception as e:
            logger.error(f"Error fetching RSS feed for {podcast.name}: {e}")
            return []
    
    def _parse_entry(self, entry: dict, podcast: PodcastConfig) -> Episode:
        """
        Parse a single RSS entry into an Episode.
        
        Args:
            entry: feedparser entry dict
            podcast: Parent podcast configuration
        
        Returns:
            Parsed Episode object
        """
        # Extract GUID
        guid = entry.get("id") or entry.get("guid") or entry.get("link", "")
        
        # Extract title
        title = entry.get("title", "Untitled Episode")
        
        # Extract description
        description = ""
        if "content" in entry and entry.content:
            description = entry.content[0].get("value", "")
        elif "summary" in entry:
            description = entry.get("summary", "")
        elif "description" in entry:
            description = entry.get("description", "")
        
        # Clean HTML from description for text extraction
        clean_description = clean_html(description)
        
        # Extract publication date
        published_date = None
        if "published_parsed" in entry and entry.published_parsed:
            try:
                published_date = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass
        elif "published" in entry:
            try:
                published_date = parsedate_to_datetime(entry.published)
            except (TypeError, ValueError):
                pass
        
        # Extract URLs
        episode_url = entry.get("link")
        
        # Extract audio URL from enclosures
        audio_url = None
        if "enclosures" in entry:
            for enclosure in entry.enclosures:
                if enclosure.get("type", "").startswith("audio/"):
                    audio_url = enclosure.get("href") or enclosure.get("url")
                    break
        
        # Extract duration
        duration = entry.get("itunes_duration")
        
        # Extract guests
        guests = self._extract_guests(title, description, clean_description)
        
        # Build Apple Podcasts URL if we have the base
        apple_podcasts_url = None
        if podcast.apple_podcasts_url:
            # For now, just use the show URL - episode-specific URLs require more parsing
            apple_podcasts_url = podcast.apple_podcasts_url
        
        return Episode(
            guid=guid,
            podcast_id=podcast.id,
            title=title,
            description=description,  # Keep HTML for potential transcript extraction
            published_date=published_date,
            episode_url=episode_url,
            audio_url=audio_url,
            apple_podcasts_url=apple_podcasts_url,
            guests=guests,
            duration=duration,
        )
    
    def _extract_guests(self, title: str, description: str, clean_description: str) -> list[Guest]:
        """
        Extract guest information from episode title and description.
        
        Args:
            title: Episode title
            description: Raw HTML description
            clean_description: Cleaned text description
        
        Returns:
            List of Guest objects
        """
        guests = []
        
        # Extract guest names from title
        names_from_title = extract_guest_names_from_title(title)
        
        # Extract LinkedIn URLs from description
        linkedin_urls = extract_linkedin_urls(description)
        
        # Try to match names with LinkedIn URLs
        for name in names_from_title:
            guest = Guest(name=name)
            
            # Try to find matching LinkedIn URL
            name_parts = name.lower().split()
            for url in linkedin_urls:
                url_lower = url.lower()
                # Check if any part of the name appears in the URL
                if any(part in url_lower for part in name_parts if len(part) > 2):
                    guest.linkedin_url = url
                    break
            
            # Try to extract a brief description
            guest.description = self._extract_guest_description(name, clean_description)
            
            guests.append(guest)
        
        # If no guests found from title, but we have LinkedIn URLs, try to extract names from URLs
        if not guests and linkedin_urls:
            for url in linkedin_urls:
                name = self._extract_name_from_linkedin_url(url)
                if name:
                    guests.append(Guest(name=name, linkedin_url=url))
        
        return guests
    
    def _extract_guest_description(self, name: str, description: str) -> Optional[str]:
        """
        Try to extract a brief description of the guest from episode description.
        
        Args:
            name: Guest name
            description: Clean episode description
        
        Returns:
            Brief description or None
        """
        if not description or not name:
            return None
        
        # Common patterns: "Name is a/the..." or "Name, title/role at Company"
        patterns = [
            rf'{re.escape(name)}\s+is\s+(?:a\s+|the\s+)?([^.]+)',
            rf'{re.escape(name)},\s+([^.]+?)(?:\.|,|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                desc = match.group(1).strip()
                # Limit length
                if len(desc) < 150:
                    return desc
        
        return None
    
    def _extract_name_from_linkedin_url(self, url: str) -> Optional[str]:
        """
        Try to extract a name from a LinkedIn profile URL.
        
        Args:
            url: LinkedIn URL like linkedin.com/in/firstname-lastname
        
        Returns:
            Formatted name or None
        """
        match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', url, re.IGNORECASE)
        if match:
            slug = match.group(1)
            # Remove numbers and convert to title case
            name_parts = re.sub(r'\d+', '', slug).split('-')
            name = ' '.join(part.capitalize() for part in name_parts if part)
            if name:
                return name
        return None
    
    def fetch_latest_episode_from_apple(
        self, 
        podcast: PodcastConfig, 
        browser: "Page"
    ) -> Optional[Episode]:
        """
        Fetch the latest episode by scraping Apple Podcasts page.
        Used as alternative to RSS when RSS is blocked.
        
        Args:
            podcast: Podcast configuration (must have apple_podcasts_url)
            browser: Playwright Page instance
        
        Returns:
            Episode object if successful, None otherwise
        """
        if not podcast.apple_podcasts_url:
            logger.error(f"No Apple Podcasts URL configured for {podcast.name}")
            return None
        
        try:
            logger.info(f"Fetching latest episode from Apple Podcasts for {podcast.name}")
            logger.info(f"URL: {podcast.apple_podcasts_url}")
            
            # Navigate to Apple Podcasts show page
            browser.goto(podcast.apple_podcasts_url, wait_until="networkidle", timeout=30000)
            browser.wait_for_timeout(3000)  # Wait for dynamic content
            
            # Find the first episode in the list
            # Apple Podcasts uses a list structure for episodes
            episode_data = self._extract_apple_episode_data(browser, podcast)
            
            if episode_data:
                logger.info(f"Fetched latest episode from Apple: {episode_data.title}")
                return episode_data
            else:
                logger.warning(f"Could not extract episode data from Apple Podcasts for {podcast.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching from Apple Podcasts for {podcast.name}: {e}")
            return None
    
    def _extract_apple_episode_data(
        self, 
        page: "Page", 
        podcast: PodcastConfig
    ) -> Optional[Episode]:
        """
        Extract episode data from Apple Podcasts page.
        
        Args:
            page: Playwright Page with Apple Podcasts loaded
            podcast: Podcast configuration
        
        Returns:
            Episode object or None
        """
        try:
            # Try to find episode elements
            # Apple Podcasts structure: episodes are in a list, each with title, date, description
            
            # Method 1: Look for episode list items with links
            episode_links = page.locator('a[href*="?i="]').all()
            
            if not episode_links:
                # Method 2: Try finding by role/structure
                episode_links = page.locator('[data-testid="episode-link"], .episode-link, li a[href*="podcast"]').all()
            
            if not episode_links:
                logger.warning("No episode links found on Apple Podcasts page")
                # Try to extract from page structure
                return self._extract_episode_from_page_text(page, podcast)
            
            # Get the first episode (most recent)
            first_episode = episode_links[0]
            
            # Extract title
            title = first_episode.text_content()
            if not title:
                title = first_episode.get_attribute('aria-label') or "Unknown Episode"
            title = title.strip()
            
            # Extract episode URL
            episode_url = first_episode.get_attribute('href')
            if episode_url and not episode_url.startswith('http'):
                episode_url = f"https://podcasts.apple.com{episode_url}"
            
            # Create a unique GUID from the URL or title
            guid = episode_url if episode_url else f"apple-{hash(title)}"
            
            # Try to get more details by navigating to episode page
            description = ""
            published_date = None
            
            if episode_url:
                try:
                    page.goto(episode_url, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    # Extract description
                    desc_elem = page.locator('[data-testid="description"], .episode-description, .product-hero-desc p').first
                    if desc_elem.count() > 0:
                        description = desc_elem.text_content() or ""
                    
                    # Extract date
                    date_elem = page.locator('time, [datetime], .episode-date').first
                    if date_elem.count() > 0:
                        date_str = date_elem.get_attribute('datetime') or date_elem.text_content()
                        if date_str:
                            published_date = self._parse_apple_date(date_str)
                except Exception as e:
                    logger.debug(f"Could not get episode details: {e}")
            
            # Extract guests from title
            guests = self._extract_guests(title, description, clean_html(description) if description else "")
            
            return Episode(
                guid=guid,
                podcast_id=podcast.id,
                title=title,
                description=description,
                published_date=published_date,
                episode_url=episode_url,
                audio_url=None,  # Not available from Apple Podcasts scraping
                apple_podcasts_url=episode_url or podcast.apple_podcasts_url,
                guests=guests,
                duration=None,
            )
            
        except Exception as e:
            logger.error(f"Error extracting Apple episode data: {e}")
            return None
    
    def _extract_episode_from_page_text(
        self, 
        page: "Page", 
        podcast: PodcastConfig
    ) -> Optional[Episode]:
        """
        Fallback: Extract episode info from page text content.
        """
        try:
            # Get all text from the page and try to find episode info
            page_text = page.locator('main, #main, .main-content').first.text_content()
            if not page_text:
                page_text = page.locator('body').text_content()
            
            if not page_text:
                return None
            
            # Look for patterns that indicate episode titles
            # Lenny's episodes usually have format: "Title | Guest Name (Company)"
            lines = page_text.split('\n')
            
            for line in lines:
                line = line.strip()
                # Skip short lines or navigation text
                if len(line) < 20 or len(line) > 300:
                    continue
                # Skip lines that look like navigation
                if any(x in line.lower() for x in ['listen on', 'subscribe', 'see all', 'episodes']):
                    continue
                # Look for episode-like patterns (contains | or guest pattern)
                if '|' in line or re.search(r'\([^)]+\)$', line):
                    # This might be an episode title
                    title = line
                    guests = self._extract_guests(title, "", "")
                    
                    return Episode(
                        guid=f"apple-{hash(title)}",
                        podcast_id=podcast.id,
                        title=title,
                        description="",
                        published_date=None,
                        episode_url=podcast.apple_podcasts_url,
                        audio_url=None,
                        apple_podcasts_url=podcast.apple_podcasts_url,
                        guests=guests,
                        duration=None,
                    )
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting from page text: {e}")
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
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def fetch_latest_episode_from_dropbox(
        self,
        podcast: PodcastConfig,
        transcript_strategy: "LennysTranscriptStrategy",
        browser: "Page"
    ) -> Optional["DropboxEpisodeResult"]:
        """
        Fetch the latest episode by checking Dropbox archive.
        Returns both episode info and transcript in one step.
        
        This is used for Lenny's Podcast where RSS is blocked and 
        transcripts come from Dropbox anyway.
        
        Args:
            podcast: Podcast configuration
            transcript_strategy: LennysTranscriptStrategy instance
            browser: Playwright Page instance
        
        Returns:
            DropboxEpisodeResult with episode, transcript, and filename if found
        """
        try:
            logger.info(f"Fetching latest episode from Dropbox for {podcast.name}")
            
            # Delegate to the transcript strategy's detection method
            result = transcript_strategy.detect_and_fetch_latest(podcast, browser)
            
            if result:
                logger.info(f"Detected latest episode from Dropbox: {result.episode.title}")
                return result
            else:
                logger.warning(f"Could not detect latest episode from Dropbox for {podcast.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching from Dropbox for {podcast.name}: {e}")
            return None
