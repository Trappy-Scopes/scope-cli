"""
Claude as a detector.

An instrument whose output happens to be language: an image goes in, an
observation comes out. It reads and reports; it drives nothing. That is
deliberate -- an agent that *decides what to do next* and calls other devices
would be a second driver of the scope, which breaks the rule that only an
Experiment drives hardware. If that is ever wanted, it belongs on the `exp`
side, not in the ScopeAssembly.

Declare it like any other device:

	ScopeAssembly:
	  claude:
	    description: "Claude - reads frames and reports what it sees."
	    kind: detectors.claude.ClaudeDetector
	    args: []
	    kwargs:
	      model: claude-opus-5

Note there is no `api_key` kwarg, on purpose. `trappyconfig.yaml` is rsynced
to the file server by the `config_server` block, so a key placed there would
leave the machine. The SDK reads ANTHROPIC_API_KEY from the environment --
set it in the shell profile or a secrets file outside the repo and outside
the synced config.

Requires an Anthropic API key, which is billed per token through the Console
and is *not* covered by a Claude Pro/Max subscription.
"""

import base64
import logging as log
import mimetypes
import os


class ClaudeDetector:
	"""
	A detector backed by the Claude API.
	"""

	def __init__(self, name="claude", model="claude-opus-5", system=None,
				 max_tokens=2048):
		self.name = name
		self.model = model
		self.max_tokens = max_tokens
		self.system = system or (
			"You are observing microscopy frames from a Trappy-Scopes "
			"microscope in a yeast lab. Report only what is visible. Say "
			"plainly when something is unclear rather than guessing."
		)
		self.config = {"model": model, "max_tokens": max_tokens}
		self._client = None

	def __repr__(self):
		return f"< ClaudeDetector :: {self.name} :: {self.model} >"

	@property
	def client(self):
		"""
		The API client, built on first use.

		Deliberately lazy: ScopeAssembly.open() constructs every device at
		boot and raises on failure, so building the client in __init__ would
		mean a missing API key takes down the whole assembly. This way the
		device mounts fine and only fails if you actually ask it to read.
		"""
		if self._client is None:
			import anthropic  # imported late for the same reason
			self._client = anthropic.Anthropic()
		return self._client

	def read(self, imgpath, prompt="Describe what you see. Note anything anomalous."):
		"""
		The detector `read` contract: image path in, observation out.

		imgpath: path to an image emitted by another device (e.g. exp.newfile).
		prompt:  what to ask about this frame.
		"""
		if not os.path.exists(imgpath):
			raise FileNotFoundError(imgpath)

		media_type = mimetypes.guess_type(imgpath)[0] or "image/png"
		with open(imgpath, "rb") as f:
			data = base64.standard_b64encode(f.read()).decode("utf-8")

		message = self.client.messages.create(
			model=self.model,
			max_tokens=self.max_tokens,
			system=self.system,
			messages=[{
				"role": "user",
				"content": [
					{"type": "image", "source": {"type": "base64",
					 "media_type": media_type, "data": data}},
					{"type": "text", "text": prompt},
				],
			}],
		)

		text = "".join(b.text for b in message.content if b.type == "text")
		log.info(f"{self.name}: read {os.path.basename(imgpath)} "
				 f"({message.usage.input_tokens} in / "
				 f"{message.usage.output_tokens} out)")
		return text

	def ask(self, question):
		"""
		Ask without an image -- useful for summarising notes at the prompt.
		"""
		message = self.client.messages.create(
			model=self.model,
			max_tokens=self.max_tokens,
			system=self.system,
			messages=[{"role": "user", "content": question}],
		)
		return "".join(b.text for b in message.content if b.type == "text")
