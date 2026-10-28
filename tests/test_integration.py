"""Customer WAV -> STT -> facts -> translate -> TTS -> rider, through the real Gnani client.

Only the network (respx) and the model (fake translator) are replaced, so the loudness step, the
streaming-WAV repair and the room routes are exercised together.
"""

import httpx
import numpy as np
import pytest
import respx
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.gnani import STT_PATH, TTS_PATH, GnaniClient
from saathi.rooms import RoomManager
from test_loudness import RATE, decode, peak_dbfs, rms_dbfs, tone
from wavs import make_streaming_wav, make_wav

BASE = "https://api.test"


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return "kannada text"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@respx.mock
async def test_turn_reaches_the_rider_with_normalized_audio() -> None:
    respx.post(f"{BASE}{STT_PATH}").mock(
        return_value=httpx.Response(
            200, json={"success": True, "transcript": "gate number 2 near the blue temple"}
        )
    )
    quiet_speech = tone(0.02).tobytes()
    respx.post(f"{BASE}{TTS_PATH}").mock(
        return_value=httpx.Response(200, content=make_streaming_wav(quiet_speech, rate=RATE))
    )
    settings = Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE)
    gnani = GnaniClient(settings)
    manager = RoomManager(max_rooms=3)
    app = create_app(settings, gnani, FakeTranslator(), manager)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://saathi"
    ) as client:
        created = (await client.post("/rooms", json={"language": "en"})).json()
        joined = (
            await client.post(f"/rooms/{created['code']}/join", json={"language": "kn"})
        ).json()
        rider_queue = manager.subscribe(
            manager.authorize(created["code"], joined["token"]).room, "rider"
        )

        turn = await client.post(
            f"/rooms/{created['code']}/turn",
            files={"audio": ("a.wav", make_wav(), "audio/wav")},
            headers=auth(created["token"]),
        )
        assert turn.status_code == 200
        event = rider_queue.get_nowait()
        assert event is not None and event.name == "turn"
        assert event.data["translation"] == "kannada text"
        assert event.data["facts"][0]["kind"] == "gate"

        audio = await client.get(event.data["audio_path"], headers=auth(joined["token"]))

    served = decode(audio.content)
    assert rms_dbfs(served) == pytest.approx(-18.0, abs=0.5)
    assert peak_dbfs(served) <= -0.99
    assert np.isfinite(served).all()
    await gnani.aclose()
