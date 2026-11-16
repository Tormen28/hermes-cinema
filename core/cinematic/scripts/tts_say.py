#!/usr/bin/env python3
"""Record every take in script.json with a local voice: a free scratch track to time the film against.

The film is timed to the voiceover, so the picture cannot be built before there is a voice. A
scratch track from the system voice costs nothing, gives real timings, and is replaced later by
the final voice (any TTS or a human): the scene re-times itself because it asks for line starts
and spoken words, never fixed seconds.

  python3 tts_say.py --project my-film                       # macOS `say`, or espeak-ng on Linux
  python3 tts_say.py --project my-film --voice Daniel --rate 165
  python3 tts_say.py --project my-film --cmd 'piper -m en_US-lessac-medium.onnx -f {out} < {txt}'

--cmd runs any command-line TTS once per take, as an argv list and never through a shell (a
trailing `< {txt}` feeds the text on stdin; pipes and `>` are not supported). {txt} is a text file
with the take's lines (one per paragraph), {out} the WAV it must write. Each take is read in one go so the delivery stays even;
split_takes.py then cuts it into lines. Writes audio/takes/<take>.wav.
"""
import argparse
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


def run(cmd, stdin_path=None):
    """Run an argv list (never through a shell). `stdin_path` feeds a file to the command."""
    stdin = open(stdin_path, "rb") if stdin_path else None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=stdin)
    finally:
        if stdin:
            stdin.close()
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")
    return r.stdout


def build_argv(template, txt, out, posix=None):
    """Turn a --cmd template into (argv, stdin_path) without a shell.

    The template is split into words first and {txt}/{out} are substituted into each word
    afterwards, so a path with spaces or shell characters stays one argument and nothing is
    ever interpreted by a shell. A trailing `< {txt}` is honoured as stdin redirection (the one
    shell feature the examples use); pipes, `>` and `&&` are not supported: wrap them in a script.
    """
    posix = (os.name != "nt") if posix is None else posix
    words = shlex.split(template, posix=posix)
    if not posix:  # the non-POSIX split keeps the quotes around a quoted word and the backslashes
        words = [w[1:-1] if len(w) >= 2 and w[0] == w[-1] and w[0] in "\"'" else w for w in words]
    argv, stdin_path, i = [], None, 0
    while i < len(words):
        w = words[i]
        if w == "<" and i + 1 < len(words):
            stdin_path = words[i + 1].replace("{txt}", str(txt)).replace("{out}", str(out))
            i += 2
            continue
        argv.append(w.replace("{txt}", str(txt)).replace("{out}", str(out)))
        i += 1
    if not argv:
        sys.exit("--cmd is empty")
    return argv, stdin_path


def to_wav(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "48000", "-ac", "1", str(dst)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--voice", default=None, help="say / espeak-ng voice name")
    ap.add_argument("--rate", type=int, default=165, help="words per minute (documentary pace is 150-170)")
    ap.add_argument("--pause", type=int, default=650, help="pause between lines, ms (split_takes.py cuts there)")
    ap.add_argument("--cmd", default=None, help="any TTS command with {txt} and {out} placeholders")
    ap.add_argument("--only", default="", help="comma-separated take names to (re)record")
    a = ap.parse_args()

    proj = pathlib.Path(a.project)
    script = json.loads((proj / "script.json").read_text())
    tdir = proj / "audio" / "takes"; tdir.mkdir(parents=True, exist_ok=True)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    engine = "cmd" if a.cmd else "say" if shutil.which("say") else "espeak-ng" if shutil.which("espeak-ng") else None
    if engine is None:
        sys.exit("no local voice: install espeak-ng (apt install espeak-ng), or pass --cmd for your TTS, "
                 "or record takes elsewhere and save them as audio/takes/<take>.wav")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for take in script["takes"]:
            name = take["take"]
            # El nombre viene del script.json del proyecto: se valida antes de
            # meterlo en una ruta o en el comando de voz (que corre por shell).
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", str(name)):
                sys.exit(f"take name {name!r} is not a safe identifier: [A-Za-z0-9][A-Za-z0-9_-]*, max 64")
            if only and name not in only:
                continue
            lines = [l["spoken"].strip() for l in take["lines"]]
            out = tdir / f"{name}.wav"
            if engine == "say":
                text = f" [[slnc {a.pause}]] ".join(lines)
                raw = tmp / f"{name}.aiff"
                cmd = ["say", "-r", str(a.rate), "-o", str(raw)] + (["-v", a.voice] if a.voice else []) + [text]
                run(cmd); to_wav(raw, out)
            elif engine == "espeak-ng":
                ssml = "<speak>" + f"<break time='{a.pause}ms'/>".join(lines) + "</speak>"
                raw = tmp / f"{name}.wav"
                cmd = ["espeak-ng", "-m", "-s", str(a.rate), "-w", str(raw)] + (["-v", a.voice] if a.voice else []) + [ssml]
                run(cmd); to_wav(raw, out)
            else:
                txt = tmp / f"{name}.txt"; txt.write_text("\n\n".join(lines) + "\n")
                raw = tmp / f"{name}_raw.wav"
                argv, stdin_path = build_argv(a.cmd, txt, raw)
                run(argv, stdin_path=stdin_path)
                to_wav(raw, out)
            dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]))
            print(f"{name:<20} {len(lines)} lines  {dur:5.1f}s  -> {out}")


if __name__ == "__main__":
    main()
