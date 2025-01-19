import os
import re
import json
import ollama
from dotenv import load_dotenv


load_dotenv()
ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
print(f"ollama_host: {ollama_host}")

client = ollama.Client(host='http://' + ollama_host + ':11434')

def split_into_sentences(text):
    """
    Split text into sentences by typical punctuation delimiters.
    We'll split on '.', '?', '!', and preserve those delimiters 
    so we can re-attach them. 
    Then we trim whitespace.
    """
    # A simple approach: use a regex that matches on (.?!),
    # capturing the punctuation to re-attach. This won't be perfect for 
    # abbreviations, decimal points, etc., but it's a decent start.
    sentence_pattern = re.compile(r'([^.?!]+[.?!])')
    # This returns a list of "sentence-like" strings, each ending with punctuation
    parts = sentence_pattern.findall(text)
    # If there's leftover text without punctuation, we handle that as well
    remainder = sentence_pattern.sub('', text).strip()
    if remainder:
        parts.append(remainder)
    
    # Clean up extra whitespace
    sentences = [p.strip() for p in parts if p.strip()]
    return sentences

def chunk_transcript(transcript, max_words_per_chunk=4000):
    """
    Improved chunker:
    1) Split transcript into sentences.
    2) Combine sentences into chunks until we reach ~4k words.
    3) If a single sentence is >4k words, we split that sentence by words.

    Returns a list of chunk strings.
    """
    sentences = split_into_sentences(transcript)
    chunks = []
    current_words = []
    current_count = 0

    for sentence in sentences:
        # Word count for this sentence
        words_in_sentence = sentence.split()
        sentence_len = len(words_in_sentence)

        if sentence_len > max_words_per_chunk:
            # The sentence alone exceeds chunk size
            # -> break this sentence into sub-chunks by words
            start = 0
            while start < sentence_len:
                end = start + max_words_per_chunk
                sub_chunk_words = words_in_sentence[start:end]
                sub_chunk_str = " ".join(sub_chunk_words)
                chunks.append(sub_chunk_str)
                start = end
        else:
            # Check if adding this sentence to current chunk
            # would exceed max_words_per_chunk
            if current_count + sentence_len > max_words_per_chunk:
                # flush current chunk
                chunks.append(" ".join(current_words))
                current_words = []
                current_count = 0
            
            # Add this sentence
            current_words.extend(words_in_sentence)
            current_count += sentence_len
    
    # leftover
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks

# ----------------------------
# 2) IMPROVED PROMPT ENGINEERING
# ----------------------------

def build_prompts_for_chunk(chunk_text):
    """
    Return a dict of four prompts: 
    - "concise": a short summary 
    - "key_topics": high-level topics
    - "takeaways": key insights, lessons 
    - "comprehensive": thorough notes capturing examples, references, quotes, etc.
    
    We add a bit more "context" or "instruction" for each prompt.
    """
    return {
        "concise": f"""
You are an expert summarizer. Read the following text and produce a concise summary 
(no more than 150 words) covering the main idea only:

TEXT:
{chunk_text}
""".strip(),

        "key_topics": f"""
You are an expert note-taker. From the following text, list the main topics or themes 
(with short bullet points), focusing on clarity and coverage:

TEXT:
{chunk_text}
""".strip(),

        "takeaways": f"""
You are a teaching assistant. From the text below, list the key takeaways or lessons 
the reader should remember. Focus on clarity and practical insights, in short bullet points:

TEXT:
{chunk_text}
""".strip(),

        "comprehensive": f"""
You are a meticulous researcher. Provide a comprehensive set of notes about 
the following text, capturing major points, examples, references, or quotes. 
Organize your notes with headings or bullet points. Aim for thoroughness:

TEXT:
{chunk_text}
""".strip()
    }

def ollama_generate_chunk(model_name, prompt):
    """
    Example direct HTTP request to Ollama. 
    We demonstrate extra parameters like 'temperature' or 'top_p' if desired.
    """
    try:
        response = client.chat(
        model=model_name,
        messages=[{"role": "user", "content": prompt}]
    )
        #enhanced_text = response.get("message", {}).get("content", "").strip()
        #resp = requests.post(url, json=payload, timeout=300)
        #resp.raise_for_status()
        data = response.get("message", {}).get("content", "").strip()
        return data #.get("content", "").strip()
    except Exception as e:
        #logger.error(f"Ollama request failed: {e}")
        print(f"Ollama request failed: {e}")
        return ""