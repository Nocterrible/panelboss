"""ONNX runtime plumbing.

find_model: looks for a *.onnx under models/ and downloads once if the
directory is empty (try each mirror, keep the first file over 1 MB, log
where it came from and how long it took).
get_session: provider list is built from what the installed onnxruntime
wheel actually has (get_available_providers) - CUDA or DirectML first
when wanted, CPU always last; requesting a provider the wheel lacks is
only a stderr warning pythonw never shows, so we never request blind.
"""

from __future__ import annotations

import glob
import logging
import os
import sys
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

def _default_models_root():
    """Where *.onnx live. A frozen PyInstaller build rewrites __file__
    into the bundle, which the user can neither see nor edit, so the
    frozen exe looks for a models/ folder BESIDE the exe first -
    exactly where a release zip puts it - and only then falls back to
    the repo layout (download-once still fills whichever wins)."""
    if getattr(sys, "frozen", False):
        cand = os.path.join(os.path.dirname(sys.executable), "models")
        if os.path.isdir(cand):
            return cand
    return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "models")


MODELS_ROOT = _default_models_root()


def cuda_gpus():
    """(id, name) per adapter. nvidia-smi enumerates in the order CUDA
    sees the cards, so these ids are the device_id the provider option
    expects. Empty list when there is no nvidia-smi (or no NVIDIA
    driver)."""
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                             timeout=10,
                             # no console, ever: a windowed parent gets
                             # a fresh visible terminal for every
                             # console-app child, and this probe runs
                             # at window build (measured popping)
                             creationflags=subprocess.CREATE_NO_WINDOW,
                             ).stdout.decode("utf-8", "replace")
    except Exception:
        return []
    gpus = []
    for line in out.splitlines():
        # "GPU 0: NVIDIA GeForce RTX 6000 Ada ... (UUID: ...)"
        head, sep, rest = line.partition(": ")
        if not sep or not head.startswith("GPU "):
            continue
        try:
            gid = int(head.split()[1])
        except (IndexError, ValueError):
            continue
        name = rest.split(" (UUID")[0].strip()
        gpus.append((gid, name))
    return gpus


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
    """Build an InferenceSession; GPU when the installed wheel has a GPU
    provider, CPU as the floor. Requesting an EP the wheel lacks is only
    a warning on ORT's stderr (invisible in a pythonw app), so we ask
    strictly from get_available_providers(): CUDA when the gpu wheel is
    installed, else DirectML (the directml wheel; any D3D12 adapter, no
    CUDA toolkit, no cuDNN dlls). device_id picks the adapter - CUDA
    order is nvidia-smi order, DML order is DXGI order, which can differ.
    """
    import onnxruntime
    avail = onnxruntime.get_available_providers()
    providers = ["CPUExecutionProvider"]
    if device in ("auto", "cuda"):
        gpu = []
        if "CUDAExecutionProvider" in avail:
            gpu.append(("CUDAExecutionProvider",
                        {"device_id": str(int(device_id))}))
        if "DmlExecutionProvider" in avail:
            gpu.append(("DmlExecutionProvider",
                        {"device_id": str(int(device_id))}))
        if not gpu:
            log.warning("device is %r but this onnxruntime wheel has no "
                        "gpu provider (available: %s); CPU only",
                        device, ", ".join(avail))
        providers = gpu + providers
    if device == "cpu":
        providers = ["CPUExecutionProvider"]
    if verbose:
        log.debug("providers: %s", providers)
    try:
        session = onnxruntime.InferenceSession(path, providers=providers)
    except Exception as e:
        log.warning("GPU unavailable (%s); falling back to CPU", e)
        session = onnxruntime.InferenceSession(
            path, providers=["CPUExecutionProvider"])
    log.info("session running on %s (device %s)",
             session.get_providers(), device_id)
    return session
