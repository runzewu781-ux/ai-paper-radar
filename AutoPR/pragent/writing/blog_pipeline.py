# pragent/writing/blog_pipeline.py

from tqdm.asyncio import tqdm
import asyncio
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from openai import AsyncOpenAI
import re
import os
import json
import pytesseract
from PIL import Image
import asyncio

from pragent.core.agents import setup_client, BlogGeneratorAgent
from pragent.paper_processing.data_loader import load_plain_text
from pragent.writing.text_processor import summarize_long_text
from .prompts import (
    TEXT_GENERATOR_PROMPT, TEXT_GENERATOR_PROMPT_CHINESE,
)
FULLTEXT_CHAR_LIMIT = int(os.getenv("AUTOPR_FULLTEXT_CHAR_LIMIT", "240000"))


# Asynchronous OCR helper function
async def ocr_image_to_text(image_path: str) -> str:
    """
    Performs OCR on an image file to extract text asynchronously.
    """
    if not Path(image_path).exists():
        return ""
    try:
        # pytesseract is a blocking library, so we run it in a thread pool
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            None, 
            lambda: pytesseract.image_to_string(Image.open(image_path))
        )
        return text.strip()
    except Exception as e:
        tqdm.write(f"[!] OCR failed for {image_path}: {e}")
        return ""


async def generate_text_blog(
    txt_path: str, api_key: str, text_api_base: str, model: str, language: str,
    disable_qwen_thinking: bool = False, ablation_mode: str = "none",
    draft_prompt_override: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Generates a structured, factual blog DRAFT in the specified language. (Stage 1)
    """
    async with setup_client(api_key, text_api_base) as client:
        if not client:
            return "Error: API client configuration failed.", None
        
        paper_text = await load_plain_text(txt_path)
        if not paper_text:
            return "Error: Could not load text file.", None

        text_for_generation = ""
        if len(paper_text) > FULLTEXT_CHAR_LIMIT:
            if ablation_mode == 'no_hierarchical_summary':
                # This ablation means "do not summarize", not "discard most of the
                # paper".  Silent prefix truncation caused later sections, tables,
                # limitations and exact numbers to disappear from the evidence base.
                tqdm.write("[*] ABLATION (no_hierarchical_summary): Using full paper text without summarization.")
                text_for_generation = paper_text
            else:
                tqdm.write(
                    f"[*] Paper is {len(paper_text)} chars; building a hierarchical evidence digest "
                    f"(full-text limit={FULLTEXT_CHAR_LIMIT})."
                )
                summarized_text = await summarize_long_text(
                    paper_text,
                    model,
                    client,
                    disable_qwen_thinking=disable_qwen_thinking
                )
                if summarized_text.startswith("Error:"):
                    return summarized_text, None
                text_for_generation = summarized_text
        else:
            tqdm.write(f"[*] Using full paper text ({len(paper_text)} chars).")
            text_for_generation = paper_text
        
        if ablation_mode in ['no_logical_draft', 'stage2']:
            ablation_reason = "no_logical_draft" if ablation_mode != 'stage2' else 'stage2'
            tqdm.write(f"[*] ABLATION ({ablation_reason}): Skipping structured draft generation.")
            return text_for_generation, text_for_generation

        draft_prompt = draft_prompt_override or (TEXT_GENERATOR_PROMPT_CHINESE if language == 'zh' else TEXT_GENERATOR_PROMPT)
        generator = BlogGeneratorAgent(draft_prompt, model)
        generated_blog_draft = await generator.run(
            client, 
            text_for_generation, 
            disable_qwen_thinking=disable_qwen_thinking
        )
        return generated_blog_draft, text_for_generation
