"""Linux AT-SPI2 accessibility and X11 window activation.

libatspi is loaded directly so the standalone app does not depend on the system
Python's GI installation. Wayland deliberately exposes accessibility only;
global input and screen capture need compositor portals and are reported absent.
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import os
import time

from ._native_types import Focus, NativeError


class _Rect(C.Structure):
    _fields_ = [(key, C.c_int) for key in ("x", "y", "width", "height")]


class _Ref:
    def __init__(self, value, lib):
        self.value, self.lib = value, lib

    def __del__(self):
        if self.value:
            self.lib.g_object_unref(self.value)


class LinuxAccessibility:
    def __init__(self):
        path = ctypes.util.find_library("atspi")
        if not path:
            raise NativeError("Desktop accessibility needs the libatspi2.0-0 system package.")
        self.lib = C.CDLL(path)
        self.glib = C.CDLL(ctypes.util.find_library("glib-2.0"))
        self.gobject = C.CDLL(ctypes.util.find_library("gobject-2.0"))
        self.glib.g_free.argtypes = [C.c_void_p]
        self.gobject.g_object_unref.argtypes = [C.c_void_p]
        self._declare()
        if self.lib.atspi_init() != 0:
            raise NativeError("The desktop accessibility bus is unavailable. Enable desktop accessibility.")
        self.wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
        self.display = None
        if os.environ.get("DISPLAY") and not self.wayland:
            from Xlib import display
            self.display = display.Display()

    def _declare(self):
        p, i, s = C.c_void_p, C.c_int, C.c_char_p
        signatures = {
            "atspi_init": (i, []), "atspi_get_desktop": (p, [i]),
            "atspi_accessible_get_child_count": (i, [p, p]),
            "atspi_accessible_get_child_at_index": (p, [p, i, p]),
            "atspi_accessible_get_parent": (p, [p, p]),
            "atspi_accessible_get_name": (p, [p, p]),
            "atspi_accessible_get_role_name": (p, [p, p]),
            "atspi_accessible_get_process_id": (C.c_uint, [p, p]),
            "atspi_accessible_get_state_set": (p, [p]),
            "atspi_state_set_contains": (i, [p, i]),
            "atspi_accessible_get_text_iface": (p, [p]),
            "atspi_accessible_get_editable_text_iface": (p, [p]),
            "atspi_accessible_get_action_iface": (p, [p]),
            "atspi_accessible_get_component_iface": (p, [p]),
            "atspi_component_get_extents": (C.POINTER(_Rect), [p, i, p]),
            "atspi_component_grab_focus": (i, [p, p]),
            "atspi_text_get_character_count": (i, [p, p]),
            "atspi_text_get_text": (p, [p, i, i, p]),
            "atspi_text_get_n_selections": (i, [p, p]),
            "atspi_text_get_caret_offset": (i, [p, p]),
            "atspi_text_get_selection": (p, [p, i, p]),
            "atspi_editable_text_set_text_contents": (i, [p, s, p]),
            "atspi_action_get_n_actions": (i, [p, p]),
            "atspi_action_do_action": (i, [p, i, p]),
        }
        for name, (restype, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = restype, args
        if hasattr(self.lib, "atspi_set_timeout"):
            self.lib.atspi_set_timeout(250, 500)

    def _string(self, pointer) -> str:
        if not pointer:
            return ""
        try:
            return C.string_at(pointer).decode("utf-8", errors="replace")
        finally:
            self.glib.g_free(pointer)

    def _ref(self, pointer):
        return _Ref(pointer, self.gobject) if pointer else None

    def _children(self, reference, *, deadline=None):
        pointer = reference.value
        for index in range(min(600, max(0, self.lib.atspi_accessible_get_child_count(pointer, None)))):
            if deadline is not None and time.monotonic() >= deadline:
                break
            child = self._ref(self.lib.atspi_accessible_get_child_at_index(pointer, index, None))
            if child:
                yield child

    def _states(self, reference) -> tuple[bool, bool]:
        states = self._ref(self.lib.atspi_accessible_get_state_set(reference.value))
        if not states:
            return False, False
        return (bool(self.lib.atspi_state_set_contains(states.value, 12)),
                bool(self.lib.atspi_state_set_contains(states.value, 7)))

    def _window_info(self, reference):
        current = reference
        for _ in range(16):
            role = self._string(self.lib.atspi_accessible_get_role_name(current.value, None))
            if role in ("frame", "window", "dialog"):
                title = self._string(self.lib.atspi_accessible_get_name(current.value, None))
                component = self._ref(self.lib.atspi_accessible_get_component_iface(current.value))
                if component:
                    extents = self.lib.atspi_component_get_extents(component.value, 0, None)
                    if extents:
                        rectangle = tuple(getattr(extents.contents, key) for key in ("x", "y", "width", "height"))
                        self.glib.g_free(extents)
                        return title, rectangle
                return title, None
            current = self._ref(self.lib.atspi_accessible_get_parent(current.value, None))
            if not current:
                break
        return "", None

    def _wrap(self, reference, app: str, window: str = "", *, with_window=False, read_text=True) -> Focus:
        pointer = reference.value
        role = self._string(self.lib.atspi_accessible_get_role_name(pointer, None))
        secure = "password" in role.casefold()
        text = ""
        text_iface = self._ref(self.lib.atspi_accessible_get_text_iface(pointer)) if read_text else None
        if text_iface and not secure:
            length = min(16000, max(0, self.lib.atspi_text_get_character_count(text_iface.value, None)))
            text = self._string(self.lib.atspi_text_get_text(text_iface.value, 0, length, None))
        component = self._ref(self.lib.atspi_accessible_get_component_iface(pointer))
        rect = (0, 0, 0, 0)
        if component:
            extents = self.lib.atspi_component_get_extents(component.value, 0, None)
            if extents:
                rect = tuple(getattr(extents.contents, key) for key in ("x", "y", "width", "height"))
                self.glib.g_free(extents)
        _, editable = self._states(reference)
        window_title, window_rect = self._window_info(reference) if with_window else ("", None)
        return Focus(f"atspi:{pointer}", int(self.lib.atspi_accessible_get_process_id(pointer, None)), app,
                     window, self._string(self.lib.atspi_accessible_get_name(pointer, None)), role, secure,
                     editable and not secure, text, rect, reference, window_title, window_rect)

    def _apps(self):
        root = self._ref(self.lib.atspi_get_desktop(0))
        if not root:
            raise NativeError("The desktop accessibility bus has no applications.")
        for reference in self._children(root):
            name = self._string(self.lib.atspi_accessible_get_name(reference.value, None))
            yield name, reference

    def _front_window(self):
        if not self.display:
            return None, None
        try:
            root = self.display.screen().root
            prop = root.get_full_property(self.display.intern_atom("_NET_ACTIVE_WINDOW"), 0)
            window = (self.display.create_resource_object("window", int(prop.value[0]))
                      if prop is not None and len(prop.value) and int(prop.value[0]) > 1 else None)
            if window is None:
                focused = self.display.get_input_focus().focus
                window = focused if hasattr(focused, "get_full_property") else None
            for _ in range(16):
                if window is None or window.id == root.id:
                    break
                value = window.get_full_property(self.display.intern_atom("_NET_WM_PID"), 0)
                if value is not None and len(value.value):
                    return window, int(value.value[0])
                window = window.query_tree().parent
        except Exception:
            return None, None
        return None, None

    def _front_pid(self) -> int | None:
        return self._front_window()[1]

    def foreground_pid(self) -> int | None:
        return self._front_pid()

    def _nodes(self, root, *, seconds: float = 0.9):
        pending, count = [(root, 0)], 0
        deadline = time.monotonic() + seconds
        while pending and count < 600 and time.monotonic() < deadline:
            reference, depth = pending.pop()
            count += 1
            yield reference
            if depth < 12:
                pending.extend((child, depth + 1) for child in reversed(list(self._children(reference, deadline=deadline))))

    def _walk(self, app: str, root):
        for reference in self._nodes(root):
            yield self._wrap(reference, app)

    def focus(self, *, read_text=True) -> Focus | None:
        window, front = self._front_window()
        for app, reference in self._apps():
            pid = self.lib.atspi_accessible_get_process_id(reference.value, None)
            if front is not None and pid != front:
                continue
            for candidate in self._nodes(reference):
                if self._states(candidate)[0]:
                    return self._wrap(candidate, app, str(window.id) if window else "",
                                      with_window=True, read_text=read_text)
        return None

    def focus_metadata(self) -> Focus | None:
        return self.focus(read_text=False)

    def keyboard_focus_matches(self, target: Focus) -> bool:
        # AT-SPI may retain a widget's focused state after WSLg loses the host
        # desktop's keyboard focus. X11 is authoritative for injected input.
        return self.display is not None and target.pid > 0 and self._front_pid() == target.pid

    def refresh(self, target: Focus) -> Focus | None:
        return self._wrap(target.handle, target.app, target.window)

    def focus_field(self, target: Focus) -> Focus:
        if not self.display or not target.window:
            raise NativeError("Returning to a dictation field needs its captured X11 window.")
        current = self.refresh(target)
        if (not current or current.identity != target.identity or current.pid != target.pid or
                current.secure or not current.editable or target.pid == os.getpid()):
            raise NativeError("The captured dictation field is no longer available.")
        window = self.display.create_resource_object("window", int(target.window))
        process = window.get_full_property(self.display.intern_atom("_NET_WM_PID"), 0)
        if process is None or not len(process.value) or int(process.value[0]) != target.pid:
            raise NativeError("The captured dictation window is no longer available.")
        if self._front_pid() != os.getpid():
            raise NativeError("Another application has taken focus.")
        self._activate_window(window)
        deadline = time.monotonic() + .3
        while self._front_pid() == os.getpid() and time.monotonic() < deadline:
            time.sleep(.01)  # EWMH activation is acknowledged asynchronously.
        checked = self.refresh(target)
        if (self._front_pid() != target.pid or not checked or checked.identity != target.identity or
                checked.pid != target.pid or checked.secure or not checked.editable):
            raise NativeError("The captured dictation field changed.")
        component = self._ref(self.lib.atspi_accessible_get_component_iface(checked.handle.value))
        if not component or not self.lib.atspi_component_grab_focus(component.value, None):
            raise NativeError("The captured dictation field did not regain focus.")
        focused = self.focus()
        if (not focused or focused.identity != target.identity or focused.pid != target.pid or
                focused.secure or not focused.editable or not self.keyboard_focus_matches(focused)):
            raise NativeError("The captured dictation field did not regain focus.")
        return focused

    def _activate_window(self, window) -> None:
        from Xlib import X, protocol
        root = self.display.screen().root
        wm = root.get_full_property(self.display.intern_atom("_NET_SUPPORTING_WM_CHECK"), 0)
        message = protocol.event.ClientMessage(window=window,
            client_type=self.display.intern_atom("_NET_ACTIVE_WINDOW"), data=(32, [2, 0, 0, 0, 0]))
        root.send_event(message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        if wm is None:
            window.map()
            window.configure(stack_mode=X.Above)
            window.set_input_focus(X.RevertToParent, X.CurrentTime)
        self.display.sync()

    def windows(self) -> list[Focus]:
        result = []
        for app, reference in self._apps():
            for child in self._children(reference):
                target = self._wrap(child, app)
                if target.pid != os.getpid():
                    result.append(target)
        return result

    def activate(self, app: str) -> Focus:
        if not self.display:
            raise NativeError("Window activation needs X11. On Wayland, activate the target app yourself.")
        from Xlib import X, protocol
        root = self.display.screen().root
        prop = root.get_full_property(self.display.intern_atom("_NET_CLIENT_LIST"), 0)
        candidates = [self.display.create_resource_object("window", int(wid)) for wid in (prop.value if prop else [])]
        # WSLg and bare X servers may not publish an EWMH client list. Discover
        # top-level X windows directly; never assume a full Linux window manager.
        if not candidates:
            pending = [(window, 0) for window in root.query_tree().children]
            while pending and len(candidates) < 300:
                window, depth = pending.pop()
                candidates.append(window)
                if depth < 2:
                    try:
                        pending.extend((child, depth + 1) for child in window.query_tree().children)
                    except Exception:
                        pass
        for window in candidates:
            try:
                title = window.get_full_property(self.display.intern_atom("_NET_WM_NAME"), 0)
                raw = title.value if title is not None else window.get_wm_name() or ""
                name = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                classes = " ".join(value.decode(errors="replace") if isinstance(value, bytes) else value
                                   for value in (window.get_wm_class() or ()))
            except Exception:
                continue
            if app.casefold() not in f"{name} {classes}".casefold():
                continue
            # XWayland's internal window manager can handle activation even when
            # it does not advertise _NET_SUPPORTING_WM_CHECK (notably WSLg).
            self._activate_window(window)
            matches = [w for w in self.windows() if app.casefold() in (w.app + " " + w.title).casefold()]
            if matches:
                return matches[0]
            # An app can have its X11 window mapped before it registers with
            # AT-SPI. Activation itself still succeeded; callers separately
            # verify accessible focus before they type or paste anything.
            process = window.get_full_property(self.display.intern_atom("_NET_WM_PID"), 0)
            pid = int(process.value[0]) if process is not None and len(process.value) else 0
            return Focus(f"x11:{window.id}", pid, classes.split()[-1] if classes else app,
                         str(window.id), name, "window")
        raise NativeError(f"{app} has no open X11 window. Open it first.")

    def elements(self, app: str = "") -> list[Focus]:
        front, result = self._front_pid(), []
        for name, reference in self._apps():
            pid = self.lib.atspi_accessible_get_process_id(reference.value, None)
            if (app and app.casefold() not in name.casefold()) or (not app and front is not None and pid != front):
                continue
            result.extend(self._walk(name, reference))
            if result and not app:
                break
        return result

    def at_point(self, x: int, y: int) -> Focus | None:
        found = None
        for target in self.elements():
            left, top, width, height = target.rect
            if left <= x < left + width and top <= y < top + height:
                found = target
        return found

    def press(self, target: Focus) -> None:
        target = self.refresh(target)
        if target.secure:
            raise NativeError("Password fields cannot be controlled.")
        action = self._ref(self.lib.atspi_accessible_get_action_iface(target.handle.value))
        if not action or self.lib.atspi_action_get_n_actions(action.value, None) < 1:
            raise NativeError("This control has no background action. Use its visible position instead.")
        if not self.lib.atspi_action_do_action(action.value, 0, None):
            raise NativeError("The application refused this accessibility action.")

    def set_value(self, target: Focus, text: str) -> None:
        target = self.refresh(target)
        if target.secure or not target.editable:
            raise NativeError("This is not a writable, non-password field.")
        editable = self._ref(self.lib.atspi_accessible_get_editable_text_iface(target.handle.value))
        if not editable or not self.lib.atspi_editable_text_set_text_contents(editable.value, text.encode(), None):
            raise NativeError("The application refused to change this field.")

    def selected_text(self, target: Focus) -> str:
        if target.secure:
            return ""
        text = self._ref(self.lib.atspi_accessible_get_text_iface(target.handle.value))
        if not text or self.lib.atspi_text_get_n_selections(text.value, None) < 1:
            return ""
        selection = self.lib.atspi_text_get_selection(text.value, 0, None)
        if not selection:
            return ""
        try:
            offsets = C.cast(selection, C.POINTER(C.c_int))
            return self._string(self.lib.atspi_text_get_text(text.value, offsets[0], offsets[1], None))
        finally:
            self.glib.g_free(selection)

    def selection_span(self, target: Focus) -> tuple[int, int] | None:
        if target.secure or not target.editable:
            return None
        text = self._ref(self.lib.atspi_accessible_get_text_iface(target.handle.value))
        if not text:
            return None
        count = self.lib.atspi_text_get_n_selections(text.value, None)
        if count == 0:
            caret = self.lib.atspi_text_get_caret_offset(text.value, None)
            return (caret, caret) if 0 <= caret <= len(target.text) else None
        if count != 1:
            return None
        selection = self.lib.atspi_text_get_selection(text.value, 0, None)
        if not selection:
            return None
        try:
            offsets = C.cast(selection, C.POINTER(C.c_int))
            start, end = offsets[0], offsets[1]
            return (start, end) if 0 <= start <= end <= len(target.text) else None
        finally:
            self.glib.g_free(selection)
