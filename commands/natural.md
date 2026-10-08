---
description: Tell whether your last message (or the given text) sounds natural to a native speaker, without adding anything to the session context
argument-hint: "[text to check instead of your last message]"
disable-model-invocation: true
---

The cc-grammar-coach naturalness check normally answers this command itself and keeps it out of the conversation entirely, so if you are reading this, its hook did not run: it failed, timed out, or the plugin's LLM settings are missing.

Tell the user in one sentence that the naturalness check did not run and that they can retry the command or check the plugin's LLM settings in the /plugin menu. Do not judge the message yourself and do nothing else.
