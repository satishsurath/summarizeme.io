import os
import json
import ollama
import tiktoken  # pip install tiktoken

ollama_host = os.getenv("REMOTE_OLLAMA_HOST")
print(f"ollama_host: {ollama_host}")

client = ollama.Client(host='http://' + ollama_host + ':11434')

DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR is None:
    DATA_DIR = "data/channels"  # Base directory for channel data

# Adjust this if your model’s token limit is different
MAX_TOKENS_PER_CHUNK = 2000  

def num_tokens_from_string(string: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count the approximate number of tokens in a string using tiktoken.
    By default, uses an encoding that should be compatible with GPT-3.5.
    Adjust the model string or the encoding as needed for your scenario.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback if model not found in tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(string)
    return len(tokens)


def chunk_text_by_sentence(text: str, max_tokens: int = 4000, model: str = "gpt-3.5-turbo") -> list:
    """
    Splits a text into chunks of sentences, ensuring each chunk stays
    below the specified max_tokens threshold (including some buffer for the prompt).
    """
    sentences = text.split('.')

    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_with_period = sentence + "."
        sentence_tokens = num_tokens_from_string(sentence_with_period, model=model)

        if current_length + sentence_tokens > max_tokens:
            chunk_text = ". ".join(current_chunk).strip()
            if chunk_text:
                chunks.append(chunk_text)
            current_chunk = [sentence]
            current_length = sentence_tokens
        else:
            current_chunk.append(sentence)
            current_length += sentence_tokens

    if current_chunk:
        chunk_text = ". ".join(current_chunk).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


def enhance_chunk_with_ollama(chunk_text: str, model: str) -> str:
    """
    Given a chunk of text, build the prompt and pass it to Ollama.
    Return the 'enhanced' text from Ollama.
    """
    prompt = f"""
You are given the raw transcript from a YouTube video. Your task is to transform it into a more human-readable format without timestamps or excessive line breaks. 
Follow these rules exactly:
	1. Remove all timestamps (if any).
	2. DO NOT remove any words or content from the transcript.
	3. Only correct words if they appear to be transcription errors and adjust sentence structure for clarity and readability.
	4. DO NOT summarize, paraphrase, or omit any content—keep it as close to the original as possible, aside from necessary grammar/spelling fixes.
	5. Present the final transcript as one continuous text (or in coherent paragraphs) that is easy to read.

Transcript:
{chunk_text}
    """
    print(f"Prompt: {prompt}")

    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    enhanced_text = response.get("message", {}).get("content", "").strip()
    print(f"Enhanced text: {enhanced_text}")
    return enhanced_text


def evaluate_enhanced_text(instructions: str, raw_text: str, enhanced_text: str, model: str = "phi4") -> str:
    """
    Given the original instructions, raw (unprocessed) text, and the enhanced text,
    asks the model to verify if instructions were followed. Returns either 'yes' or 'no'.
    
    The model must ONLY respond with 'yes' or 'no'—no extra text.
    """
    eval_prompt = f"""
You are asked to verify if the instructions were followed in the transformation of a transcript.
Instructions:
{instructions}

Original (Raw) Transcript:
{raw_text}

Enhanced Transcript:
{enhanced_text}

Question: Did the Enhanced Transcript strictly follow all the instructions above?
Please answer with a single score from 1 to 5 (1 being did not follow at all, 5 being it completely followed the instructions). No explanation. No additional text.
"""
    print(f"Evaluation prompt: {eval_prompt[:]}")

    eval_response = client.chat(
        model=model,
        messages=[{"role": "user", "content": eval_prompt}]
    )
    answer = eval_response.get("message", {}).get("content", "").strip().lower()
    
    print(f"\n-------------------------------Evaluation response: {answer}")
    # Sometimes the model might produce extra text. 
    # We only want 'yes' or 'no', so let's do a small cleanup:
    if int(answer[0]) > 3:
        return "yes"
    else:
        # If it didn't produce a clean yes/no, we can default to "no" or some fallback.
        return "no"


def transcript_enhancer_ollama(
    channel_id: str,
    video_id: str,
    model: str = "phi4"
):
    """
    Summarize or 'enhance' a transcript by sending it to a locally running Ollama instance
    (with the specified model). If the transcript is longer than MAX_TOKENS_PER_CHUNK, it is
    split into smaller sentence-based chunks. The final concatenated text is saved in:
    data/channels/<channel_id>/enhanced_phi4_transcript/<video_id>.md
    """

    # 1. Locate transcript file
    transcript_file = os.path.join(DATA_DIR, channel_id, "transcripts", f"{video_id}.json")
    if not os.path.exists(transcript_file):
        raise FileNotFoundError(f"Transcript file not found for video {video_id}")

    # 2. Read transcript
    with open(transcript_file, "r", encoding="utf-8") as f:
        video_data = json.load(f)
    transcript_entries = video_data.get("transcript", [])
    transcript_text = "\n".join([e["text"] for e in transcript_entries])
    title = video_data.get("title", "Untitled Video")
    upload_date = video_data.get("upload_date", "UnknownDate")

    # The transformation instructions we'll pass to the evaluator:
    instructions_for_evaluation = """
    1. Remove all timestamps (if any).
    2. DO NOT remove any words or content from the transcript.
    3. Only correct words if they appear to be transcription errors and adjust sentence structure for clarity and readability.
    4. DO NOT summarize, paraphrase, or omit any content—keep it as close to the original as possible, aside from necessary grammar/spelling fixes.
    5. Present the final transcript as one continuous text (or in coherent paragraphs) that is easy to read.
    """

    # 3. Check token length & chunk if needed
    total_tokens = num_tokens_from_string(transcript_text, model="gpt-3.5-turbo")
    
    def enhance_and_evaluate(raw_text_chunk: str) -> str:
        """
        Helper to enhance a chunk, then evaluate with a yes/no loop.
        If the evaluation is 'no', re-try until 'yes' or until a max number of retries is reached.
        """
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            print(f"Enhancing chunk (attempt {attempt})...")
            enhanced_candidate = enhance_chunk_with_ollama(raw_text_chunk, model=model)
            
            evaluation_result = evaluate_enhanced_text(
                instructions_for_evaluation,
                raw_text_chunk,
                enhanced_candidate,
                model=model
            )
            print(f"Evaluation result: {evaluation_result}")
            
            if evaluation_result == "yes":
                print("Instructions followed successfully.")
                return enhanced_candidate
            else:
                print("Instructions were NOT followed. Retrying...")
                # Optionally, you could modify the prompt or do some additional logic here.
        
        # If we still can't get 'yes' after max_retries, we just return the last one
        print("Reached maximum retries, returning last enhanced candidate.")
        return enhanced_candidate

    if total_tokens > MAX_TOKENS_PER_CHUNK:
        print(f"Transcript has {total_tokens} tokens, exceeding {MAX_TOKENS_PER_CHUNK}. Splitting into chunks...")
        text_chunks = chunk_text_by_sentence(
            transcript_text,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            model="gpt-3.5-turbo"
        )

        enhanced_chunks = []
        for i, chunk in enumerate(text_chunks):
            print(f"Processing chunk {i+1}/{len(text_chunks)}...")
            final_chunk = enhance_and_evaluate(chunk)
            enhanced_chunks.append(final_chunk)

        summary_text = "\n".join(enhanced_chunks)
    else:
        # If it's within the limit, do it all at once
        print(f"Transcript has {total_tokens} tokens, within {MAX_TOKENS_PER_CHUNK} limit. Enhancing in one request...")
        summary_text = enhance_and_evaluate(transcript_text)

    # 4. Save final enhanced transcript to file
    summary_folder = os.path.join(DATA_DIR, channel_id, "enhanced_phi4_transcript")
    os.makedirs(summary_folder, exist_ok=True)
    summary_path = os.path.join(summary_folder, f"{video_id}.md")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print(f"Enhanced transcript saved to {summary_path}")