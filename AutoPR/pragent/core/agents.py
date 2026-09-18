# agent.py

import base64
from openai import AsyncOpenAI
from contextlib import asynccontextmanager
from typing import List, Dict, AsyncIterator, Optional, Any, Tuple
from tqdm.asyncio import tqdm
import tiktoken


def _prepare_extra_body(model_name: str, disable_qwen_thinking: bool) -> Optional[Dict[str, Any]]:
    if "qwen3" in model_name.lower() and disable_qwen_thinking:
        tqdm.write("[*] 'disable_thinking' mode has been enabled for the Qwen3 model.")
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return None

@asynccontextmanager
async def setup_client(api_key: str, base_url: str) -> AsyncIterator[AsyncOpenAI]:
    """Use an asynchronous context manager to create and properly destroy the API client."""
    client = None
    if not api_key or "sk-" not in api_key:
        tqdm.write("[!] Error: API Key is invalid or not set.")
        yield None
        return

    try:
        tqdm.write("[*] Initializing API client...")
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=300.0)
        yield client
    except Exception as e:
        tqdm.write(f"[!] Error initializing AsyncOpenAI client: {e}")
        yield None
    finally:
        if client:
            tqdm.write("[*] Closing API client connection...")
            await client.close()
            tqdm.write("[*] API client closed.")

def encode_image_to_base64(image_path: str) -> str:

    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        tqdm.write(f"[!] Failed to encode image {image_path}: {e}")
        return ""


async def call_text_llm_api(local_client: AsyncOpenAI, system_prompt: str, user_prompt: str, model: str, disable_qwen_thinking: bool = False) -> str:
    if not local_client: return "Error: API client is not configured."
    try:
        extra_body = _prepare_extra_body(model, disable_qwen_thinking)
        completion = await local_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            extra_body=extra_body  # 应用 extra_body
        )
        return completion.choices[0].message.content
    except Exception as e:
                return f"Error: Text API call failed - {e}"

async def call_multimodal_llm_api(local_client: AsyncOpenAI, system_prompt: str, user_prompt_parts: list, model: str, disable_qwen_thinking: bool = False) -> str:

    if not local_client: return "Error: API client is not configured."
    try:
        extra_body = _prepare_extra_body(model, disable_qwen_thinking)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_parts}
        ]
        completion = await local_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
            extra_body=extra_body  # 应用 extra_body
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error: Multimodal API call failed - {e}"

class BlogGeneratorAgent:

    def __init__(self, prompt_template: str, model: str):
        self.prompt_template = prompt_template
        self.model = model
        self.system_prompt = "You are a top-tier science and technology blogger and popular science writer."

    async def run(self, local_client: AsyncOpenAI, paper_text: str, disable_qwen_thinking: bool = False) -> str:
        user_prompt = self.prompt_template.format(paper_text=paper_text)
        return await call_text_llm_api(local_client, self.system_prompt, user_prompt, self.model, disable_qwen_thinking)


