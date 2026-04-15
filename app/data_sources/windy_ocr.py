"""Extract weather data from Windy screenshots using Claude Vision."""

import base64
import json
import mimetypes
import anthropic
from app.config import ANTHROPIC_API_KEY

EXTRACTION_PROMPT = """\
You are extracting weather forecast data from a Windy app screenshot.

The screenshot shows a table-like grid with:
- Column headers: hours (e.g., 11 AM, 12 PM, 01 PM, etc.)
- Row groups by altitude level (e.g., 6394 ft, 4781 ft, 3243 ft, 2500 ft, 1773 ft, 364 ft)
- Each altitude group has two rows: wind direction arrows and wind speed values
- Below the altitude groups, there are surface/ground-level rows:
  - A wind direction arrow row
  - "mph" row: surface wind speed (~33ft / 10m level)
  - "mph*" row: wind gusts
  - "°F" row (first one): temperature
  - "°F" row (second one): dew point temperature
  - "%" row: relative humidity

Extract ALL visible data and return it as JSON with this exact structure:
{
  "date": "YYYY-MM-DD",
  "hours": [11, 12, 13, 14, ...],
  "altitudes": {
    "6394ft": {
      "wind_speed_mph": [15, 15.3, 14.3, 13.1, ...],
      "wind_dir": ["E", "E", "E", "E", ...]
    },
    "4781ft": {
      "wind_speed_mph": [...],
      "wind_dir": [...]
    },
    "3243ft": { ... },
    "2500ft": { ... },
    "1773ft": { ... },
    "364ft": {
      "wind_speed_mph": [...],
      "wind_dir": [...]
    },
    "33ft": {
      "wind_speed_mph": [...],
      "wind_gust_mph": [...],
      "wind_dir": [...],
      "temp_f": [...],
      "dewpoint_f": [...],
      "humidity_pct": [...]
    }
  }
}

Important rules:
- The "33ft" key represents all the surface/ground-level rows at the bottom
- Wind direction arrows: interpret the arrow direction (← is W, → is E, ↑ is S, ↓ is N, and diagonals accordingly). If they all point left (←), that means wind is coming FROM the east, so direction is "E"
- Read the date from the header (e.g., "WED, APR 15" → "2026-04-15"). Use the current year 2026.
- Hours should be integers in 24-hour format based on AM/PM labels
- Include ALL columns visible in the screenshot
- Use numeric values (not strings) for all measurements
- Return ONLY the JSON object, no other text"""


def is_configured():
    return bool(ANTHROPIC_API_KEY)


def extract_from_image(image_path):
    """Extract Windy weather data from a screenshot using Claude Vision.

    Args:
        image_path: Path to the screenshot image file

    Returns:
        Dict with extracted weather data matching the Windy entry format,
        or None if extraction fails
    """
    if not is_configured():
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    # Read and encode image
    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    # Parse the response
    response_text = message.content[0].text.strip()

    # Handle potential markdown code blocks in response
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        response_text = "\n".join(lines)

    return json.loads(response_text)
