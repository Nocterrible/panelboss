"""ONNX runtime plumbing.

find_model: looks for a *.onnx under models/ and downloads once if the
directory is empty (try each mirror, keep the first file over 1 MB, log
where it came from and how long it took).
get_session: provider list is per config - CUDA first when wanted, CPU
always last; when the CUDA provider cannot load we fall back to CPU and
say so loudly, because a dark screen with a silent crash is worse than a
slow detection.
"""

from __future__ import annotations

import glob
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("inference")

# Mirror list; the first entry is the one verified at build time.
# Replace or prepend your own mirror if the network is fussy.
MODEL_URLS = [
    "https://huggingface.co/aaurelions/yolo11n.onnx/resolve/main/yolo11n.onnx",
    "https://huggingface.co/aaurelions/yolo11n.onnx/resolve/main/files/1024/yolo11n.onnx",
]

MODELS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "models")


def find_model(name="yolo11n", root=MODELS_ROOT):
    """Any *.onnx that smells like the requested model wins; the name
    filter comes first, the directory listing second."""
    preferred = sorted(glob.glob(os.path.join(root, f"*{name}*.onnx")))
    others = sorted(glob.glob(os.path.join(root, "*.onnx")))
    files = preferred + [p for p in others if p not in preferred]
    if not files:
        files = [download_model(name)]
    path = files[0]
    if os.path.getsize(path) < 1_000_000:
        raise RuntimeError(f"{path} is a stub, not a model")
    log.debug("using %s", path)
    return path


def download_model(name="yolo11n", root=MODELS_ROOT):
    """Download the weights once; try each mirror until one is big enough
    to be real (1 MB floor catches HTML error pages)."""
    if not os.path.exists(root):
        os.makedirs(root)
    path = os.path.join(root, f"{name}.onnx")
    start = time.perf_counter()
    for url in MODEL_URLS:
        log.info("downloading %s ...", url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent":
                "icu-presence-detector"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            break
        except Exception as e:
            continue
    else:
        raise RuntimeError(
            "model not found: drop %s.onnx into %s (run scripts\\setup.ps1)"
            % (name, root))
    if len(data) < 1_000_000:
        raise RuntimeError("download too small")
    with open(path, "wb") as f:
        f.write(data)
    log.info("found %s after %.2f s", url, time.perf_counter() - start)
    return path


def get_session(path, device="auto", device_id=0, verbose=False):
    """Build an InferenceSession; CUDA when asked, CPU as the floor."""
    import onnxruntime
    providers = ["CPUExecutionProvider"]
    if device in ("auto", "cuda"):
        providers.insert(0, "CUDAExecutionProvider")   # cuda always first
    if device == "cpu":
        providers = ["CPUExecutionProvider"]
    if verbose:
        log.debug("providers: %s", providers)
    try:
        session = onnxruntime.InferenceSession(path, providers=providers)
    except Exception as e:
        log.warning("CUDA unavailable (%s); falling back to CPU", e)
        session = onnxruntime.InferenceSession(
            path, providers=["CPUExecutionProvider"])
    log.info("session running on %s", session.get_providers())
    return session
