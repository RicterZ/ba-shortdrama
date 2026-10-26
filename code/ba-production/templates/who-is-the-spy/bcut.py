"""Spy layout, spotlight and composite rules are owned by this processor."""
from functools import partial
import ba_layer_schedule as schedule
import ba_scene

layers = partial(schedule.default_layers, spy=True)
ranges = partial(schedule.layer_frame_ranges, spy=True)
jobs = partial(schedule.render_jobs, spy=True)
effects = schedule.effect_audio_events
static_spans = partial(ba_scene.static_spans, spy=True)
composites = partial(ba_scene.composites, spy=True)
audio_events = partial(ba_scene.audio_events, spy=True)
TEXT_BELOW = set()
EXPORT_WARNINGS = (
    "谁是卧底的词牌、大字幕、心理字幕和投票字按画面位置写成字幕。描边是必剪的单层描边。"
    "聚光灯只压暗背景和其他角色，没有径向光。",
)
