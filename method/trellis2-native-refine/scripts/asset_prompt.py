"""Shared asset task instructions; host configuration supplies runtime facts only."""


DEFAULT_TRANSPORT_HINT = (
    "Use the skill's TRELLIS.2 scripts and the active configured deployment as tools."
)


def build_asset_prompt(skill, image, root, settings, context="", writable_dirs=()):
    """Construct the model prompt without reading credentials or starting tools."""
    transport_hint = settings.get("transport_hint", DEFAULT_TRANSPORT_HINT)
    if not isinstance(transport_hint, str):
        raise ValueError("transport_hint must be a string containing runtime information")
    native_requirement = ""
    if skill.name == "trellis2-native-refine":
        native_requirement = (
            "This route requires a TRELLIS native candidate. If TRELLIS generation or a required "
            "environment operation is unavailable or blocked, save diagnostics and STOP. "
            "Do not substitute a Blender-only asset, even if you announce the substitution.\n"
        )
    extra_writes = ""
    if writable_dirs:
        extra_writes = (
            "Only your API temporary/cache paths may additionally be written within\n"
            f"{list(writable_dirs)}; keep final case assets and reports in {root}.\n"
        )
    return f"""Execute the user's single-image interactive asset request using ${skill.name}.
Read {skill / 'SKILL.md'} and the relevant references and implement that route fully.
You are already inside the API-key execution process: do not launch run_api.py again.
Input image: {image}
Write generated assets, scripts, reports and renders only under {root}.
The original image is attached. Observe it yourself; author case-specific Blender and
simulation code, inspect actual renders and iterate from the evidence yourself.
Inspect rendered image pixels with the available image-viewing tool when assessing
appearance and whether visible defects have been repaired.
The parent desktop task only launches this run and displays results. Do not ask it
to supply modeling decisions or code. Do not create additional agents or invoke
another LLM/API/session. Do not read credential files or print environment secrets.
{native_requirement}Configured Python: {settings.get('runtime_python', '')}
Configured Blender: {settings.get('runtime_blender', '')}
Configured TRELLIS profile (pass as --config before the subcommand): {settings.get('trellis_config') or skill / 'references' / 'server.json'}
{transport_hint}
{extra_writes}Infer editable dimensions/physics when absent. Export the editable Blender file,
MJCF/dependencies and visual asset, matched-view renders and real interaction tests.
Preserve raw candidates and reports; describe unsupported physics and failed checks.
Do not change login, global settings, installed skills, weights, or unrelated work.
Respect enforced permissions. If a required operation is blocked, report it; do not
bypass restrictions or silently switch methods, models or authentication.
Return a concise Chinese result report with output paths and actual passed/failed checks.
Additional user task context (may include tool locations):
{context}
"""
