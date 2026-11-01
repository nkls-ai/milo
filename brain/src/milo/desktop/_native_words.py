"""Local dictionaries behind the correction observer's WordList interface."""
from __future__ import annotations

import ctypes as C
import ctypes.util
import sys

from .corrections import ConservativeWords


class _WindowsWords:
    def __init__(self):
        import comtypes
        import comtypes.client
        from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
        class Errors(IUnknown):
            _iid_ = GUID("{803E3BD4-2828-4410-8290-418D1D73C762}")
            _methods_ = [COMMETHOD([], HRESULT, "Next", (["out", "retval"], C.POINTER(C.POINTER(IUnknown)), "value"))]
        class Checker(IUnknown):
            _iid_ = GUID("{B6FD0B71-E2BC-4653-8D05-F197E412770B}")
            _methods_ = [COMMETHOD(["propget"], HRESULT, "LanguageTag", (["out", "retval"], C.POINTER(C.c_wchar_p), "value")),
                         COMMETHOD([], HRESULT, "Check", (["in"], C.c_wchar_p, "text"),
                                   (["out", "retval"], C.POINTER(C.POINTER(Errors)), "value"))]
        class Factory(IUnknown):
            _iid_ = GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")
            _methods_ = [COMMETHOD(["propget"], HRESULT, "SupportedLanguages", (["out", "retval"], C.POINTER(C.POINTER(IUnknown)), "value")),
                         COMMETHOD([], HRESULT, "IsSupported", (["in"], C.c_wchar_p, "language"),
                                   (["out", "retval"], C.POINTER(C.c_int), "value")),
                         COMMETHOD([], HRESULT, "CreateSpellChecker", (["in"], C.c_wchar_p, "language"),
                                   (["out", "retval"], C.POINTER(C.POINTER(Checker)), "value"))]
        factory = comtypes.client.CreateObject("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}", interface=Factory)
        self.checkers = [factory.CreateSpellChecker(language) for language in ("en-US", "de-DE")
                         if factory.IsSupported(language)]
        if not self.checkers:
            raise RuntimeError("No local English or German spell dictionary is installed")
        self.complete = len(self.checkers) == 2

    def is_word(self, word: str) -> bool:
        if not self.complete and ConservativeWords().is_word(word):
            return True
        for checker in self.checkers:
            if not checker.Check(word).Next():
                return True
        return False


class _EnchantWords:
    def __init__(self):
        path = ctypes.util.find_library("enchant-2") or ctypes.util.find_library("enchant")
        if not path:
            raise RuntimeError("No local Enchant spelling dictionary")
        self.lib = C.CDLL(path)
        self.lib.enchant_broker_init.restype = C.c_void_p
        self.lib.enchant_broker_request_dict.argtypes = [C.c_void_p, C.c_char_p]
        self.lib.enchant_broker_request_dict.restype = C.c_void_p
        self.lib.enchant_dict_check.argtypes = [C.c_void_p, C.c_char_p, C.c_ssize_t]
        self.lib.enchant_dict_check.restype = C.c_int
        self.lib.enchant_broker_free_dict.argtypes = [C.c_void_p, C.c_void_p]
        self.lib.enchant_broker_free.argtypes = [C.c_void_p]
        self.broker = self.lib.enchant_broker_init()
        if not self.broker:
            raise RuntimeError("The local spelling dictionary could not be opened")
        self.dictionaries = [dictionary for language in (b"en_US", b"de_DE")
                             if (dictionary := self.lib.enchant_broker_request_dict(self.broker, language))]
        if not self.dictionaries:
            raise RuntimeError("No local English or German spell dictionary is installed")
        self.complete = len(self.dictionaries) == 2

    def is_word(self, word: str) -> bool:
        if not self.complete and ConservativeWords().is_word(word):
            return True
        encoded = word.encode("utf-8")
        return any(self.lib.enchant_dict_check(dictionary, encoded, len(encoded)) != 1
                   for dictionary in self.dictionaries)

    def __del__(self):
        if getattr(self, "broker", None):
            for dictionary in getattr(self, "dictionaries", []):
                self.lib.enchant_broker_free_dict(self.broker, dictionary)
            self.lib.enchant_broker_free(self.broker)


class SystemWords:
    """Use installed dictionaries; absence conservatively suppresses ambiguous lowercase changes."""
    def __init__(self):
        self._implementation = None

    def is_word(self, word: str) -> bool:
        if self._implementation is None:
            try:
                self._implementation = _WindowsWords() if sys.platform == "win32" else _EnchantWords()
            except Exception:
                self._implementation = ConservativeWords()
        try:
            return self._implementation.is_word(word)
        except Exception:
            return True  # a failing dictionary must never turn a rewrite into a learned correction
