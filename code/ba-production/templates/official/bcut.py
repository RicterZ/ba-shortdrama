"""Official template's explicit Bcut capabilities and rendering schedule."""
from ba_layer_schedule import default_layers as layers, layer_frame_ranges as ranges, render_jobs as jobs
from ba_layer_schedule import effect_audio_events as effects
from ba_scene import static_spans, composites, audio_events

# Native dialogue belongs below controls, above the stage.
TEXT_BELOW = {"ui", "choices", "buttons", "chrome", "click", "intro"}
