"""
Episode tracking storage - tracks last processed episodes per podcast.
Uses a simple JSON file for persistence.

Note: The 'guid' field is used as a unique identifier for episodes.
- For RSS-sourced episodes: this is the episode GUID from the RSS feed
- For Dropbox-sourced episodes (Lenny's): this is the filename from Dropbox
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from ..models.episode import TrackedEpisode
from ..utils.logger import get_logger

logger = get_logger(__name__)


class EpisodeTracker:
    """
    Tracks the last processed episode for each podcast.
    Stores data in a JSON file.
    """
    
    def __init__(self, data_file: str = "data/last_episodes.json"):
        """
        Initialize the tracker.
        
        Args:
            data_file: Path to the JSON file for storing episode data
        """
        self.data_file = Path(data_file)
        self._data: dict[str, dict] = {}
        self._load()
    
    def _load(self) -> None:
        """Load tracked episodes from file."""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Loaded {len(self._data)} tracked podcasts from {self.data_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load tracker data: {e}. Starting fresh.")
                self._data = {}
        else:
            logger.info(f"No existing tracker file at {self.data_file}. Starting fresh.")
            self._data = {}
    
    def _save(self) -> None:
        """Save tracked episodes to file."""
        # Ensure directory exists
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
            logger.debug(f"Saved tracker data to {self.data_file}")
        except IOError as e:
            logger.error(f"Failed to save tracker data: {e}")
            raise
    
    def get_last_episode(self, podcast_id: str) -> Optional[TrackedEpisode]:
        """
        Get the last tracked episode for a podcast.
        
        Args:
            podcast_id: Unique identifier for the podcast
        
        Returns:
            TrackedEpisode if found, None otherwise
        """
        if podcast_id not in self._data:
            return None
        
        try:
            data = self._data[podcast_id]
            return TrackedEpisode(
                guid=data["guid"],
                title=data["title"],
                published_date=datetime.fromisoformat(data["published_date"]) if data.get("published_date") else None,
                processed_at=datetime.fromisoformat(data["processed_at"]) if data.get("processed_at") else datetime.utcnow()
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid tracker data for {podcast_id}: {e}")
            return None
    
    def update_last_episode(
        self,
        podcast_id: str,
        guid: str,
        title: str,
        published_date: Optional[datetime] = None
    ) -> None:
        """
        Update the last tracked episode for a podcast.
        
        Args:
            podcast_id: Unique identifier for the podcast
            guid: Episode identifier (RSS GUID or Dropbox filename for Lenny's)
            title: Episode title
            published_date: Episode publication date
        """
        self._data[podcast_id] = {
            "guid": guid,
            "title": title,
            "published_date": published_date.isoformat() if published_date else None,
            "processed_at": datetime.utcnow().isoformat()
        }
        self._save()
        logger.info(f"Updated tracker for {podcast_id}: {title}")
    
    def is_new_episode(self, podcast_id: str, guid: str) -> bool:
        """
        Check if an episode is new (not yet processed).
        
        Args:
            podcast_id: Unique identifier for the podcast
            guid: Episode GUID to check
        
        Returns:
            True if this is a new episode, False otherwise
        """
        last = self.get_last_episode(podcast_id)
        if last is None:
            return True
        return last.guid != guid
    
    def get_all_tracked(self) -> dict[str, TrackedEpisode]:
        """
        Get all tracked episodes.
        
        Returns:
            Dictionary mapping podcast_id to TrackedEpisode
        """
        result = {}
        for podcast_id in self._data:
            episode = self.get_last_episode(podcast_id)
            if episode:
                result[podcast_id] = episode
        return result
    
    def clear(self, podcast_id: Optional[str] = None) -> None:
        """
        Clear tracked episodes.
        
        Args:
            podcast_id: If provided, clear only this podcast. Otherwise clear all.
        """
        if podcast_id:
            if podcast_id in self._data:
                del self._data[podcast_id]
                logger.info(f"Cleared tracker for {podcast_id}")
        else:
            self._data = {}
            logger.info("Cleared all tracker data")
        self._save()
