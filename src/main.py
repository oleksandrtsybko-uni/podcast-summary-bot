"""
Podcast Summary Bot - Main Orchestrator

This is the entry point for the bot. It coordinates all services to:
1. Check RSS feeds for new episodes
2. Fetch transcripts from Apple Podcasts
3. Generate AI summaries using OpenAI
4. Send formatted summaries to Telegram
"""

import sys
import time
from datetime import datetime
from typing import Optional

from .config import get_settings, get_all_podcasts, PodcastConfig
from .services import RSSParser, TranscriptScraper, Summarizer, TelegramService
from .storage import EpisodeTracker
from .models import Episode
from .utils import setup_logger, get_logger

# Initialize logger
logger = get_logger(__name__)


class PodcastSummaryBot:
    """Main bot orchestrator."""
    
    def __init__(self):
        """Initialize all services."""
        logger.info("Initializing Podcast Summary Bot...")
        
        self.settings = get_settings()
        self.podcasts = get_all_podcasts()
        
        # Initialize services
        self.rss_parser = RSSParser()
        # TranscriptScraper will be initialized as context manager in run()
        self.transcript_scraper = None
        self.summarizer = Summarizer()
        self.telegram = TelegramService()
        self.tracker = EpisodeTracker(
            data_file=f"{self.settings.data_dir}/last_episodes.json"
        )
        
        logger.info(f"Bot initialized. Monitoring {len(self.podcasts)} podcasts.")
    
    def run(self) -> int:
        """
        Run the bot - check all podcasts for new episodes.
        
        Returns:
            Number of new episodes processed
        """
        logger.info("=" * 50)
        logger.info("Starting podcast check...")
        logger.info(f"Time: {datetime.utcnow().isoformat()}")
        logger.info("=" * 50)
        
        new_episodes_count = 0
        errors = []
        
        # Initialize transcript scraper with context manager (reuses browser for all episodes)
        with TranscriptScraper() as scraper:
            self.transcript_scraper = scraper
            
            for podcast in self.podcasts:
                try:
                    result = self._process_podcast(podcast)
                    if result:
                        new_episodes_count += 1
                    
                    # Delay between podcasts to be respectful
                    time.sleep(self.settings.request_delay)
                    
                except Exception as e:
                    error_msg = f"Error processing {podcast.name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        # Send error notification if any errors occurred
        if errors:
            self._send_error_notification(errors)
        
        logger.info("=" * 50)
        logger.info(f"Check complete. New episodes: {new_episodes_count}")
        logger.info("=" * 50)
        
        return new_episodes_count
    
    def _process_podcast(self, podcast: PodcastConfig) -> bool:
        """
        Process a single podcast - check for and handle new episodes.
        
        Args:
            podcast: Podcast configuration
        
        Returns:
            True if a new episode was processed, False otherwise
        """
        logger.info(f"\n--- Checking: {podcast.name} ---")
        
        # Fetch latest episode from RSS
        episode = self.rss_parser.fetch_latest_episode(podcast)
        if not episode:
            logger.warning(f"Could not fetch latest episode for {podcast.name}")
            return False
        
        # Check if this is a new episode
        if not self.tracker.is_new_episode(podcast.id, episode.guid):
            logger.info(f"No new episode for {podcast.name}")
            logger.info(f"Last episode: {episode.title}")
            return False
        
        logger.info(f"🆕 New episode found: {episode.title}")
        
        # Process the new episode
        success = self._process_new_episode(episode, podcast)
        
        if success:
            # Update tracker
            self.tracker.update_last_episode(
                podcast_id=podcast.id,
                guid=episode.guid,
                title=episode.title,
                published_date=episode.published_date,
            )
        
        return success
    
    def _process_new_episode(self, episode: Episode, podcast: PodcastConfig) -> bool:
        """
        Process a new episode - fetch transcript, summarize, and send.
        
        Args:
            episode: New episode to process
            podcast: Parent podcast config
        
        Returns:
            True if successfully processed
        """
        try:
            # Try to fetch transcript
            logger.info("Fetching transcript...")
            transcript = self.transcript_scraper.fetch_transcript_sync(episode, podcast)
            
            if transcript:
                episode.transcript = transcript
                logger.info(f"Got transcript ({len(transcript)} chars)")
            else:
                logger.warning("Could not fetch transcript")
                episode.transcript = "Transcript not found"
            
            # Generate summary
            logger.info("Generating AI summary...")
            summary = self.summarizer.generate_summary(episode, podcast.name)
            episode.summary = summary
            logger.info(f"Generated summary ({len(summary)} chars)")
            
            # Send to Telegram
            logger.info("Sending to Telegram...")
            success = self.telegram.send_episode_summary_sync(episode, podcast.name)
            
            if success:
                logger.info("✅ Successfully sent summary to Telegram")
            else:
                logger.error("❌ Failed to send to Telegram")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing episode: {e}")
            return False
    
    def _send_error_notification(self, errors: list[str]) -> None:
        """Send error notification to Telegram."""
        try:
            error_message = "\n".join(errors)
            self.telegram.send_error_notification_sync(error_message)
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
    
    def test_telegram(self) -> bool:
        """Test Telegram connection."""
        return self.telegram.send_test_message()
    
    def force_process_podcast(self, podcast_id: str) -> bool:
        """
        Force process a specific podcast (ignore tracker).
        Useful for testing.
        
        Args:
            podcast_id: ID of podcast to process
        
        Returns:
            True if successful
        """
        from .config import get_podcast_by_id
        
        podcast = get_podcast_by_id(podcast_id)
        if not podcast:
            logger.error(f"Podcast not found: {podcast_id}")
            return False
        
        episode = self.rss_parser.fetch_latest_episode(podcast)
        if not episode:
            return False
        
        # Initialize transcript scraper if not already done
        if self.transcript_scraper is None:
            self.transcript_scraper = TranscriptScraper()
            with self.transcript_scraper:
                return self._process_new_episode(episode, podcast)
        else:
            return self._process_new_episode(episode, podcast)


def main():
    """Main entry point."""
    # Set up logging based on environment
    import os
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(level=log_level)
    
    logger.info("Podcast Summary Bot starting...")
    
    try:
        bot = PodcastSummaryBot()
        
        # Check for command line arguments
        if len(sys.argv) > 1:
            command = sys.argv[1]
            
            if command == "test":
                # Test Telegram connection
                logger.info("Testing Telegram connection...")
                if bot.test_telegram():
                    logger.info("✅ Telegram test successful!")
                    return 0
                else:
                    logger.error("❌ Telegram test failed!")
                    return 1
            
            elif command == "force":
                # Force process a specific podcast
                if len(sys.argv) > 2:
                    podcast_id = sys.argv[2]
                    logger.info(f"Force processing podcast: {podcast_id}")
                    if bot.force_process_podcast(podcast_id):
                        return 0
                    return 1
                else:
                    logger.error("Usage: python -m src.main force <podcast_id>")
                    return 1
            
            else:
                logger.error(f"Unknown command: {command}")
                logger.info("Available commands: test, force <podcast_id>")
                return 1
        
        # Normal run - check all podcasts
        new_count = bot.run()
        logger.info(f"Processed {new_count} new episodes")
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
