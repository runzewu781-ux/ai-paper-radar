# pragent/backend/text_processor.py
import re
from typing import List, Tuple
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from openai import AsyncOpenAI, BadRequestError
from tqdm.asyncio import tqdm

SUMMARIZATION_THRESHOLD = 4000
FALLBACK_HEADER_SIZE = 3000

def create_llm(model: str, client: AsyncOpenAI, disable_qwen_thinking: bool = False):
    """Creates a LangChain LLM object from the provided client."""
    if not client:
        raise ValueError("API client is not initialized.")
    
    model_kwargs = {}
    if "qwen3" in model.lower() and disable_qwen_thinking:
        tqdm.write("[*] Summarizer: Enabling 'disable_thinking' for Qwen3 model.")
        model_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    
    return ChatOpenAI(
        model_name=model,
        openai_api_key=client.api_key,
        openai_api_base=str(client.base_url),
        model_kwargs=model_kwargs  # Pass the extra arguments here
    )

def split_text_by_structure(long_text: str) -> Tuple[str, str]:
    """
    Intelligently splits the text into a "header" (title, authors, abstract) and "body".
    It looks for keywords like "Abstract" and "Introduction" to determine the split point.
    """
    abstract_match = re.search(r'\bAbstract\b', long_text, re.IGNORECASE)
    if not abstract_match:
        tqdm.write("[!] 'Abstract' keyword not found. Falling back to fixed character count for splitting.")
        return long_text[:FALLBACK_HEADER_SIZE], long_text[FALLBACK_HEADER_SIZE:]

    intro_match = re.search(r'(\n\s*(\d+|I|II|III|IV|V)\.?\s*)?Introduction', long_text[abstract_match.end():], re.IGNORECASE)
    
    if not intro_match:
        tqdm.write("[!] 'Introduction' keyword not found after 'Abstract'. Falling back to fixed character count for splitting.")
        return long_text[:FALLBACK_HEADER_SIZE], long_text[FALLBACK_HEADER_SIZE:]
        
    split_point = abstract_match.end() + intro_match.start()
    
    header_text = long_text[:split_point]
    body_text = long_text[split_point:]
    
    tqdm.write(f"[*] Successfully separated header via keywords ({len(header_text)} characters).")
    return header_text, body_text

async def summarize_long_text(long_text: str, model: str, client: AsyncOpenAI, disable_qwen_thinking: bool = False) -> str:
    """
    Asynchronously summarizes long text using a structure-aware hybrid strategy.
    """
    if not long_text:
        return ""

    if len(long_text) <= SUMMARIZATION_THRESHOLD:
        tqdm.write(f"[*] Total text length ({len(long_text)} chars) is below threshold {SUMMARIZATION_THRESHOLD}. Skipping summarization.")
        return long_text

    header_text, body_text = split_text_by_structure(long_text)
    
    if not body_text:
        tqdm.write("[!] Could not separate the body text. Returning the full original text.")
        return header_text

    tqdm.write(f"[*] Summarizing the identified body text ({len(body_text)} characters)...")

    try:
        # Pass the flag down to the LLM creator
        llm = create_llm(model, client, disable_qwen_thinking=disable_qwen_thinking)
    except ValueError as e:
        return f"Error: {e}"

    body_summary = ""

    tqdm.write("[*] Attempting high-speed 'stuff' summarization strategy for the body text...")
    try:
        stuff_prompt_template = """
        # INSTRUCTION
        You are a scientific evidence editor. Build a detailed source-grounded evidence digest of the paper body.
        Preserve exact reported numbers, units, baselines, comparison directions, dataset names, method stages,
        experimental settings, limitations, and uncertainty/causal qualifiers. Mention important Figure/Table numbers
        when the text names them. Do not add interpretation or external facts. The digest will be used as the sole
        factual source for a science article, so omission of a major result is more harmful than extra detail.

        # PAPER BODY TEXT:
        ---
        {text}
        ---

        # YOUR DETAILED SYNTHESIZED SUMMARY:
        """
        STUFF_PROMPT = PromptTemplate(template=stuff_prompt_template, input_variables=["text"])
        stuff_chain = load_summarize_chain(llm, chain_type="stuff", prompt=STUFF_PROMPT, verbose=True)
        
        docs = [Document(page_content=body_text)]
        body_summary = await stuff_chain.arun(docs)
        tqdm.write("[OK] 'Stuff' strategy for the body text was successful!")

    except BadRequestError as e:
        if "context_length_exceeded" not in str(e).lower() and "maximum context length" not in str(e).lower() and "context length" not in str(e).lower():
            tqdm.write(f"[!] Unexpected API error with 'stuff' strategy: {e}")
            return f"Error: API call failed - {e}"
        tqdm.write("[!] Body text is too long for the 'stuff' strategy. Falling back to 'map_reduce'.")
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=30000, 
            chunk_overlap=3000
        )
        chunks = text_splitter.split_text(body_text)
        docs = [Document(page_content=t) for t in chunks]
        tqdm.write(f"[*] Body text has been split into {len(docs)} chunks for summarization.")

        map_prompt_template = """
        # INSTRUCTION
        You are a research evidence extractor. Convert this segment into a compact evidence ledger.
        Preserve exact numbers, units, named entities, datasets, methods, baselines, comparisons, limitations,
        qualifiers, and Figure/Table references. Do not infer missing facts and do not use outside knowledge.

        # TEXT SEGMENT:
        ---
        {text}
        ---

        # YOUR CONCISE SUMMARY:
        """
        MAP_PROMPT = PromptTemplate(template=map_prompt_template, input_variables=["text"])

        combine_prompt_template = """
        # INSTRUCTION
        You are a scientific evidence editor. Merge the following chunk-level evidence ledgers into one detailed,
        deduplicated evidence digest. Preserve exact numbers, units, comparison objects, qualifiers, limitations,
        and Figure/Table references. Never invent a fact that is absent from the ledgers.

        # LIST OF SUMMARIES:
        ---
        {text}
        ---

        # YOUR SYNTHESIZED FINAL DETAILED SUMMARY:
        """
        COMBINE_PROMPT = PromptTemplate(template=combine_prompt_template, input_variables=["text"])

        map_reduce_chain = load_summarize_chain(llm, chain_type="map_reduce", map_prompt=MAP_PROMPT, combine_prompt=COMBINE_PROMPT, verbose=True)
        
        try:
            body_summary = await map_reduce_chain.arun(docs)
            tqdm.write("[OK] 'Map-Reduce' summarization for the body text is complete.")
        except Exception as chain_error:
            tqdm.write(f"[!] 'Map-Reduce' chain execution failed: {chain_error}")
            return f"Error: 'Map-Reduce' summarization failed - {chain_error}"

    except Exception as e:
        tqdm.write(f"[!] An unknown error occurred during the summarization process: {e}")
        return f"Error: Summarization failed - {e}"

    final_text = f"{header_text}\n\n[--- Body Summary ---]\n\n{body_summary}"
    return final_text
