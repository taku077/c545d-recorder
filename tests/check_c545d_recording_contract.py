#!/usr/bin/env python3
"""Static production-pipeline invariants; no camera/media runtime assertions."""
import argparse
from pathlib import Path


def check(raw: str) -> dict:
    text = raw.lstrip("\ufeff").replace("\r\n", "\n")
    output = text[text.index("Add-Gst @(\n    'compositor'"):text.index("function Add-Input(")]
    for key, value in {
        "left_x": "'sink_0::xpos=0'",
        "right_x": "'sink_1::xpos=1280'",
        "resolution_fps": "'video/x-raw,width=2560,height=720,framerate=15/1'",
        "x264_quality": "'x264enc','pass=qual','quantizer=24','bitrate=15000'",
        "medium": "'speed-preset=medium'",
        "mux": "'splitmuxsink','name=mux'",
        "hourly": "'max-size-time=3600000000000'",
        "sync_mux": "'async-finalize=false'",
        "keyframe_split": "'send-keyframe-requests=true'",
    }.items():
        if output.count(value) != 1:
            raise ValueError("Production output contract changed: " + key)

    inputs = text[text.index("function Add-Input("):text.index("Add-Input 'cam1'")]
    for key, value in {
        "tcp": "'protocols=tcp'",
        "ntp": "'ntp-sync=true','tcp-timestamp=true'",
        "h264": "'application/x-rtp,media=video,encoding-name=H264'",
        "full_au": "'rtph264depay'",
        "input_geometry": "'video/x-raw,format=I420,width=1280,height=720,framerate=15/1'",
        "audio_one_stream": "if ($side -eq 0)",
        "aac_mux": "'aacparse','!','mux.audio_0'",
        "unused_audio_drop": "'fakesink','async=false','sync=false','enable-last-sample=false'",
    }.items():
        if inputs.count(value) != 1:
            raise ValueError("Production stream contract changed: " + key)

    for key, value in {
        "wide_stream": ':554/stream1"',
        "tele_stream": ':554/stream6"',
        "cam1_left": "Add-Input 'cam1' $wideURL 0",
        "cam2_right": "Add-Input 'cam2' $teleURL 1",
        "prefer_avdec_h264": "'auto' { $decoderCandidates = @('avdec_h264','openh264dec','decodebin') }",
        "aac_48k_mono": "channels=1,rate=48000",
        "aac_bitrate": "'bitrate=192000'",
        "eos": "$gstArgs = @('-e') + $pipeline.ToArray()",
        "stop_marker": "if (Test-C545DStopRequested)",
    }.items():
        if value not in text:
            raise ValueError("Source invariant changed: " + key)
    return {
        "static_contract": "PASS",
        "streams": 2,
        "resolution": "2560x720",
        "fps": 15,
        "qp": 24,
        "segment_ns": 3600000000000,
        "audio_hz": 48000,
        "real_hourly_mp4_verified": False,
        "real_tapo_rtsp_verified": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    a = p.parse_args()
    d = check(a.source.read_text(encoding="utf-8-sig"))
    print(
        "C545D_RECORDING_STATIC_CONTRACT_PASS,"
        f"streams={d['streams']},fps={d['fps']},qp={d['qp']},"
        f"segment_ns={d['segment_ns']},audio_hz={d['audio_hz']},"
        "real_hourly_mp4_not_verified=1,real_tapo_rtsp_not_verified=1"
    )


if __name__ == "__main__":
    main()
