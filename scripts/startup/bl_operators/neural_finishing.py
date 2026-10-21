# SPDX-FileCopyrightText: 2026 Jason Lok
# SPDX-License-Identifier: GPL-2.0-or-later
"""WIP native Render Properties integration for an optional external worker.

Importing or drawing this module never renders, loads a runtime or probes a GPU.
Settings are session-only during this prototype; no DNA/file-versioning changes.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup

_process = None
_log = None


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _package(settings):
    return Path(bpy.path.abspath(settings.package_directory)).resolve()


def _background_render_exists():
    if os.name != "nt":
        return False
    # Read-only, no process termination. Fail closed if enumeration is unavailable.
    command = ("@(Get-CimInstance Win32_Process -Filter \"Name='blender.exe'\" | "
               "Where-Object { $_.CommandLine -match '(?:^|\\s)(?:-b|--background)(?:\\s|$)' } | "
               "Select-Object -ExpandProperty ProcessId) | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                            capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Could not check for another background Blender render")
    ids = json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(ids, int):
        ids = [ids]
    return any(pid != os.getpid() for pid in ids)


def _preflight(context, settings):
    if os.name != "nt":
        raise ValueError("The experimental backend currently requires Windows")
    if _process is not None and _process.poll() is None:
        raise ValueError("A neural-finishing job is already running")
    if bpy.app.is_job_running("RENDER") or _background_render_exists():
        raise ValueError("Another Blender render is active; no second render was started")
    if not settings.enabled:
        raise ValueError("Enable the experimental feature first")
    scene = context.scene
    if scene.render.engine != "CYCLES":
        raise ValueError("Version one supports Cycles only")
    if scene.camera is None or scene.camera.data.type != "PERSP":
        raise ValueError("Select a perspective camera")
    if any(marker.camera and marker.camera.data.type != "PERSP" for marker in scene.timeline_markers):
        raise ValueError("All camera cuts must use perspective cameras")
    if scene.render.film_transparent or scene.render.use_border or scene.render.use_multiview:
        raise ValueError("Use opaque, uncropped, single-view output for this prototype")
    if scene.render.use_sequencer and scene.sequence_editor is not None:
        raise ValueError("The first prototype processes one scene, not Video Sequencer output")
    if any(item.use and item != context.view_layer for item in scene.view_layers):
        raise ValueError("Enable only the active view layer")
    if bpy.data.libraries:
        raise ValueError("Linked libraries are outside the first prototype's snapshot support")
    package = _package(settings)
    if not (package / "runtime/python.exe").is_file() or not (package / "neural_finishing/worker.py").is_file():
        raise ValueError("Select the extracted experimental worker package")


def _poll():
    global _process, _log
    if _process is None:
        return None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "PROPERTIES":
                area.tag_redraw()
    settings = bpy.context.window_manager.neural_finishing
    try:
        state = json.loads((Path(settings.last_job).parent / "status.json").read_text())
        total = state.get("total", 0)
        suffix = " %s/%s" % (state.get("completed", 0), total) if total else ""
        settings.status = state["stage"].title() + suffix + ": " + state.get("message", "")
    except (OSError, ValueError, KeyError):
        pass
    if _process.poll() is None:
        return 0.5
    settings.running = False
    if _process.returncode not in (0, 75):
        settings.status = "Failed: " + settings.status
    if _log is not None:
        _log.close()
    _log = _process = None
    return None


def _launch(settings, job_path):
    global _process, _log
    package = _package(settings)
    _log = (job_path.parent / "worker.log").open("ab")
    try:
        _process = subprocess.Popen(
            [str(package / "runtime/python.exe"), "-m", "neural_finishing.worker", "--job", str(job_path)],
            cwd=package, stdout=_log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        _log.close()
        _log = None
        raise
    settings.last_job = str(job_path)
    settings.running = True
    settings.status = "Starting background capture"
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.5)


class NeuralFinishingSettings(PropertyGroup):
    enabled: BoolProperty(name="Enable Experimental Neural Finishing", default=False)
    mode: EnumProperty(name="Mode", items=[("STILL", "Current Frame", ""), ("ANIMATION", "Frame Range", "")])
    intensity: FloatProperty(name="Intensity", default=0.65, min=0, max=2)
    structure: FloatProperty(name="Structure", default=0.65, min=0, max=2)
    tone: FloatProperty(name="Tone", default=0.4, min=0, max=2)
    style: EnumProperty(name="Style", items=[("STANDARD", "Standard", ""), ("NATURAL", "Natural", ""),
                                           ("CINEMATIC", "Cinematic", "")], default="CINEMATIC")
    package_directory: StringProperty(name="Worker Package", subtype="DIR_PATH")
    output_directory: StringProperty(name="Output Folder", subtype="DIR_PATH", default="//neural_finishing/")
    last_job: StringProperty(name="Last Job", subtype="FILE_PATH")
    status: StringProperty(default="Disabled; no runtime loaded")
    running: BoolProperty(default=False, options={"SKIP_SAVE"})


class RENDER_OT_neural_finishing_probe(Operator):
    bl_idname = "render.neural_finishing_probe"
    bl_label = "Verify Worker Files"
    bl_description = "Verify runtime files without rendering or initializing a GPU"

    def execute(self, context):
        settings = context.window_manager.neural_finishing
        package = _package(settings)
        try:
            command = [str(package / "runtime/python.exe"), "-m", "neural_finishing.worker", "--probe"]
            result = subprocess.run(command, cwd=package, capture_output=True, text=True, timeout=30,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            response = json.loads(result.stdout if result.returncode == 0 else result.stderr)
            settings.status = response["message"]
            if result.returncode:
                raise ValueError(settings.status)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class RENDER_OT_neural_finishing(Operator):
    bl_idname = "render.neural_finishing"
    bl_label = "Render & Process"
    bl_description = "Explicitly render a separate scene snapshot and run neural finishing"

    def execute(self, context):
        settings = context.window_manager.neural_finishing
        try:
            _preflight(context, settings)
            root = Path(bpy.path.abspath(settings.output_directory)).resolve() / uuid.uuid4().hex[:12]
            root.mkdir(parents=True, exist_ok=False)
            snapshot = root / "scene.blend"
            assets = []
            for image in bpy.data.images:
                if image.source == "FILE" and image.filepath and not image.packed_file:
                    path = Path(bpy.path.abspath(image.filepath)).resolve()
                    assets.append(dict(path=str(path), sha256=_digest(path)))
                elif image.source in {"MOVIE", "SEQUENCE", "TILED"}:
                    raise ValueError("Movie, sequence and tiled textures are outside the first prototype")
            scene = context.scene
            frames = [scene.frame_current] if settings.mode == "STILL" else list(range(scene.frame_start, scene.frame_end + 1))
            bpy.ops.wm.save_as_mainfile(filepath=str(snapshot), copy=True, relative_remap=True)
            job = dict(protocol=1, blender=bpy.app.binary_path, snapshot="scene.blend",
                       snapshot_sha256=_digest(snapshot), source_file=bpy.data.filepath,
                       scene=scene.name, view_layer=context.view_layer.name, frames=frames,
                       width=scene.render.resolution_x * scene.render.resolution_percentage // 100,
                       height=scene.render.resolution_y * scene.render.resolution_percentage // 100,
                       backend="nvidia", assets=assets,
                       runtime_manifest_sha256=_digest(_package(settings) / "runtime-manifest.json"),
                       intensity=settings.intensity, structure=settings.structure,
                       tone=settings.tone, style=settings.style)
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
            _launch(settings, job_path)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class RENDER_OT_neural_finishing_cancel(Operator):
    bl_idname = "render.neural_finishing_cancel"
    bl_label = "Cancel"

    def execute(self, context):
        settings = context.window_manager.neural_finishing
        if settings.running and settings.last_job:
            (Path(settings.last_job).parent / "CANCEL").touch()
            settings.status = "Cancelling; verified completed work will be retained"
        return {"FINISHED"}


class RENDER_OT_neural_finishing_resume(Operator):
    bl_idname = "render.neural_finishing_resume"
    bl_label = "Resume Last Job"

    def execute(self, context):
        settings = context.window_manager.neural_finishing
        try:
            _preflight(context, settings)
            job_path = Path(settings.last_job).resolve()
            if not job_path.is_file():
                raise ValueError("Select an existing job.json to resume")
            job_path.with_name("CANCEL").unlink(missing_ok=True)
            _launch(settings, job_path)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class RENDER_OT_neural_finishing_view(Operator):
    bl_idname = "render.neural_finishing_view"
    bl_label = "View Result"
    processed: BoolProperty(default=True)

    def execute(self, context):
        settings = context.window_manager.neural_finishing
        try:
            job_path = Path(settings.last_job)
            job = json.loads(job_path.read_text(encoding="utf-8"))
            frame = context.scene.frame_current
            if frame not in job["frames"]:
                frame = job["frames"][0]
            path = job_path.parent / ("processed" if self.processed else "beauty") / ("%07d.png" % frame)
            if not path.is_file():
                raise ValueError("This frame is not available yet")
            image = bpy.data.images.load(str(path), check_existing=True)
            editors = [area for area in context.screen.areas if area.type == "IMAGE_EDITOR"]
            if not editors:
                bpy.ops.render.view_show("INVOKE_DEFAULT")
                editors = [area for window in context.window_manager.windows for area in window.screen.areas
                           if area.type == "IMAGE_EDITOR"]
            if not editors:
                raise ValueError("Open an Image Editor to view the result")
            for area in editors:
                area.spaces.active.image = image
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


classes = (
    NeuralFinishingSettings,
    RENDER_OT_neural_finishing_probe,
    RENDER_OT_neural_finishing,
    RENDER_OT_neural_finishing_cancel,
    RENDER_OT_neural_finishing_resume,
    RENDER_OT_neural_finishing_view,
)


def register():
    bpy.types.WindowManager.neural_finishing = PointerProperty(type=NeuralFinishingSettings)


def unregister():
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
    del bpy.types.WindowManager.neural_finishing
