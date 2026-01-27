"""
AI summarization service using OpenAI GPT-4.
Generates structured summaries from podcast transcripts.
"""

from typing import Optional
from openai import OpenAI

from ..models.episode import Episode
from ..config.settings import get_settings
from ..utils.logger import get_logger
from ..utils.helpers import clean_html, truncate_text

logger = get_logger(__name__)

# Maximum context length for transcript (to manage token usage)
MAX_TRANSCRIPT_LENGTH = 150000  # ~37k tokens approximately (GPT-4o supports 128k context)

# Summary prompt template
SUMMARY_PROMPT = """You are an expert podcast analyst. Create a structured, bullet-point summary of the transcript below.

Hard rules:
- Use ONLY information explicitly stated in the transcript. Do not add assumptions, background, or advice not present in the text.
- If a detail is uncertain or implied but not said, mark it as "unclear" instead of guessing.
- Keep it informational and specific (facts, claims, examples, numbers, definitions, decisions, tradeoffs). Avoid generic advice. Prefer concrete details, examples, and constraints.
- No narrative article style. No long paragraphs.

Output format (use this exact structure):

1) Key blocks (grouped by storyline)
For each block:
- Headline takeaway (must read like a point, not a topic)
  - What they said (2–4 bullets)
  - Context: what problem/constraint led to this (1–2 bullets)
  - Example(s) / specifics: (numbers, experiments, product flows, tool names, partners, etc.) (1–4 bullets)
  - Tradeoffs / caveats / disagreements mentioned (0–3 bullets)
  - "So what": implication stated or clearly explained in the transcript (1–2 bullets)

IMPORTANT: Your block headline should summarize the story of that section.
Examples:
- "Ads were introduced without hurting UX by controlling quality via direct partners"
- "The first IAP experiment was streak repair; expansion came later"


2) Actionable takeaways mentioned
- What they recommend doing:
  - Context (when/why)
  - Expected outcome / metric (if mentioned)
- What they recommend avoiding:
  - Context

3) Experiments / AB tests / tactics described
- Experiment/tactic:
  - Trigger / condition
  - Implementation details
  - Result / impact (if mentioned)

4) Workflows & process (expand every step)
If the transcript describes any workflow/process, present it as:

- Workflow name (as described in the podcast)
  - Goal of the workflow (as stated)
  - Trigger: when/why they run this workflow (as stated)
  - Step-by-step:
    - Step 1 — <step name exactly as said>
      - What this means in their words (explain using transcript wording)
      - How they do it (tools/systems mentioned, e.g., Linear/Cursor/Slack/etc.)
      - Output/artifact produced (ticket/doc/PR/etc.) — if stated
      - Example from transcript — if stated
      - If any of the above is missing: "Not specified in transcript"
    - Step 2 — …
  - Hand-offs / roles involved (if stated)
  - Quality checks / review loops (if stated)

CRITICAL: Do not leave steps as vague labels.
If "Explore idea" is mentioned, you MUST look for:
- how they explore (e.g., prototype, doc, AI tool, brainstorming method)
- where (Linear doc, Cursor, PRD, whiteboard, etc.)
- what output they produce
If not found, write "Not specified in transcript" + clarifying questions.

Transcript:
{transcript}"""

# Fallback prompt when no transcript is available
DESCRIPTION_SUMMARY_PROMPT = """You are an expert podcast summarizer. Based on the episode description below, create a brief summary of what this podcast episode covers.

**Episode Information:**
- Show: {show_name}
- Episode: {episode_title}
- Guests: {guests}

**Episode Description:**
{description}

**Instructions:**
1. Summarize the main topics and themes of this episode based on the description
2. Keep the summary to 2-3 paragraphs
3. Note that this is based on the description only (full transcript was unavailable)
4. Highlight what listeners can expect to learn

**Summary:**"""


class Summarizer:
    """Generates AI-powered summaries of podcast episodes."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the summarizer.
        
        Args:
            api_key: OpenAI API key (uses settings if not provided)
            model: Model to use (uses settings if not provided)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"Initialized summarizer with model: {self.model}")
    
    def generate_summary(
        self,
        episode: Episode,
        show_name: str,
    ) -> str:
        """
        Generate a summary for a podcast episode.
        
        Args:
            episode: Episode to summarize
            show_name: Name of the podcast show
        
        Returns:
            Generated summary text
        """
        # Check if we have a transcript
        if episode.has_transcript() and episode.transcript != "Transcript not found":
            return self._summarize_transcript(episode, show_name)
        else:
            logger.warning(f"No transcript available for {episode.title}")
            return "Transcript not found"
    
    def _summarize_transcript(self, episode: Episode, show_name: str) -> str:
        """
        Generate summary from full transcript.
        
        Args:
            episode: Episode with transcript
            show_name: Podcast name
        
        Returns:
            Generated summary
        """
        # Prepare transcript (truncate if too long)
        transcript = episode.transcript or ""
        if len(transcript) > MAX_TRANSCRIPT_LENGTH:
            logger.warning(f"Transcript too long ({len(transcript)} chars), truncating")
            transcript = truncate_text(transcript, MAX_TRANSCRIPT_LENGTH, "... [transcript truncated]")
        
        # Build prompt
        prompt = SUMMARY_PROMPT.format(transcript=transcript)
        
        return self._call_api(prompt)
    
    def _summarize_description(self, episode: Episode, show_name: str) -> str:
        """
        Generate summary from episode description (fallback).
        
        Args:
            episode: Episode with description
            show_name: Podcast name
        
        Returns:
            Generated summary
        """
        # Clean HTML from description
        description = clean_html(episode.description) if episode.description else "No description available"
        
        # Format guest information
        guests = episode.get_guests_formatted() if episode.guests else "Not specified"
        
        # Build prompt
        prompt = DESCRIPTION_SUMMARY_PROMPT.format(
            show_name=show_name,
            episode_title=episode.title,
            guests=guests,
            description=description,
        )
        
        return self._call_api(prompt)
    
    def _call_api(self, prompt: str) -> str:
        """
        Call OpenAI API to generate summary.
        
        Args:
            prompt: Full prompt to send
        
        Returns:
            Generated text
        """
        try:
            logger.info(f"Calling OpenAI API with model {self.model}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert podcast analyst who creates structured, factual, bullet-point summaries. Only include information explicitly stated in the transcript."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=6000,
            )
            
            summary = response.choices[0].message.content
            
            # Log token usage
            if response.usage:
                logger.info(
                    f"API usage - Prompt: {response.usage.prompt_tokens}, "
                    f"Completion: {response.usage.completion_tokens}, "
                    f"Total: {response.usage.total_tokens}"
                )
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise
