# Discord Voice Chat Integration — Research & Plan

**Date:** 2026-03-05
**Status:** Research complete, not yet implemented

---

## Current adw-agent Code Overview

The bot is a **text-only Discord daemon** that:

| Layer | File | Purpose |
|-------|------|---------|
| **Entry** | `daemon.py` | CLI entry point, poll loop (every 10s), starts Discord bot + task dispatcher |
| **Discord** | `discord_bot.py` | Parses `!commands`, role auth, thread creation, thread-reply handling |
| **Queue** | `queue.py` | SQLite-backed async task queue |
| **Config** | `config.py` | TOML + `.env` loading into dataclasses |
| **Streaming** | `streaming.py` | Edit-in-place Discord messages for live Claude output |
| **Workflows** | `workflows/compile.py`, `package.py`, `submit.py`, `analyze.py`, `custom.py` | Each workflow runs Claude Agent SDK sessions or UE build subprocesses |
| **Utilities** | `cost_tracker.py`, `session_history.py`, `utils.py` | Budget warnings, session persistence, log parsing |

The bot uses `discord.py >=2.3` with only `Intents.default()` + `message_content`. **No voice intents or voice-related code exists currently.**

---

## How to Enable Discord Voice Chat

There are **two approaches** depending on what we want:

---

### Approach A: Voice Commands -> Text Pipeline (Recommended Start)

Users speak in a voice channel, the bot transcribes via STT, runs the same `!command` pipeline, and speaks the result back via TTS.

#### Step 1: Install voice dependencies

```toml
# pyproject.toml — add these:
dependencies = [
    ...
    "discord.py[voice]>=2.3",   # adds PyNaCl for voice
    "openai>=1.0",               # for Whisper STT + TTS (or use another provider)
]
```

FFmpeg must also be on the system PATH (required by discord.py for audio playback):

```bash
# Windows (via scoop or choco):
scoop install ffmpeg
# or
choco install ffmpeg
```

#### Step 2: Enable voice intents

In `discord_bot.py`, update `create_bot`:

```python
def create_bot(config: AgentConfig, queue: TaskQueue, repo_root: str = "") -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True       # NEW: required for voice
    bot = discord.Client(intents=intents)
```

Also enable **Server Members Intent** and **Voice States** in the [Discord Developer Portal](https://discord.com/developers/applications) -> Bot settings.

#### Step 3: Add voice connection commands

Add `!join` and `!leave` commands in `discord_bot.py`:

```python
async def handle_join(message: discord.Message):
    """Join the user's current voice channel."""
    if not message.author.voice or not message.author.voice.channel:
        await message.reply("You need to be in a voice channel first.")
        return
    vc = await message.author.voice.channel.connect()
    await message.reply(f"Joined {vc.channel.name}")

async def handle_leave(message: discord.Message):
    """Leave the current voice channel."""
    if message.guild.voice_client:
        await message.guild.voice_client.disconnect()
        await message.reply("Disconnected from voice.")
```

#### Step 4: Record and transcribe audio (STT)

Use `discord.py`'s sink-based recording (or a custom AudioSink):

```python
import io
import openai

async def transcribe_audio(audio_bytes: bytes) -> str:
    """Send recorded audio to Whisper for transcription."""
    client = openai.AsyncOpenAI()
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "recording.wav"
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return transcript.text
```

#### Step 5: Text-to-Speech playback

```python
import discord
import tempfile
import openai

async def speak_response(vc: discord.VoiceClient, text: str):
    """Convert text to speech and play it in the voice channel."""
    client = openai.AsyncOpenAI()
    response = await client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(response.content)
        f.flush()
        source = discord.FFmpegPCMAudio(f.name)
        vc.play(source)
```

#### Step 6: Config additions

```toml
# config.toml
[voice]
enabled = true
stt_provider = "openai"        # "openai" | "deepgram" | "azure"
tts_provider = "openai"        # "openai" | "elevenlabs" | "azure"
tts_voice = "alloy"
auto_join = false               # auto-join when a user enters a channel
listen_timeout_seconds = 30     # max recording duration per utterance
```

```env
# .env
OPENAI_API_KEY=sk-...
```

---

### Approach B: Full Conversational Voice (Advanced)

A continuous voice experience where the bot listens, detects speech segments (VAD), transcribes, runs Claude, and speaks back — like a voice assistant.

This is significantly more complex and requires:

1. **Voice Activity Detection (VAD)** — e.g., `webrtcvad` or `silero-vad` to detect when a user starts/stops speaking.
2. **Streaming STT** — Deepgram or Azure Speech Services for real-time transcription.
3. **Streaming TTS** — ElevenLabs or Azure for low-latency speech output.
4. **Conversation state machine** — managing listen/think/speak states per user.

#### Additional dependencies for Approach B

```toml
dependencies = [
    ...
    "webrtcvad>=2.0",
    "deepgram-sdk>=3.0",
    "numpy>=1.24",
]
```

#### Architecture sketch

```
Voice Channel
    |
    v
AudioSink (discord.py) --> VAD --> chunk on silence
    |
    v
STT (Deepgram streaming) --> transcribed text
    |
    v
Claude Agent SDK session --> response text
    |
    v
TTS (ElevenLabs streaming) --> audio chunks
    |
    v
VoiceClient.play() --> spoken response
```

---

## Recommended Implementation Order

1. **Phase 1:** `!join` / `!leave` commands + basic TTS playback of bot responses
2. **Phase 2:** Record user audio + Whisper STT transcription + feed into existing command pipeline
3. **Phase 3:** VAD-based continuous listening (no explicit `!listen` command needed)
4. **Phase 4:** Streaming STT/TTS for lower latency conversational experience

## Key Dependencies Summary

| Package | Purpose | Required Phase |
|---------|---------|---------------|
| `discord.py[voice]` | Voice channel connect/play/record | Phase 1 |
| `PyNaCl` | Encryption for voice (auto-installed with above) | Phase 1 |
| `FFmpeg` (system) | Audio format conversion for playback | Phase 1 |
| `openai` | Whisper STT + TTS-1 | Phase 1-2 |
| `webrtcvad` or `silero-vad` | Voice Activity Detection | Phase 3 |
| `deepgram-sdk` | Streaming STT | Phase 4 |
| `elevenlabs` | Streaming TTS | Phase 4 |

## Estimated Cost Per Interaction (OpenAI)

- **Whisper STT:** ~$0.006/min of audio
- **TTS-1:** ~$0.015 per 1K characters
- **Claude API:** existing cost (varies by model/tokens)
- Typical voice command round-trip: **~$0.02-0.05** (excluding Claude)
