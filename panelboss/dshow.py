r"""DirectShow device-tree identity: the index space named honestly.

OpenCV's CAP_DSHOW picks index N as the Nth filter of the VideoInput
category in the SystemDeviceEnum enumeration order. That order is the
index space the whole app lives in (the scan probes it, the picker
publishes it) - but nothing in-process could NAME it before this
module: camera_names() is a class-Camera PnP list whose order need not
match (positional attach: the gate-8 lie) and whose CLASS misses the
vendor virtual filters (NVIDIA ROOT\, DroidCam SWD\) that DSHOW hands
out as open indices anyway.

GetDisplayName on each moniker returns the device PATH, e.g.
    \\?\USB#VID_1532&PID_0E03&MI_00#b&236b59e&0&0000#{65e8...}
which embeds the PnP InstanceId (the wizard's key!) between "\\?\" and
"#{". One enumerator walk therefore maps index -> instance without
EVERY opening a single device (no graphs, no LEDs - monikers bind
names, not pipelines). Instance -> the rest (name, status, virtual?)
is one powershell query back through camera.pnp_rows_by_instance.

Failure mode by design: any COM error at any step answers [] (logged
once) and every caller degrades to the old positional behavior -
naming is never fatal. ctypes by hand because the venv carries no
COM bindings; vtable indices are IMoniker ABI (slot 8 =
GetDisplayName/GetDisplayName2-flag-0, the same string either SDK
spelling - do NOT "fix" it by shifting;
IEnumMoniker Next = 3; ICreateDevEnum CreateClassEnumerator = 3).
SIZE LAW note: 192, justified - one COM seam, one apartment story; the
vtable arithmetic reads top-to-bottom or not at all.
"""
import ctypes
from ctypes import POINTER, byref, cast
from ctypes.wintypes import BYTE, DWORD, LONG, ULONG, WORD
from ctypes import c_wchar_p          # 3.10's wintypes has no WSTRING
import logging

log = logging.getLogger("camera")

_OLE32 = ctypes.OleDLL("ole32")


class GUID(ctypes.Structure):
    """The one COM structure ctypes refuses to ship: 16 packed bytes,
    spelled the way the uuid.h initializer macros spell them."""
    _fields_ = [("Data1", DWORD), ("Data2", WORD), ("Data3", WORD),
                ("Data4", BYTE * 8)]

    def __init__(self, d1, d2, d3, d4):
        ctypes.Structure.__init__(self)
        self.Data1, self.Data2, self.Data3 = d1, d2, d3
        self.Data4[:] = d4

_CLSID_SYSTEM_DEVICE_ENUM = GUID(0x62BE5D14, 0x60EB, 0x11D0,
                                 bytes.fromhex("BD3B00A0C911CE86"))
_IID_ICREATE_DEV_ENUM = GUID(0x29840814, 0x5B81, 0x4C5B,
                             bytes.fromhex("B3F5AD7E62E632D2"))
_CAT_VIDEO_INPUT = GUID(0x860BB310, 0x5D01, 0x11D0,
                        bytes.fromhex("BD3B00A0C911CE86"))
_IID_ICLASS_FACTORY = GUID(0x00000001, 0x0000, 0x0000,
                           bytes.fromhex("C000000000000046"))
# CreateClassEnumerator takes the category CLSID and hands back the
# generic enumerator - no extra IID needed; the GUID types are
# layout-identical, so the module spells every one of them GUID.

_CLSCTX_INPROC_SERVER = 1


def _vt(obj, index):
    """Call vtable slot `index` of a COM pointer with the given args
    (this-pointer implicit, stdcall): the whole reason this file can
    be 120 lines instead of a typelib."""
    vtable = cast(obj, POINTER(POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(LONG)(vtable[index])   # restype only: the
    return fn                                      # argtypes stay per-
    # call (byref/c_void_p/None all pass), which is the whole economy
    # of hand-rolled vtables


def _call(obj, index, *args):
    return _vt(obj, index)(obj, *args)


def _instance_of(path):
    r"""\\?\USB#VID_1532&PID_0E03&MI_00#b&236b59e&0&0000#{guid} ->
    USB\\VID_1532&PID_0E03&MI_00\\B&236B59E&0&0000 (upper, '#'-to-'\\'
    for the leading device-id half, trailing '#&0&0000' subpaths
    joined as PnP spells them). Answers None for anything that is not
    a \\?\ device path (a class-moniker display name we cannot parse
    must not guess an instance)."""
    if not path or not path.startswith("\\\\?\\"):
        return None
    body = path[4:].split("#{", 1)[0]
    parts = body.split("#")
    if len(parts) < 2:
        return None
    return "\\".join(p.upper() for p in parts)


def _create_devenum():
    """ICreateDevEnum, by whichever route THIS machine allows. Measured
    on the dev desk: CLSID_SystemDeviceEnum is CLASSNOTREG in every
    registry root, cold or after cv2 loads quartz/devenum - yet cv2's
    DSHOW opens work, so OpenCV reaches the factory through the DLL
    export, not registration. Same here: CoCreateInstance first (the
    registered-machine happy path), then DllGetClassObject straight
    out of devenum.dll (the enumerator's home; qedit.dll exports it
    too on some builds). Answers a c_void_p or None."""
    out = ctypes.c_void_p()
    try:
        _OLE32.CoCreateInstance(byref(_CLSID_SYSTEM_DEVICE_ENUM), None,
                                _CLSCTX_INPROC_SERVER,
                                byref(_IID_ICREATE_DEV_ENUM), byref(out))
        if out.value:
            return out
    except OSError:
        pass
    for dll_name in ("devenum.dll", "qedit.dll"):
        try:
            dll = ctypes.WinDLL(dll_name)
            factory = ctypes.c_void_p()
            hr = dll.DllGetClassObject(byref(_CLSID_SYSTEM_DEVICE_ENUM),
                                       byref(_IID_ICLASS_FACTORY),
                                       byref(factory))
            if hr != 0 or not factory.value:
                continue
            try:  # IClassFactory::CreateInstance = vtable slot 3
                inst = ctypes.c_void_p()
                if _call(factory, 3, None,
                         byref(_IID_ICREATE_DEV_ENUM), byref(inst)) == 0 \
                        and inst.value:
                    return inst
            finally:
                _call(factory, 2)      # Release
        except OSError:
            continue
    return None


_warned = False


def _warn_once(msg):
    global _warned
    if not _warned:
        _warned = True
        log.warning(msg)


def device_paths():
    """Ordered DSHOW video-input device paths; position == the
    CAP_DSHOW index. [] = the tree could not be walked."""
    try:
        _OLE32.CoInitializeEx(None, 0)    # MTA; S_FALSE on an already
    except OSError:                       # initialized thread is fine,
        pass                              # RPC_E_CHANGED_MODE even more
                                          # so: somebody else's apartment
                                          # still serves the enumerator
    devenum = _create_devenum()
    if devenum is None:
        _warn_once("dshow tree: no enumerator (class unregistered and "
                   "no factory in devenum/qedit)")
        return []
    try:
        enum = ctypes.c_void_p()
        if _call(devenum, 3, byref(_CAT_VIDEO_INPUT), byref(enum), 0) != 0 \
                or not enum:
            return []                      # no category: no cameras, plain
        try:
            paths = []
            mon = ctypes.c_void_p()
            got = ULONG(0)
            while _call(enum, 3, 1, byref(mon), byref(got)) == 0 and got.value:
                try:
                    pbstr = c_wchar_p()     # BSTR out param
                    if _call(mon, 8, None, 0, byref(pbstr)) == 0 and pbstr.value:
                        paths.append(str(pbstr.value))
                        _OLE32.CoTaskMemFree(pbstr)
                    else:
                        paths.append("")    # position kept: the index space
                                            # must not compress on a nameless
                                            # filter (a hole shifts every
                                            # later position)
                finally:
                    _call(mon, 2)           # Release
            return paths
        finally:
            _call(enum, 2)
    finally:
        _call(devenum, 2)


def index_instances():
    """{index: instance}: the honest name-attach seed. An empty-string
    display name (the hole case) simply maps nowhere - positional
    behavior for that index is the documented fallback, not a lie."""
    return {i: inst for i, p in enumerate(device_paths())
            if (inst := _instance_of(p))}
