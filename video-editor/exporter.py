import os
import subprocess
import json
import tempfile
import csv
from timeline import Segment, format_timeline_for_display

def get_file_duration_ffprobe(video_path):
    cmd = ["ffprobe","-v","quiet","-print_format","json","-show_format",video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        return float(data.get("format",{}).get("duration",0))
    except Exception:
        return 0.0

def render_video(segments, output_path, progress_callback=None, video_codec="libx264", audio_codec="aac", crf=18, resolution=None):
    if not segments:
        raise ValueError("Nessun segmento da esportare")
    total_segs = len(segments)
    tmp_dir = tempfile.mkdtemp()
    segment_files = []
    concat_list = os.path.join(tmp_dir, "concat.txt")
    try:
        for i, seg in enumerate(segments):
            if progress_callback:
                progress_callback(int((i/total_segs)*60), f"Taglio segmento {i+1}/{total_segs}...")
            seg_output = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
            vf = ["-vf", f"scale={resolution.replace('x',':')}:force_original_aspect_ratio=decrease"] if resolution else []
            cmd = ["ffmpeg","-y","-ss",str(seg.start),"-i",seg.video_path,"-t",str(seg.duration)] + vf + ["-c:v",video_codec,"-crf",str(crf),"-preset","fast","-c:a",audio_codec,"-b:a","192k","-avoid_negative_ts","1",seg_output]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg errore segmento {i}: {result.stderr[-300:]}")
            segment_files.append(seg_output)
        if progress_callback:
            progress_callback(65, "Unisco i segmenti...")
        with open(concat_list, "w", encoding="utf-8") as f:
            for sf in segment_files:
                f.write(f"file '{sf.replace(chr(92),'/')}'\n")
        if progress_callback:
            progress_callback(70, "Rendering finale...")
        cmd_concat = ["ffmpeg","-y","-f","concat","-safe","0","-i",concat_list,"-c","copy",output_path]
        result = subprocess.run(cmd_concat, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg errore concat: {result.stderr[-300:]}")
        if progress_callback:
            progress_callback(100, "Esportazione completata!")
        return True
    finally:
        for sf in segment_files:
            try: os.remove(sf)
            except: pass
        try: os.remove(concat_list)
        except: pass
        try: os.rmdir(tmp_dir)
        except: pass

def export_fcpxml(segments, output_path, project_name="WeddingCut", frame_rate="25"):
    fr = int(frame_rate)
    total_frames = int(sum(s.duration for s in segments) * fr)
    unique_files = {}
    asset_id = 2
    lines = ['<?xml version="1.0" encoding="UTF-8"?>','<!DOCTYPE fcpxml>','<fcpxml version="1.9">','  <resources>',f'    <format id="r1" name="FFVideoFormat{frame_rate}p" frameDuration="1/{fr}s" width="1920" height="1080"/>']
    for seg in segments:
        if seg.video_path not in unique_files:
            uid = f"r{asset_id}"
            unique_files[seg.video_path] = uid
            name = os.path.basename(seg.video_path)
            url = "file:///" + seg.video_path.replace("\\","/").replace(" ","%20")
            dur = int(get_file_duration_ffprobe(seg.video_path) * fr)
            lines += [f'    <asset id="{uid}" name="{name}" start="0s" duration="{dur}/{fr}s" hasVideo="1" hasAudio="1" format="r1">',f'      <media-rep kind="original-media" src="{url}"/>','    </asset>']
            asset_id += 1
    lines += ['  </resources>','  <library>',f'    <event name="{project_name}">',f'      <project name="{project_name}">',f'        <sequence duration="{total_frames}/{fr}s" format="r1" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">','          <spine>']
    offset = 0
    for seg in segments:
        ref = unique_files[seg.video_path]
        sf = int(round(seg.start * fr))
        df = int(round(seg.duration * fr))
        lines.append(f'            <asset-clip ref="{ref}" name="{os.path.basename(seg.video_path)}" offset="{offset}/{fr}s" start="{sf}/{fr}s" duration="{df}/{fr}s" format="r1" audioRole="dialogue"/>')
        offset += df
    lines += ['          </spine>','        </sequence>','      </project>','    </event>','  </library>','</fcpxml>']
    with open(output_path,"w",encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True

def export_edl(segments, output_path, project_name="WeddingCut", frame_rate=25):
    def tc(secs):
        tf = int(round(secs * frame_rate))
        return f"{tf//3600//frame_rate:02d}:{(tf//frame_rate%3600)//60:02d}:{tf//frame_rate%60:02d}:{tf%frame_rate:02d}"
    lines = [f"TITLE: {project_name}", "FCM: NON-DROP FRAME", ""]
    pos = 0.0
    for i, seg in enumerate(segments):
        tape = os.path.splitext(os.path.basename(seg.video_path))[0][:8].upper()
        lines.append(f"{i+1:03d}  {tape:<8} AA/V  C  {tc(seg.start)} {tc(seg.end)} {tc(pos)} {tc(pos+seg.duration)}")
        lines.append(f"* FROM CLIP NAME: {os.path.basename(seg.video_path)}")
        lines.append("")
        pos += seg.duration
    with open(output_path,"w",encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True

def export_csv(segments, output_path):
    items = format_timeline_for_display(segments)
    with open(output_path,"w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["N","File sorgente","Inizio (s)","Fine (s)","Durata (s)","Pos. timeline (s)","Tipo","Score"], delimiter=";")
        w.writeheader()
        for item in items:
            w.writerow({"N":item["index"],"File sorgente":item["source_file"],"Inizio (s)":item["source_start"],"Fine (s)":item["source_end"],"Durata (s)":item["duration"],"Pos. timeline (s)":item["timeline_start"],"Tipo":item["type"],"Score":item["score"]})
    return True

def export_transcript(analyses, output_path):
    with open(output_path,"w",encoding="utf-8") as f:
        for analysis in analyses:
            f.write(f"=== {analysis['filename']} ===\n\n")
            for seg in analysis.get("transcription",{}).get("segments",[]):
                ms, me = int(seg["start"]//60), int(seg["end"]//60)
                ss, se = seg["start"]%60, seg["end"]%60
                f.write(f"[{ms:02d}:{ss:05.2f} --> {me:02d}:{se:05.2f}]  {seg['text']}\n")
                if seg.get("fillers"):
                    f.write(f"  Filler: {', '.join(w['word'] for w in seg['fillers'])}\n")
            f.write("\n")
    return True
