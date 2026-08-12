"""
AI summarization service using OpenAI GPT-5.6.
Generates structured summaries from podcast transcripts.
"""

from typing import Optional
from openai import OpenAI

from ..models.episode import Episode
from ..config.settings import get_settings
from ..utils.logger import get_logger
from ..utils.helpers import clean_html, truncate_text

logger = get_logger(__name__)

# Maximum transcript length sent to the model.
# GPT-5.6 has a 1M-token context, so this is NOT a context limit — it is a cost
# fuse against a runaway transcript (a scraper looping on a page, Whisper
# stuttering a repeated phrase). Real episodes top out around 150k chars.
MAX_TRANSCRIPT_LENGTH = 500000  # ~125k tokens, ~$0.13 of input at Luna pricing

# Output budget. Reasoning tokens are billed as output and count against this.
MAX_OUTPUT_TOKENS = 16000

# GPT-5.x defaults to "medium"; restructuring a transcript we already supply
# does not need that much deliberation, and reasoning bills at the output rate.
REASONING_EFFORT = "low"

# Length budget. Telegram splits at 3996 chars/message and the episode header
# costs ~450, so two messages leave ~7400 chars for the summary itself. We ask
# the model for ~900 words (~5.5k chars) and keep the rest as headroom.
SUMMARY_TARGET_WORDS = 900
MAX_SUMMARY_CHARS = 7000

# Summary prompt template
SUMMARY_PROMPT = """Summarize the podcast transcript below for someone who did not listen to the episode.

Grounding:
- Use only what is explicitly stated in the transcript. Do not add background, advice, or inference of your own.
- If something is implied but never said, leave it out rather than guessing.
- Favour concrete detail over generalities: numbers, names, tools, examples, decisions, tradeoffs.

Length: at most {target_words} words in total. Selecting what matters is part of the
task. A shorter summary covering the most important material beats a complete one.

Format: plain text only. Do not use Markdown — no #, *, _, backticks or ---.
Start bullets with "•" and indent sub-bullets by two spaces. Write section
headings as plain words on their own line.

Structure:

KEY POINTS

At most 5 blocks, covering the 5 most important storylines of the episode.
Anything that does not earn one of those places is left out. Each block is:

• A headline that states the point itself rather than naming the topic.
  Write "Ads were introduced without hurting UX by controlling quality via
  direct partners", not "On advertising".
  • Up to 4 bullets on what was actually said, one line each.
  • Up to 2 bullets on the problem or constraint that led to it.
  • Up to 2 bullets of specifics: numbers, experiments, tools, partners, flows.
  • Up to 2 bullets on tradeoffs, caveats or disagreements that came up.

Drop any of those four categories the transcript does not support. An empty
category should disappear entirely — never announce that something is missing.

WHAT THEY RECOMMEND

• Up to 5 things they recommend doing, one line each, with the stated condition
  or expected outcome where one was given.
• Up to 3 things they warn against, one line each.

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
2. Keep the summary to 2-3 short paragraphs
3. Note that this is based on the description only (full transcript was unavailable)
4. Highlight what listeners can expect to learn
5. Plain text only — no Markdown, no #, *, _ or backticks

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
        prompt = SUMMARY_PROMPT.format(
            transcript=transcript,
            target_words=SUMMARY_TARGET_WORDS,
        )
        
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
                # GPT-5.x models only accept the default temperature, and use
                # max_completion_tokens instead of max_tokens.
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                reasoning_effort=REASONING_EFFORT,
            )

            choice = response.choices[0]
            summary = choice.message.content

            # Log token usage
            if response.usage:
                details = getattr(response.usage, "completion_tokens_details", None)
                reasoning_tokens = getattr(details, "reasoning_tokens", None)
                logger.info(
                    f"API usage - Prompt: {response.usage.prompt_tokens}, "
                    f"Completion: {response.usage.completion_tokens} "
                    f"(reasoning: {reasoning_tokens}), "
                    f"Total: {response.usage.total_tokens}, "
                    f"Finish reason: {choice.finish_reason}"
                )

            # A reasoning model can burn the whole output budget before writing
            # any summary. Fail loudly rather than posting an empty message.
            if choice.finish_reason == "length":
                raise RuntimeError(
                    f"Model hit the {MAX_OUTPUT_TOKENS} token output budget before "
                    f"finishing the summary. Raise MAX_OUTPUT_TOKENS or lower "
                    f"REASONING_EFFORT."
                )

            if not summary or not summary.strip():
                raise RuntimeError(
                    f"Model returned an empty summary "
                    f"(finish_reason={choice.finish_reason})."
                )

            return self._fit_to_budget(summary.strip())

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise

    def _fit_to_budget(self, summary: str) -> str:
        """
        Trim a summary that overshot MAX_SUMMARY_CHARS.

        The prompt asks for ~900 words, but a prompt is a request, not a
        guarantee. This is the deterministic backstop that keeps delivery to two
        Telegram messages. Trailing paragraphs go first, so the least important
        sections are what fall off.

        Args:
            summary: Generated summary

        Returns:
            Summary within the character budget
        """
        if len(summary) <= MAX_SUMMARY_CHARS:
            return summary

        marker = "\n\n[trimmed to fit Telegram]"
        budget = MAX_SUMMARY_CHARS - len(marker)

        kept: list[str] = []
        used = 0
        for paragraph in summary.split("\n\n"):
            if used + len(paragraph) + 2 > budget:
                break
            kept.append(paragraph)
            used += len(paragraph) + 2

        # No paragraph boundary within budget — fall back to a hard cut.
        trimmed = "\n\n".join(kept) if kept else summary[:budget].rstrip()

        logger.warning(
            f"Summary was {len(summary)} chars, over the {MAX_SUMMARY_CHARS} "
            f"budget; trimmed to {len(trimmed)}. Consider lowering "
            f"SUMMARY_TARGET_WORDS or tightening the prompt caps."
        )

        return trimmed + marker
