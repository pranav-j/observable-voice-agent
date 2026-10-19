"""`python deploy/smoke_call.py <host>`: place a call to the live demo and check the agent answers.

It joins the way the web page does: a token from the API, WebRTC through LiveKit. It
passes once the agent has joined and its greeting has arrived as audio and as text, which
covers the API, signalling, the media path, dispatch, the worker and text-to-speech. The
call says nothing, so it costs no LLM tokens and ends itself when the agent gives up on
the silence. It does count against the demo's per-address call limit.
"""

import asyncio
import json
import sys
import time
import urllib.request

from livekit import rtc

GREETING_TIMEOUT_S = 40.0  # longer than the web page's redispatch, so a retry can land


def fetch_token(host: str) -> dict[str, str]:
    request = urllib.request.Request(f"https://{host}/api/token", method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        token: dict[str, str] = json.loads(response.read())
    return token


async def smoke(token: dict[str, str]) -> bool:
    room = rtc.Room()
    tasks: set[asyncio.Future[None]] = set()  # keep references until they finish
    agent: list[str] = []
    frames = 0
    greeting = asyncio.get_running_loop().create_future()

    @room.on("participant_connected")
    def joined(participant: rtc.RemoteParticipant) -> None:
        agent.append(participant.identity)

    @room.on("track_subscribed")
    def subscribed(track: rtc.Track, *_: object) -> None:
        async def count() -> None:
            nonlocal frames
            async for _ in rtc.AudioStream(track):
                frames += 1

        if track.kind == rtc.TrackKind.KIND_AUDIO:
            task = asyncio.ensure_future(count())
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def read(reader: rtc.TextStreamReader) -> None:
        text = (await reader.read_all()).strip()
        final = (reader.info.attributes or {}).get("lk.transcription_final") == "true"
        if final and text and not greeting.done():
            greeting.set_result(text)

    def on_text(reader: rtc.TextStreamReader, _who: str) -> None:
        task = asyncio.ensure_future(read(reader))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("lk.transcription", on_text)
    started = time.monotonic()
    await room.connect(token["url"], token["token"])
    try:
        said = await asyncio.wait_for(greeting, GREETING_TIMEOUT_S)
    except TimeoutError:
        said = ""
    await asyncio.sleep(1.0)  # let the rest of the greeting's audio arrive
    await room.disconnect()
    ok = bool(agent and frames and said)
    print(
        f"room {token['room']}: agent {agent[0] if agent else 'never joined'}, "
        f"{frames} audio frames, greeting after {time.monotonic() - started:.1f}s"
    )
    print(f"  {said!r}" if said else "  no greeting")
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python deploy/smoke_call.py <host>")
    sys.exit(0 if asyncio.run(smoke(fetch_token(sys.argv[1]))) else 1)
