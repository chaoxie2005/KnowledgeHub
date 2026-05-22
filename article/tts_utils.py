import html
import logging
import os
import re

from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

logger = logging.getLogger(__name__)

DASHSCOPE_TTS_MODEL = os.getenv("DASHSCOPE_TTS_MODEL", "cosyvoice-v1")
DASHSCOPE_TTS_VOICE = os.getenv("DASHSCOPE_TTS_VOICE", "longxiaochun")
MAX_CHUNK_CHARS = int(os.getenv("TTS_MAX_CHUNK_CHARS", "1500"))


def _strip_markdown_to_plain_text(content: str) -> str:
    """Convert Markdown content to clean plain text suitable for TTS."""
    import markdown

    html_content = markdown.markdown(content, extensions=["extra", "codehilite"])
    text = re.sub(r"<[^>]+>", "", html_content)
    text = html.unescape(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at paragraph boundaries, each <= max_chars."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = re.split(r"(?<=[。！？.!?])", para)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(current) + len(sentence) <= max_chars:
                    current += sentence
                else:
                    if current:
                        chunks.append(current.strip())
                    current = sentence
        else:
            if len(current) + len(para) + 2 <= max_chars:
                current = current + "\n\n" + para if current else para
            else:
                chunks.append(current.strip())
                current = para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _synthesize_single_chunk(text: str) -> bytes | None:
    """Call DashScope TTS v2 for a single text chunk. Returns MP3 bytes or None."""
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY not configured")
        return None

    try:
        synthesizer = SpeechSynthesizer(
            model=DASHSCOPE_TTS_MODEL,
            voice=DASHSCOPE_TTS_VOICE,
            format=AudioFormat.MP3_48000HZ_MONO_256KBPS,
        )
        audio_data = synthesizer.call(text)
        if not audio_data:
            logger.warning("TTS returned empty audio data")
            return None

        return audio_data

    except Exception:
        logger.exception("SpeechSynthesizer call failed")
        return None


def generate_article_audio(content: str) -> bytes | None:
    """Generate MP3 audio for article content. Returns bytes or None on failure."""
    try:
        plain_text = _strip_markdown_to_plain_text(content)
        if not plain_text:
            logger.warning("Article content is empty after stripping")
            return None

        chunks = _chunk_text(plain_text)
        if not chunks:
            return None

        audio_chunks = []
        for i, chunk in enumerate(chunks):
            audio_bytes = _synthesize_single_chunk(chunk)
            if audio_bytes is None:
                logger.error("Failed to synthesize chunk %d/%d", i + 1, len(chunks))
                return None
            audio_chunks.append(audio_bytes)

        if len(audio_chunks) == 1:
            return audio_chunks[0]

        # Concatenate MP3 chunks
        try:
            from pydub import AudioSegment
            from io import BytesIO

            combined = AudioSegment.empty()
            for chunk_bytes in audio_chunks:
                segment = AudioSegment.from_file(BytesIO(chunk_bytes), format="mp3")
                combined += segment

            output = BytesIO()
            combined.export(output, format="mp3")
            return output.getvalue()
        except Exception:
            logger.warning(
                "pydub concatenation failed, falling back to raw join"
            )
            return b"".join(audio_chunks)

    except Exception:
        logger.exception("generate_article_audio failed")
        return None
