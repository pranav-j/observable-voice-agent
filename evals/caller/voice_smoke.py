"""Place a scripted voice call against the running worker, over real WebRTC audio.

    python -m evals.caller.voice_smoke "A masala dosa please" "That's all" ...

Each caller line is synthesized with OpenAI TTS and streamed into the room as a
microphone track, with silence between lines so voice activity detection can find
the end of each turn. What the agent says comes back on LiveKit's transcription
stream and is printed. This is a development tool, and the seed of the audio caller.
"""

import argparse
import asyncio
import contextlib
import sys
import time
from dataclasses import dataclass, field

from livekit import rtc
from openai import AsyncOpenAI

from voice_order.api.app import join_token, new_call_ids
from voice_order.config import get_settings
from voice_order.menu.loader import load_menu
from voice_order.store.postgres import PostgresOrderStore
from voice_order.tools.base import Session
from voice_order.tools.catalog import order_view

SAMPLE_RATE = 24_000  # OpenAI TTS "pcm" output: 24 kHz, 16-bit, mono
FRAME = SAMPLE_RATE // 100  # 10 ms
SILENCE = bytes(FRAME * 2)


@dataclass
class Transcript:
    lines: list[tuple[float, str, str]] = field(default_factory=list)  # (t, who, text)
    agent_said: asyncio.Event = field(default_factory=asyncio.Event)
    started: float = field(default_factory=time.monotonic)

    def add(self, who: str, text: str) -> None:
        t = time.monotonic() - self.started
        self.lines.append((t, who, text))
        print(f"[{t:6.1f}s] {who:6}: {text}", flush=True)
        if who == "agent":
            self.agent_said.set()


async def synthesize(client: AsyncOpenAI, text: str, voice: str) -> bytes:
    response = await client.audio.speech.create(
        model="gpt-4o-mini-tts", voice=voice, input=text, response_format="pcm"
    )
    return response.content


async def feed(source: rtc.AudioSource, queue: asyncio.Queue[bytes]) -> None:
    """Send queued speech, and silence whenever there's none. capture_frame paces it."""
    pending = b""
    while True:
        if not pending and not queue.empty():
            pending = queue.get_nowait()
        chunk, pending = (pending[: FRAME * 2], pending[FRAME * 2 :]) if pending else (SILENCE, b"")
        chunk = chunk.ljust(FRAME * 2, b"\0")
        await source.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, FRAME))


async def call(lines: list[str], voice: str, wait_s: float) -> int:
    settings = get_settings()
    room_name, identity = new_call_ids()
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    transcript = Transcript()
    room = rtc.Room()

    async def read_transcription(reader: rtc.TextStreamReader, participant_identity: str) -> None:
        text = await reader.read_all()
        final = (reader.info.attributes or {}).get("lk.transcription_final") == "true"
        if final and text.strip():
            transcript.add("caller" if participant_identity == identity else "agent", text.strip())

    tasks: set[asyncio.Task[None]] = set()

    def on_stream(reader: rtc.TextStreamReader, participant_identity: str) -> None:
        task = asyncio.create_task(read_transcription(reader, participant_identity))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("lk.transcription", on_stream)
    await room.connect(settings.livekit_url, join_token(settings, room_name, identity))
    print(f"joined {room_name} as {identity}", flush=True)

    source = rtc.AudioSource(SAMPLE_RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("caller-mic", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    speech: asyncio.Queue[bytes] = asyncio.Queue()
    feeder = asyncio.create_task(feed(source, speech))

    try:
        await asyncio.wait_for(transcript.agent_said.wait(), timeout=30)  # the greeting
        for line in lines:
            transcript.agent_said.clear()
            await speech.put(await synthesize(client, line, voice))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(transcript.agent_said.wait(), timeout=wait_s)
            await asyncio.sleep(2.0)  # let the agent finish speaking before the next line
    finally:
        feeder.cancel()
        await room.disconnect()

    menu = load_menu()
    async with await PostgresOrderStore.connect(settings.database_url) as store:
        await asyncio.sleep(1.0)
        order = await store.get(room_name)
    if order is None:
        print("no order saved for this session")
        return 1
    view = order_view(Session(menu=menu, order=order))
    items = [x["description"] for x in view["lines"]]
    print(f"order {view['status']}: {items}, total {view['total']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("lines", nargs="+", help="what the caller says, one turn each")
    parser.add_argument("--voice", default="alloy")
    parser.add_argument("--wait", type=float, default=25.0, help="seconds to wait for each reply")
    args = parser.parse_args()
    return asyncio.run(call(args.lines, args.voice, args.wait))


if __name__ == "__main__":
    sys.exit(main())
