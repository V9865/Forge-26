"""Guardrail verification system for EmberRoute LLM operational briefings.

Enforces zero-hallucination factual grounding:
1. Sentence-level fact citation validation: every sentence must cite at least one existing fact [F#].
2. Number grounding: every number token (integer, decimal, duration) must be present in cited facts.
3. Place name grounding: every capitalized proper noun / place name must be substantiated in cited facts.
4. Minimal surviving length: at least 2 substantiated sentences required for ok=True.
"""

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel


class GuardResult(BaseModel):
    """Result of factual verification across an LLM-generated briefing."""

    clean_text: str
    text_with_markers: str
    dropped_count: int
    ok: bool


# Common English words, report headings, and operational keywords that may appear capitalized
# but do NOT represent geographic settlements or place names.
COMMON_NON_PLACE_WORDS: Set[str] = {
    "A", "An", "The", "In", "At", "On", "By", "To", "From", "For", "With", "About", "Of", "Off",
    "Wind", "Fire", "Fires", "Warning", "Warnings", "Evacuation", "Evacuate", "Trapped",
    "Settlement", "Settlements", "All", "Every", "No", "Current", "Currently", "Recent",
    "Data", "Operational", "Safety", "Status", "Depart", "Departure", "Route", "Routes",
    "Predicted", "Mode", "Emergency", "Officer", "Priority", "Please", "However", "Therefore",
    "Meanwhile", "Immediate", "Baseline", "Due", "As", "If", "When", "While", "Where", "Which",
    "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "North", "South", "East", "West", "Northern", "Southern", "Eastern", "Western",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW", "NNE", "ENE", "ESE", "SSE", "SSW", "WSW", "WNW", "NNW",
    "LIVE", "SCENARIO", "EVACUATE", "TRAPPED", "ALREADY_BURNING", "NOT_THREATENED",
    "NASA", "FIRMS", "ESA", "AWS", "OSM", "UTC", "FRP", "VIIRS", "MODIS", "DEM",
    "This", "That", "These", "Those", "There", "Here", "Total", "Average", "Overall",
    "Hour", "Hours", "Minute", "Minutes", "Min", "Second", "Seconds", "Hectare", "Hectares", "Ha",
    "Speed", "Direction", "Bearing", "Burned", "Area", "Arrival", "Travel", "Time", "Times",
    "Open-Meteo", "OpenStreetMap", "Terrarium", "WorldCover", "EmberRoute", "District",
    "Briefing", "Report", "Overview", "Alert", "Caution", "Notice", "Critical", "Extreme",
}


def split_sentences(text: str) -> List[str]:
    """Split briefing text into individual sentences preserving trailing citation markers.

    Handles sentences ending in periods, exclamation marks, or question marks, followed
    by optional bracketed fact markers like `[F3][F7]`, across single- or multi-line text.
    """
    text = text.strip()
    if not text:
        return []

    # Split after terminal punctuation or closing citation brackets when followed by whitespace and a capital/bracket
    raw_parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])|(?<=\])\s+(?=[A-Z0-9])", text)
    sentences: List[str] = []

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        # If a part consists purely of trailing citation markers like '[F2]' or '[F2][F3]', attach to previous sentence
        if re.fullmatch(r"(\[F\d+\])+", part) and sentences:
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)

    return sentences


def extract_numbers(text: str) -> List[str]:
    """Extract numeric values including integers and decimals.

    Range Handling:
    Ranges such as '30-40 minutes', '30 - 40 min', or '30 to 40' are decomposed into their
    individual numeric constituents (e.g. '30' and '40'). Each constituent number must be
    substantiated by appearing in at least one of the cited supporting facts.
    """
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def verify(text: str, facts: Dict[str, str]) -> GuardResult:
    """Verify an operational briefing against cited facts.

    Enforces strict hallucination controls:
    1. Each sentence must contain at least one [F#] marker whose ID exists in `facts`.
    2. Every number token (decimals, integers, constituent numbers of ranges) must exist in at least one cited fact.
    3. Every capitalized place name (ignoring common operational terms) must exist in at least one cited fact.
    4. Sentences violating any rule are removed.
    5. ok is False if fewer than 2 sentences survive; True otherwise.

    Args:
        text: Raw LLM briefing text containing [F#] citations.
        facts: Ground truth facts dictionary mapping fact IDs (e.g. 'F1') to fact sentences.

    Returns:
        GuardResult with cleaned text, marked text, dropped sentence count, and boolean ok status.
    """
    sentences = split_sentences(text)
    surviving_sentences: List[str] = []
    dropped_count = 0

    for sent in sentences:
        # 1. Fact Citations Check
        cited_fids = re.findall(r"\[(F\d+)\]", sent)
        if not cited_fids:
            # Uncited sentence rejected
            dropped_count += 1
            continue

        if any(fid not in facts for fid in cited_fids):
            # Citation to missing/non-existent fact ID rejected
            dropped_count += 1
            continue

        # Text of cited facts combined
        cited_facts_text = " ".join(facts[fid] for fid in cited_fids)

        # Strip citation markers from sentence for content validation
        sent_no_markers = re.sub(r"\[F\d+\]", "", sent)

        # 2. Number Token Grounding Check
        sent_numbers = extract_numbers(sent_no_markers)
        fact_numbers = set(extract_numbers(cited_facts_text))
        # Also store numeric float values for safe decimal/integer comparison
        fact_floats = {float(n) for n in fact_numbers}

        number_hallucinated = False
        for num_str in sent_numbers:
            # Direct string match or float equivalence
            if num_str in fact_numbers:
                continue
            try:
                val = float(num_str)
                if val in fact_floats:
                    continue
            except ValueError:
                pass
            number_hallucinated = True
            break

        if number_hallucinated:
            dropped_count += 1
            continue

        # 3. Capitalized Place Name Grounding Check
        # Extract potential proper noun / place tokens
        cap_tokens = re.findall(r"\b[A-Z][a-zA-Z0-9_\'-]*\b", sent_no_markers)
        place_hallucinated = False

        for token in cap_tokens:
            if token in COMMON_NON_PLACE_WORDS:
                continue

            # Check if this capitalized token appears in any cited fact text
            if token.lower() not in cited_facts_text.lower():
                place_hallucinated = True
                break

        if place_hallucinated:
            dropped_count += 1
            continue

        # Sentence passed all verification gates
        surviving_sentences.append(sent)

    text_with_markers = " ".join(surviving_sentences)
    # Strip [F#] markers and normalize spacing for clean_text
    clean_text = re.sub(r"\[F\d+\]", "", text_with_markers)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    clean_text = re.sub(r"\s+([.,!?;:])", r"\1", clean_text)

    ok = len(surviving_sentences) >= 2

    return GuardResult(
        clean_text=clean_text,
        text_with_markers=text_with_markers,
        dropped_count=dropped_count,
        ok=ok,
    )
