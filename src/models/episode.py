"""
Episode data models.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Guest(BaseModel):
    """Guest information extracted from episode."""
    name: str
    description: Optional[str] = None
    linkedin_url: Optional[str] = None


class Episode(BaseModel):
    """Podcast episode data model."""
    
    # Identifiers
    guid: str = Field(..., description="Unique episode identifier from RSS")
    podcast_id: str = Field(..., description="Parent podcast ID")
    
    # Basic Info
    title: str = Field(..., description="Episode title")
    description: str = Field(default="", description="Episode description/show notes")
    published_date: Optional[datetime] = Field(None, description="Publication date")
    
    # URLs
    episode_url: Optional[str] = Field(None, description="Link to episode page")
    audio_url: Optional[str] = Field(None, description="Direct audio file URL")
    apple_podcasts_url: Optional[str] = Field(None, description="Apple Podcasts episode URL")
    
    # Extracted Content
    guests: list[Guest] = Field(default_factory=list, description="Episode guests")
    transcript: Optional[str] = Field(None, description="Episode transcript")
    
    # Generated Content
    summary: Optional[str] = Field(None, description="AI-generated summary")
    
    # Metadata
    duration: Optional[str] = Field(None, description="Episode duration")
    
    def has_transcript(self) -> bool:
        """Check if transcript is available."""
        return self.transcript is not None and len(self.transcript.strip()) > 100
    
    def has_summary(self) -> bool:
        """Check if summary has been generated."""
        return self.summary is not None and len(self.summary.strip()) > 0
    
    def get_guest_names(self) -> list[str]:
        """Get list of guest names."""
        return [guest.name for guest in self.guests]
    
    def get_guests_formatted(self) -> str:
        """Get formatted guest string for display."""
        if not self.guests:
            return "No guests listed"
        
        parts = []
        for guest in self.guests:
            if guest.linkedin_url:
                parts.append(f"[{guest.name}]({guest.linkedin_url})")
            elif guest.description:
                parts.append(f"{guest.name} ({guest.description})")
            else:
                parts.append(guest.name)
        
        return ", ".join(parts)


class TrackedEpisode(BaseModel):
    """Minimal episode data for tracking last processed episodes."""
    guid: str
    title: str
    published_date: Optional[datetime] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
