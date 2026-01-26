"""
Utility helper functions.
"""

import re
import html
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse, parse_qs


def clean_html(text: str) -> str:
    """
    Remove HTML tags and decode HTML entities from text.
    
    Args:
        text: Text potentially containing HTML
    
    Returns:
        Cleaned plain text
    """
    if not text:
        return ""
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_linkedin_urls(text: str) -> list[str]:
    """
    Extract LinkedIn profile URLs from text.
    
    Args:
        text: Text to search for LinkedIn URLs
    
    Returns:
        List of LinkedIn URLs found
    """
    if not text:
        return []
    
    # Pattern for LinkedIn profile URLs
    pattern = r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?'
    
    urls = re.findall(pattern, text, re.IGNORECASE)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        normalized = url.rstrip('/').lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)
    
    return unique_urls


def extract_guest_names_from_title(title: str) -> list[str]:
    """
    Extract guest names from episode title.
    
    Common patterns:
    - "Guest Name | Topic"
    - "Topic with Guest Name"
    - "Guest Name: Topic"
    - "Topic feat. Guest Name"
    
    Args:
        title: Episode title
    
    Returns:
        List of potential guest names
    """
    if not title:
        return []
    
    names = []
    
    # Pattern: "Name | Topic" or "Topic | Name"
    if '|' in title:
        parts = [p.strip() for p in title.split('|')]
        # First part is often the guest name
        if parts and not any(kw in parts[0].lower() for kw in ['how', 'what', 'why', 'the', 'episode']):
            names.append(parts[0])
    
    # Pattern: "with Guest Name" or "featuring Guest Name"
    with_pattern = r'(?:with|featuring|feat\.?|ft\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
    matches = re.findall(with_pattern, title, re.IGNORECASE)
    names.extend(matches)
    
    # Pattern: "Guest Name:" at start
    colon_pattern = r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):'
    match = re.match(colon_pattern, title)
    if match:
        names.append(match.group(1))
    
    # Clean up and deduplicate
    cleaned_names = []
    seen = set()
    for name in names:
        name = name.strip()
        if name.lower() not in seen and len(name) > 2:
            seen.add(name.lower())
            cleaned_names.append(name)
    
    return cleaned_names


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to maximum length, adding suffix if truncated.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)].rsplit(' ', 1)[0] + suffix


def parse_duration(duration_str: Optional[str]) -> Optional[int]:
    """
    Parse duration string to seconds.
    
    Args:
        duration_str: Duration in format "HH:MM:SS" or "MM:SS"
    
    Returns:
        Duration in seconds, or None if parsing fails
    """
    if not duration_str:
        return None
    
    try:
        parts = duration_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return int(parts[0])
    except (ValueError, IndexError):
        return None


def format_date(dt: Optional[datetime], format_str: str = "%B %d, %Y") -> str:
    """
    Format datetime for display.
    
    Args:
        dt: Datetime to format
        format_str: strftime format string
    
    Returns:
        Formatted date string or "Unknown date"
    """
    if dt is None:
        return "Unknown date"
    return dt.strftime(format_str)


def split_message(text: str, max_length: int = 4096) -> list[str]:
    """
    Split a long message into chunks that fit within max_length.
    Tries to split at paragraph boundaries.
    
    Args:
        text: Text to split
        max_length: Maximum length per chunk
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph exceeds limit
        if len(current_chunk) + len(paragraph) + 2 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # If single paragraph is too long, split by sentences
            if len(paragraph) > max_length:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        current_chunk += " " + sentence if current_chunk else sentence
            else:
                current_chunk = paragraph
        else:
            current_chunk += "\n\n" + paragraph if current_chunk else paragraph
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks
