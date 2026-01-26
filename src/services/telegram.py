"""
Telegram bot service for sending podcast summaries.
Uses direct HTTP requests to avoid async event loop issues.
"""

import time
from typing import Optional
from datetime import datetime
import requests

from ..models.episode import Episode
from ..config.settings import get_settings
from ..utils.logger import get_logger
from ..utils.helpers import split_message, format_date

logger = get_logger(__name__)

# Telegram API base URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"

# Telegram message character limit
MAX_MESSAGE_LENGTH = 4096

# Message template for episode summaries (HTML format)
MESSAGE_TEMPLATE = """🎙️ <b>NEW EPISODE ALERT</b>

📺 <b>Show:</b> {show_name}
📌 <b>Episode:</b> {episode_title}
📅 <b>Published:</b> {published_date}
👤 <b>Guest(s):</b> {guests}

📝 <b>SUMMARY</b>

{summary}

🔗 <a href="{episode_url}">Listen to Episode</a>
"""

# Error notification template (HTML format)
ERROR_TEMPLATE = """⚠️ <b>Podcast Bot Error</b>

An error occurred while processing podcasts:

<pre>{error_message}</pre>

Time: {timestamp}
"""


class TelegramService:
    """Service for sending messages via Telegram bot using direct HTTP requests."""
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        """
        Initialize the Telegram service.
        
        Args:
            bot_token: Telegram bot token (uses settings if not provided)
            chat_id: Target chat/channel ID (uses settings if not provided)
        """
        settings = get_settings()
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.api_base = TELEGRAM_API_BASE.format(token=self.bot_token)
        
        logger.info(f"Initialized Telegram service for chat: {self.chat_id}")
    
    def _make_request(self, method: str, data: dict) -> dict:
        """
        Make a request to Telegram API.
        
        Args:
            method: API method name (e.g., 'sendMessage')
            data: Request payload
        
        Returns:
            API response as dict
        
        Raises:
            Exception: If request fails
        """
        url = f"{self.api_base}/{method}"
        
        try:
            response = requests.post(url, json=data, timeout=30)
            result = response.json()
            
            if not result.get("ok"):
                error_desc = result.get("description", "Unknown error")
                raise Exception(f"Telegram API error: {error_desc}")
            
            return result
        except requests.RequestException as e:
            raise Exception(f"HTTP request failed: {e}")
    
    def send_episode_summary_sync(
        self,
        episode: Episode,
        show_name: str,
    ) -> bool:
        """
        Send an episode summary to Telegram.
        
        Args:
            episode: Episode with summary
            show_name: Name of the podcast
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Format the message
            message = self._format_episode_message(episode, show_name)
            
            # Send (split if necessary)
            self._send_message(message)
            
            logger.info(f"Sent summary for: {episode.title}")
            return True
            
        except Exception as e:
            logger.error(f"Telegram error sending summary: {e}")
            return False
    
    def send_error_notification_sync(self, error_message: str) -> bool:
        """
        Send an error notification to Telegram.
        
        Args:
            error_message: Error details
        
        Returns:
            True if sent successfully
        """
        try:
            message = ERROR_TEMPLATE.format(
                error_message=self._escape_html(error_message[:1000]),
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            
            self._send_message(message)
            logger.info("Sent error notification")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """
        Send a test message to verify bot setup.
        
        Returns:
            True if successful
        """
        try:
            self._make_request("sendMessage", {
                "chat_id": self.chat_id,
                "text": "✅ Podcast Summary Bot is working!",
            })
            logger.info("Test message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Test message failed: {e}")
            return False
    
    def _format_episode_message(self, episode: Episode, show_name: str) -> str:
        """
        Format episode data into a Telegram message.
        
        Args:
            episode: Episode to format
            show_name: Podcast name
        
        Returns:
            Formatted message string
        """
        # Format guests
        guests = self._format_guests_for_telegram(episode)
        
        # Get episode URL
        episode_url = episode.episode_url or episode.apple_podcasts_url or "#"
        
        # Format published date
        published = format_date(episode.published_date)
        
        # Escape HTML special characters
        summary = self._escape_html(episode.summary or "Summary not available")
        episode_title = self._escape_html(episode.title)
        show_name_escaped = self._escape_html(show_name)
        
        message = MESSAGE_TEMPLATE.format(
            show_name=show_name_escaped,
            episode_title=episode_title,
            published_date=published,
            guests=guests,
            summary=summary,
            episode_url=episode_url,
        )
        
        return message
    
    def _format_guests_for_telegram(self, episode: Episode) -> str:
        """
        Format guest information for Telegram (with links).
        
        Args:
            episode: Episode with guests
        
        Returns:
            Formatted guest string
        """
        if not episode.guests:
            return "Not specified"
        
        parts = []
        for guest in episode.guests:
            name = self._escape_html(guest.name)
            if guest.linkedin_url:
                parts.append(f'<a href="{guest.linkedin_url}">{name}</a>')
            elif guest.description:
                desc = self._escape_html(guest.description[:50])
                parts.append(f"{name} ({desc})")
            else:
                parts.append(name)
        
        return ", ".join(parts)
    
    def _escape_html(self, text: str) -> str:
        """
        Escape special characters for HTML.
        
        Args:
            text: Text to escape
        
        Returns:
            Escaped text
        """
        if not text:
            return ""
        
        # HTML special characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        return text
    
    def _send_message(self, message: str) -> None:
        """
        Send a message, splitting if necessary.
        
        Args:
            message: Message to send
        """
        # Split message if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            chunks = split_message(message, MAX_MESSAGE_LENGTH - 100)
            logger.info(f"Message too long, splitting into {len(chunks)} parts")
            
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    chunk = f"<b>[Part {i+1}/{len(chunks)}]</b>\n\n{chunk}"
                
                self._make_request("sendMessage", {
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
                
                if i < len(chunks) - 1:
                    time.sleep(0.5)
        else:
            self._make_request("sendMessage", {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
    
    # Async methods kept for compatibility but just call sync versions
    async def send_episode_summary(self, episode: Episode, show_name: str) -> bool:
        """Async wrapper - calls sync method."""
        return self.send_episode_summary_sync(episode, show_name)
    
    async def send_error_notification(self, error_message: str) -> bool:
        """Async wrapper - calls sync method."""
        return self.send_error_notification_sync(error_message)
