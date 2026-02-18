import os
import json
import subprocess
import tempfile
import wave
import struct
import math

def extract_audio(video_path, output_wav=None):
    if output_wav is None:
        output_wav = tempfile.mktemp(suffix=".wav")
    cmd = ["ffmpeg","-y","-i",video_path,"-ar","16000","-ac","1","-vn",output_wav]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg errore: {result.stderr}")
    return output_wav

def get_video_duration(video_path):
    cmd = ["ffprobe","-v","quiet","-print_format","json","-show_format",video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    data = json.loads(result.stdout)
    return float(data.get("format",{}).get("duration",0))

def read_wav_samples(wav_path):
    with wave.open(wav_path,"rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if sample_width == 2:
        samples_all = list(struct.unpack(f"<{n_frames*n_channels}h", raw))
    else:
        samples_all = [s-128 for s in struct.unpack(f"{n_frames*n_channels}B", raw)]
    if n_channels > 1:
        samples = [sum(samples_all[i:i+n_channels])/n_channels for i in range(0,len(samples_all),n_channels)]
    else:
        samples = samples_all
    return samples, framerate

def compute_rms(samples, start, end):
    chunk = samples[start:end]
    if not chunk:
        return 0.0
    return math.sqrt(sum(s*s for s in chunk)/len(chunk))

def detect_silences(wav_path, silence_threshold_db=-40.0, min_silence_duration=0.5, frame_duration=0.02):
    samples, sr = read_wav_samples(wav_path)
    frame_size = int(sr * frame_duration)
    n_frames = len(samples) // frame_size
    threshold = 32767.0 * (10 ** (silence_threshold_db / 20.0)) if silence_threshold_db > -96 else 0.0
    is_silent = [compute_rms(samples, i*frame_size, (i+1)*frame_size) < threshold for i in range(n_frames)]
    silences = []
    in_silence = False
    silence_start = 0.0
    for i, silent in enumerate(is_silent):
        t = i * frame_duration
        if silent and not in_silence:
            in_silence = True
            silence_start = t
        elif not silent and in_silence:
            in_silence = False
            dur = t - silence_start
            if dur >= min_silence_duration:
                silences.append({"start": silence_start, "end": t, "duration": dur, "type": "silence"})
    if in_silence:
        dur = n_frames*frame_duration - silence_start
        if dur >= min_silence_duration:
            silences.append({"start": silence_start, "end": n_frames*frame_duration, "duration": dur, "type": "silence"})
    return silences

FILLER_WORDS_IT = ["ehm","ehmm","uh","uhh","ah","ahh","allora","tipo","cioè","praticamente","diciamo","insomma","ecco","dunque","vabbè","boh","mah"]
FILLER_WORDS_EN = ["um","uh","uhh","er","ah","like","you know","basically","literally","actually","so","right","i mean","well"]

def transcribe_with_whisper(wav_path, language="it", model_size="base"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"text":"","segments":[],"filler_segments":[],"error":"faster-whisper non installato"}
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments_raw, info = model.transcribe(wav_path, language=language, word_timestamps=True, vad_filter=True)
    segments = []
    filler_segments = []
    full_text = []
    filler_list = FILLER_WORDS_IT if language == "it" else FILLER_WORDS_EN
    for seg in segments_raw:
        words = []
        seg_fillers = []
        if seg.words:
            for w in seg.words:
                wi = {"word": w.word.strip(), "start": w.start, "end": w.end, "probability": w.probability}
                words.append(wi)
                wl = w.word.strip().lower()
                if any(wl == f or wl.startswith(f) for f in filler_list):
                    filler_segments.append({"start": w.start, "end": w.end, "word": w.word.strip(), "type": "filler"})
                    seg_fillers.append(wi)
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip(), "words": words, "fillers": seg_fillers})
        full_text.append(seg.text.strip())
    return {"text": " ".join(full_text), "segments": segments, "filler_segments": filler_segments, "language": info.language, "duration": info.duration}

def detect_best_scenes(video_path, sample_every_n_seconds=2.0, top_percent=0.3):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        return []
    frame_interval = int(fps * sample_every_n_seconds)
    scores = []
    frame_idx = 0
    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = float(np.mean(gray))
        bs = 1.0 if 80 <= brightness <= 170 else (0.3 if brightness < 50 or brightness > 210 else 0.7)
        scores.append({"timestamp": frame_idx/fps, "score": sharpness*bs, "type": "scene_score"})
        frame_idx += frame_interval
    cap.release()
    if not scores:
        return []
    scores.sort(key=lambda x: x["score"], reverse=True)
    best = scores[:max(1, int(len(scores)*top_percent))]
    for s in best:
        s["type"] = "best_scene"
    best.sort(key=lambda x: x["timestamp"])
    return best

def detect_music_beats(audio_path):
    try:
        import librosa
    except ImportError:
        return []
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    return librosa.frames_to_time(beat_frames, sr=sr).tolist()

def analyze_clip(video_path, options=None):
    if options is None:
        options = {}
    results = {"video_path": video_path, "filename": os.path.basename(video_path), "duration": 0.0, "silences": [], "transcription": {}, "filler_segments": [], "best_scenes": [], "beat_times": [], "errors": []}
    results["duration"] = get_video_duration(video_path)
    tmp_wav = tempfile.mktemp(suffix=".wav")
    try:
        extract_audio(video_path, tmp_wav)
    except Exception as e:
        results["errors"].append(str(e))
        return results
    try:
        results["silences"] = detect_silences(tmp_wav, options.get("silence_threshold_db",-40.0), options.get("min_silence_duration",0.5))
        if options.get("run_transcription", True):
            trans = transcribe_with_whisper(tmp_wav, options.get("transcription_language","it"), options.get("whisper_model","base"))
            results["transcription"] = trans
            results["filler_segments"] = trans.get("filler_segments",[])
        if options.get("run_scene_detection", True):
            results["best_scenes"] = detect_best_scenes(video_path)
        if options.get("run_beat_detection", False) and options.get("audio_file_for_beats"):
            results["beat_times"] = detect_music_beats(options["audio_file_for_beats"])
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)
    return results

def save_analysis(results, output_path):
    with open(output_path,"w",encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

def load_analysis(json_path):
    with open(json_path,"r",encoding="utf-8") as f:
        return json.load(f)
