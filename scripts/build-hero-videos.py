"""Cut the existing hero recordings into short, fast-start browser videos.

Requires FFmpeg on PATH or the imageio-ffmpeg Python package.
Only trims, retimes and arranges the supplied recordings; no new physics is rendered.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts/hero-media.json"


def locate_ffmpeg(explicit):
    if explicit or shutil.which("ffmpeg"):
        return explicit or shutil.which("ffmpeg")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def retime(start, end, duration, fps):
    frames = round(duration * fps)
    assert abs(frames / fps - duration) < 1e-8
    return (f"trim=start={start}:end={end},setpts=(PTS-STARTPTS)*{duration / (end - start):.12f},"
            f"fps={fps},tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={frames},"
            f"setpts=N/({fps}*TB),setsar=1")


def encode(ffmpeg, inputs, graph, output, frames, fps):
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "4"]
    for source in inputs:
        command += ["-i", str(source)]
    command += ["-filter_complex", graph, "-map", "[out]", "-an", "-c:v", "libx264",
                "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
                "-frames:v", str(frames), "-threads", "4", "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)


def build_clip(ffmpeg, clip, fps, font):
    segments = clip["segments"]
    parallel = clip.get("parallel_controls")
    count = len(segments) + (2 if parallel else 0)
    graph = [f"[0:v]split={count}" + "".join(f"[s{i}]" for i in range(count))]
    labels = []
    for i, (start, end, duration) in enumerate(segments):
        label = f"v{i}"
        graph.append(f"[s{i}]" + retime(start, end, duration, fps) + f"[{label}]")
        labels.append(label)
    if parallel:
        for i, name in enumerate(["dials", "shutter"]):
            start, end, w, h, x, y = parallel[name]
            label = "Two dials" if name == "dials" else "Shutter press"
            overlay = (f",drawtext=fontfile={font}:text='{label}':fontcolor=white:fontsize=34:"
                       "box=1:boxcolor=0x142229@0.8:boxborderw=14:x=32:y=h-th-36") if font else ""
            graph.append(f"[s{len(segments)+i}]" + retime(start, end, parallel["duration"], fps)
                         + f",crop={w}:{h}:{x}:{y},scale=960:1080{overlay}[{name}]")
        graph.append("[dials][shutter]hstack=inputs=2,drawbox=x=958:y=0:w=4:h=ih:color=0xe6eeea@0.8:t=fill[controls]")
        labels.insert(parallel["insert_before_segment"], "controls")
    graph.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=1:a=0,format=yuv420p[out]")
    total = sum(segment[2] for segment in segments) + (parallel["duration"] if parallel else 0)
    assert abs(total - clip["duration"]) < 1e-8 and total < 10
    encode(ffmpeg, [ROOT / "website/assets/hero" / (clip["original_key"] + ".mp4")],
           ";".join(graph), ROOT / clip["output"], round(total * fps), fps)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg")
    parser.add_argument("--only", choices=["camera", "trifold", "globe", "ladder", "carousel", "overview"])
    args = parser.parse_args()
    os.chdir(ROOT)
    ffmpeg = locate_ffmpeg(args.ffmpeg)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    fps = config["fps"]
    work = Path(subprocess.check_output(["git", "rev-parse", "--git-path", "video-work"], text=True).strip())
    work.mkdir(parents=True, exist_ok=True)
    font_source = next((p for p in [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")] if p.is_file()), None)
    font = None
    if font_source:
        shutil.copyfile(font_source, work / "hero-font.ttf")
        font = (work / "hero-font.ttf").as_posix()
    for name, clip in config["clips"].items():
        if args.only and args.only != name:
            continue
        build_clip(ffmpeg, clip, fps, font)
        print(f"{name}: {clip['duration']:.1f}s, {(ROOT / clip['output']).stat().st_size} bytes", flush=True)
    if args.only and args.only != "overview":
        return
    overview = config["overview"]
    inputs, graph, labels = [], [], []
    for i, chapter in enumerate(overview["chapters"]):
        clip = config["clips"][chapter["key"]]
        inputs.append(ROOT / clip["output"])
        graph.append(f"[{i}:v]" + retime(0, clip["duration"], chapter["end"]-chapter["start"], fps) + f"[v{i}]")
        labels.append(f"[v{i}]")
    graph.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0,format=yuv420p[out]")
    encode(ffmpeg, inputs, ";".join(graph), ROOT / overview["output"], round(overview["duration"] * fps), fps)
    print(f"overview: {overview['duration']}s, {(ROOT / overview['output']).stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
