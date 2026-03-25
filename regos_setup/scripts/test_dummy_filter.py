"""
title: RegOS Test Filter (Dummy)
description: A harmless test filter that prepends a small tag to every response. Used to verify the registration script works. Safe to delete after testing.
author: APAS AI
version: 0.0.1
"""

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=99,
            description="Filter execution priority. Higher = runs later."
        )
        tag_text: str = Field(
            default="[RegOS Test]",
            description="Text tag prepended to responses. Change this to verify valves work."
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """Pass-through — does nothing to the incoming message."""
        return body

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Prepends a small tag to the assistant's last message."""
        messages = body.get("messages", [])
        if messages and messages[-1].get("role") == "assistant":
            content = messages[-1].get("content", "")
            messages[-1]["content"] = f"{self.valves.tag_text} {content}"
        return body
