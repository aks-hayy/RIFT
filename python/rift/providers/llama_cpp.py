"""Compatibility import for the folder-owned backend implementation."""

import subprocess  # compatibility surface for existing tests and embedders
import platform  # compatibility surface for existing tests and embedders

from ..backends.llama_cpp.backend import LlamaCppProvider

__all__ = ["LlamaCppProvider"]
