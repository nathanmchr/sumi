"""Bounded, isolated experiments; never writes the production audio directory."""

import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import time
import wave

import numpy as np

from generate_vocab_audio_google import ROOT_DIR, create_google_client


def metrics(audio: bytes) -> dict:
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getsampwidth() == 2 and wav.getnchannels() == 1
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32768
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    return {
        "seconds": len(samples) / rate,
        "peak_dbfs": round(20 * math.log10(max(peak, 1e-10)), 2),
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-10)), 2),
        "near_silent_screen": peak < 10 ** (-35 / 20),
    }


def experiment_matrix(suite: str = "baseline") -> list[dict]:
    path = ROOT_DIR / "audio/vocabulary-chirp3-yomigana/manifest.json"
    manifest = json.loads(path.read_text())
    records = {e["id"]: e for group in manifest.values() for e in group}
    cases = []
    for slug, identity in (
        ("ee", "47355133-d6d1-5df3-bb24-2cea6ae1a385"),
        ("san", "815d9e39-02bb-5f36-b28b-251e0adabbfc"),
        ("hai_control", "ccecb3d1-c563-5b48-ae0d-f88de1044d09"),
    ):
        record = records[identity]
        word = record["reading"]
        variants = {"original": record["request"]["input"]}
        if suite == "reproduce":
            if slug == "hai_control":
                continue
            variants["voice_kore"] = record["request"]["input"]
        elif slug != "hai_control":
            variants.update({
                "text": {"text": word + "。"},
                "plain_ssml": {"ssml": f"<speak>{word}。</speak>"},
                "phoneme_no_stop": {"ssml": record["request"]["input"]["ssml"].replace("。</speak>", "</speak>")},
            })
        for variant, speech in variants.items():
            repeats = 10 if suite == "reproduce" and variant == "original" else 3
            for repeat in range(1, repeats + 1):
                request = copy.deepcopy(record["request"])
                request["input"] = speech
                if variant == "voice_kore":
                    request["voice"]["name"] = "ja-JP-Chirp3-HD-Kore"
                cases.append({"case": f"{slug}-{variant}-{repeat}", "word": word, "variant": variant, "repeat": repeat, "request": request})
    # Interleave variants and words to avoid confounding with run order.
    return sorted(cases, key=lambda case: (case["repeat"], case["variant"], case["word"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly authorize the bounded Google calls")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", choices=("baseline", "reproduce"), default="baseline")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.is_relative_to((ROOT_DIR / "audio").resolve()):
        parser.error("Experiments cannot write under the production audio root")
    cases = experiment_matrix(args.suite)
    chars = sum(len(next(iter(c["request"]["input"].values()))) for c in cases)
    print(json.dumps({"calls": len(cases), "characters": chars, "indicative_usd_before_free_tier": chars * .00003}), flush=True)
    if not args.run:
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        return
    # Refuse any reuse/overwrite so experiment identities remain auditable.
    output.mkdir(parents=True, exist_ok=False)
    (output / "requests.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2))
    client, tts, _ = create_google_client()
    with (output / "results.jsonl").open("x") as log:
        for case in cases:
            start = time.monotonic()
            result = {**case, "pronunciation_verified": False}
            try:
                response = client.synthesize_speech(request=tts.SynthesizeSpeechRequest(**case["request"]), retry=None, timeout=30)
                content = response.audio_content
                file = output / f"{case['case']}.wav"
                with file.open("xb") as stream:
                    stream.write(content)
                result.update({"audio_file": file.name, "sha256": hashlib.sha256(content).hexdigest(), **metrics(content)})
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps({k: v for k, v in result.items() if k != "request"}, ensure_ascii=False), flush=True)
            time.sleep(max(0, .4 - (time.monotonic() - start)))


if __name__ == "__main__":
    main()
