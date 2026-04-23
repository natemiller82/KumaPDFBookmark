"""
Optional Ollama integration for classifying ambiguous heading candidates.

Usage (internal — called by extractor.py):
    classifier = OllamaClassifier(model="mistral-nemo")
    labels = classifier(["Introduction", "3.1 Overview", "Figure 2a"])
    # → ["H1", "H2", "BODY"]

The returned callable matches the signature expected by extractor.extract_outline().
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Callable

from apb.config import LLM_SYSTEM_PROMPT, OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL, OLLAMA_TIMEOUT


class OllamaClassifier:
    """
    Wraps an Ollama /api/chat endpoint to classify heading candidates.

    Implements __call__ so it can be passed directly as the *use_llm*
    argument to extractor.extract_outline().
    """

    def __init__(
        self,
        model: str = OLLAMA_DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = OLLAMA_TIMEOUT,
        verbose: bool = False,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose

    def __call__(self, candidates: list[str]) -> list[str]:
        """
        Classify each candidate as H1, H2, H3, or BODY.

        Falls back to "BODY" for any candidate that cannot be classified
        (network error, unexpected response, etc.).
        """
        labels: list[str] = []
        for text in candidates:
            label = self._classify_one(text)
            labels.append(label)
        return labels

    def _classify_one(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        url = f"{self.base_url}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                raw = body["message"]["content"].strip().upper().split()[0]
                if raw in {"H1", "H2", "H3", "BODY"}:
                    if self.verbose:
                        print(f"[llm] '{text[:40]}' → {raw}")
                    return raw
                return "BODY"
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as exc:
            if self.verbose:
                print(f"[llm] Classification failed for '{text[:40]}': {exc}")
            return "BODY"

    def ping(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            url = f"{self.base_url}/api/tags"
            with urllib.request.urlopen(url, timeout=5):
                return True
        except Exception:
            return False


def build_classifier(
    model: str = OLLAMA_DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    verbose: bool = False,
) -> Callable[[list[str]], list[str]] | None:
    """
    Construct an OllamaClassifier and verify connectivity.
    Returns None (with a warning) if Ollama is unreachable.
    """
    clf = OllamaClassifier(model=model, base_url=base_url, verbose=verbose)
    if not clf.ping():
        print(
            f"[llm] WARNING: Ollama not reachable at {base_url}. "
            "LLM classification disabled."
        )
        return None
    if verbose:
        print(f"[llm] Connected to Ollama at {base_url}, model={model}")
    return clf
