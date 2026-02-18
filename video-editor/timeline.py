import os

class Segment:
    def __init__(self, video_path, start, end, clip_label="", segment_type="speech"):
        self.video_path = video_path
        self.start = start
        self.end = end
        self.duration = end - start
        self.clip_label = clip_label
        self.segment_type = segment_type
        self.score = 0.0
        self.keep = True

    def to_dict(self):
        return {"video_path": self.video_path, "start": round(self.start,3), "end": round(self.end,3), "duration": round(self.duration,3), "clip_label": self.clip_label, "segment_type": self.segment_type, "score": round(self.score,3), "keep": self.keep}

def build_segments_from_analysis(analysis):
    video_path = analysis["video_path"]
    label = analysis["filename"]
    duration = analysis["duration"]
    silences = analysis.get("silences", [])
    fillers = analysis.get("filler_segments", [])
    best_scenes = analysis.get("best_scenes", [])

    bad_intervals = []
    for s in silences:
        bad_intervals.append((s["start"], s["end"], "silence"))
    for f in fillers:
        bad_intervals.append((max(0, f["start"]-0.1), f["end"]+0.1, "filler"))
    bad_intervals.sort(key=lambda x: x[0])

    segments = []
    current_pos = 0.0
    for bad_start, bad_end, bad_type in bad_intervals:
        bad_start = max(bad_start, 0.0)
        bad_end = min(bad_end, duration)
        if bad_start > current_pos + 0.05:
            seg = Segment(video_path, current_pos, bad_start, label, "speech")
            segments.append(seg)
        bad_seg = Segment(video_path, bad_start, bad_end, label, bad_type)
        bad_seg.keep = False
        segments.append(bad_seg)
        current_pos = max(current_pos, bad_end)
    if current_pos < duration - 0.1:
        segments.append(Segment(video_path, current_pos, duration, label, "speech"))

    best_timestamps = {round(b["timestamp"],1): b["score"] for b in best_scenes}
    for seg in segments:
        if seg.keep:
            center = (seg.start + seg.end) / 2
            for ts, sc in best_timestamps.items():
                if abs(center - ts) < 2.0:
                    seg.score = sc
                    break
    return segments

def auto_cut_timeline(analyses, options=None):
    if options is None:
        options = {}
    remove_silences = options.get("remove_silences", True)
    remove_fillers = options.get("remove_fillers", True)
    min_seg_dur = options.get("min_segment_duration", 0.3)
    max_duration = options.get("max_total_duration", None)
    padding = options.get("padding_seconds", 0.05)

    all_segments = []
    for analysis in analyses:
        segs = build_segments_from_analysis(analysis)
        for seg in segs:
            if seg.keep:
                seg.start = seg.start + padding
                seg.end = seg.end - padding
                seg.duration = seg.end - seg.start
            if not seg.keep:
                continue
            if seg.duration < min_seg_dur:
                continue
            if seg.segment_type == "silence" and remove_silences:
                continue
            if seg.segment_type == "filler" and remove_fillers:
                continue
            all_segments.append(seg)

    if max_duration:
        selected = []
        total = 0.0
        for seg in all_segments:
            if total + seg.duration > max_duration:
                remaining = max_duration - total
                if remaining > min_seg_dur:
                    clipped = Segment(seg.video_path, seg.start, seg.start+remaining, seg.clip_label, seg.segment_type)
                    clipped.score = seg.score
                    selected.append(clipped)
                break
            selected.append(seg)
            total += seg.duration
        all_segments = selected

    return all_segments

def sync_to_beats(segments, beat_times, tolerance=0.15):
    if not beat_times:
        return segments
    def nearest_beat(t):
        best = min(beat_times, key=lambda b: abs(b-t))
        return best if abs(best-t) <= tolerance else t
    snapped = []
    for seg in segments:
        ns = nearest_beat(seg.start)
        ne = nearest_beat(seg.end)
        if ne <= ns:
            ne = seg.end
        new_seg = Segment(seg.video_path, ns, ne, seg.clip_label, seg.segment_type)
        new_seg.score = seg.score
        new_seg.keep = seg.keep
        snapped.append(new_seg)
    return snapped

def timeline_stats(segments):
    if not segments:
        return {"total_duration": 0, "n_segments": 0}
    total = sum(s.duration for s in segments)
    by_type = {}
    for seg in segments:
        by_type[seg.segment_type] = by_type.get(seg.segment_type, 0) + seg.duration
    return {"total_duration": round(total,2), "n_segments": len(segments), "by_type": {k: round(v,2) for k,v in by_type.items()}, "avg_segment_duration": round(total/len(segments),2)}

def format_timeline_for_display(segments):
    result = []
    pos = 0.0
    for i, seg in enumerate(segments):
        result.append({"index": i+1, "source_file": seg.clip_label, "source_start": round(seg.start,2), "source_end": round(seg.end,2), "duration": round(seg.duration,2), "timeline_start": round(pos,2), "timeline_end": round(pos+seg.duration,2), "type": seg.segment_type, "score": round(seg.score,1)})
        pos += seg.duration
    return result
