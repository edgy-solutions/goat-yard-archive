#!/usr/bin/env python3
"""Test BAML verse extraction."""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()
print(f"API key set: {bool(os.getenv('OPENROUTER_API_KEY'))}")

from baml_client import b

async def test():
    md_path = Path("extracted_images/page100_image1.md")
    text = md_path.read_text(encoding="utf-8")
    print(f"Markdown length: {len(text)} chars")
    
    result = await b.ExtractVersesFromMarkdown(text)
    print(f"Verses extracted: {len(result)}")
    for v in result[:3]:
        print(f"  {v.verse_ref}: {v.start_phrase[:40]}...")

if __name__ == "__main__":
    asyncio.run(test())
