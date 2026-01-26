"""
Podcast definitions and RSS feed configurations.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PodcastConfig:
    """Configuration for a single podcast."""
    id: str
    name: str
    rss_url: str
    apple_podcasts_url: Optional[str] = None
    website: Optional[str] = None
    category: Optional[str] = None


# List of podcasts to monitor
PODCASTS: list[PodcastConfig] = [
    PodcastConfig(
        id="lennys-podcast",
        name="Lenny's Podcast",
        rss_url="https://api.substack.com/feed/podcast/10845.rss",
        apple_podcasts_url="https://podcasts.apple.com/us/podcast/lennys-podcast-product-growth-career/id1627920305",
        website="https://www.lennysnewsletter.com/podcast",
        category="Product Management"
    ),
    PodcastConfig(
        id="sub-club",
        name="Sub Club by RevenueCat",
        rss_url="https://feeds.transistor.fm/sub-club",
        apple_podcasts_url="https://podcasts.apple.com/us/podcast/sub-club-by-revenuecat/id1538057974",
        website="https://subclub.com/",
        category="Mobile App Monetization"
    ),
    PodcastConfig(
        id="20vc",
        name="The Twenty Minute VC",
        rss_url="https://thetwentyminutevc.libsyn.com/rss",
        apple_podcasts_url="https://podcasts.apple.com/us/podcast/the-twenty-minute-vc-vc-venture-capital-startup-funding/id958230465",
        website="https://www.thetwentyminutevc.com",
        category="Venture Capital"
    ),
]


def get_podcast_by_id(podcast_id: str) -> Optional[PodcastConfig]:
    """Get a podcast configuration by its ID."""
    for podcast in PODCASTS:
        if podcast.id == podcast_id:
            return podcast
    return None


def get_all_podcasts() -> list[PodcastConfig]:
    """Get all configured podcasts."""
    return PODCASTS
