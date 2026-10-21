# External worker protocol v1

The native Blender UI and worker communicate through files, not an imported
NVIDIA library. No network service is involved. `python -m
neural_finishing.worker --probe` validates files only; `--job /path/job.json`
explicitly starts capture and inference. Unknown protocol versions are rejected.

The UI writes an immutable job directory containing a copied `scene.blend` and
`job.json`. Required fields are protocol=1; Blender executable; relative snapshot
path and SHA256; scene and view-layer names; ordered consecutive integer frames;
positive pixel width/height; backend=`nvidia`; style=`STANDARD`, `NATURAL` or
`CINEMATIC`; finite intensity/structure/tone in [0,2]; runtime manifest SHA256.
External unpacked image files are listed with absolute paths and hashes. These
are local job data, not uploaded telemetry. The native panel never selects the
test-only fixture backend.

The worker checks the snapshot and assets, acquires an OS-owned job lock, verifies
the runtime files, and starts one background Blender capture process. `status.json`
reports protocol, state, stage, completed, total, message and worker PID. States
are running/complete/cancelled/error; capture stages are beauty/guides, followed
by neural. Status replacement is atomic. Logs are local text files.

Capture output consists of original `hdr/FRAME.exr`, display-transformed
`beauty/FRAME.png`, `guides/FRAME.exr`, `metadata/FRAME.json`, and a verified
`capture/FRAME.json` receipt. Metadata includes clipping planes, camera identity,
camera-marker shot identity, world/projection matrices, resolution and the actual
beauty/guide motion-blur flags. Guide files retain native float32 Z and Vector
channels. Conversion uses perspective device depth and [Vector.X,-Vector.Y]
current-to-previous pixel motion, with bottom-up orientation handled once in the
native wrapper. Perspective reprojection on the new sample remains a deferred
rendering validation; prior project-specific results are not generalized as proof.

Within each shot, the worker creates a fresh native feature stream, zeros motion
and resets history on the first frame, then evaluates sequentially. Processed
PNGs and `shots/START_END.json` receipts are separate from originals. A receipt
records input-job fingerprint, output hashes, frame resets and timings. A receipt
is written only after the entire shot succeeds. Resume skips intact captures and
complete shots; a partial or altered shot is reprocessed from its first frame.

The UI requests cancellation by creating `CANCEL`. The worker terminates only its
own background capture subprocess, or stops between native evaluations. Exit 75
means cancelled; 0 complete; nonzero error otherwise. Resume explicitly removes
the cancellation marker. A second worker cannot acquire the same job lock.

A future backend implements initialization, process(color,depth,motion,settings,
reset) and close behind this worker. The current BlenDLSS ABI-3 wrapper is an
implementation detail, not a promise about a future official NVIDIA API. Native
errors never silently produce a filtered substitute. The current interface is
RGBA8 SDR and does not add frames or change resolution.

The WIP native UI uses a session-only WindowManager property group and Python
operators; no DNA structs, file versioning, C++ ABI or F12 handlers are changed.
Persisting per-scene settings is intentionally deferred to upstream design review.
