"""Folder-owned vLLM backend entry point."""

from .backend import create_backend

__all__ = ["create_backend"]
