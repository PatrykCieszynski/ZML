from __future__ import annotations

import random
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GenConfig:
	# How many lines to write total (including multi-line expansions).
	total_lines: int = 10000
	# Chance to write a mining-related System line.
	p_system_mining: float = 0.35
	# Chance to write a public channel line.
	p_public: float = 0.50
	# Chance to write a Globals line.
	p_globals: float = 0.10
	# Chance to write a multi-line "tower" message (rare edge-case).
	p_tower_multiline: float = 0.01
	# If set, add real delays between writes to simulate tailing.
	sleep_ms_min: int = 150
	sleep_ms_max: int = 350
	# Seed for deterministic outputs.
	seed: int = 1234


class ChatLogGenerator:
	"""
	Generates Entropia-like chat.log lines with realistic mining-related System messages,
	mixed with public channels and globals. Can optionally emit a rare multiline tower message.
	"""

	def __init__(self, cfg: GenConfig) -> None:
		self._cfg = cfg
		self._rng = random.Random(cfg.seed)

		self._public_channels = [
			"#calytrade",
			"#arktrade",
			"#cyrenetrade",
			"#rocktrading",
			"Rookie",
		]

		self._avatars = [
			"Zabujca Sheaki Ortografjii",
			"Nark Oo Allon",
			"Mr TERN-- Sir",
			"Drax Thunderclaw Bloodshot",
			"Maya Drisara Meussa",
			"Aleksandr Borcuha Koltsov",
		]

		self._resources = [
			"Yellow Crystal",
			"Blue Crystal",
			"Zorn Star Ore",
			"Oil",
			"Crude Oil",
			"Belkar",
		]

		self._mobs = [
			"Fenris Elite Guard",
			"Thunderous Golem",
			"Snablesnot",
		]

	def iter_lines(self, start_dt: datetime | None = None) -> Iterable[str]:
		"""
		Yield formatted chat.log lines.
		Timestamps are EU time (naive).
		"""
		dt = start_dt or datetime(2026, 1, 10, 12, 37, 0)

		produced = 0
		while produced < self._cfg.total_lines:
			dt = dt + timedelta(seconds=self._rng.randint(1, 7))

			# Rare multiline edge-case: tower message expands to 2 lines, both start with timestamp/header.
			if self._rng.random() < self._cfg.p_tower_multiline:
				for ln in self._gen_tower_multiline(dt):
					yield ln
					produced += 1
					if produced >= self._cfg.total_lines:
						return
				self._maybe_sleep()
				continue

			r = self._rng.random()
			if r < self._cfg.p_system_mining:
				yield self._gen_system_mining(dt)
			elif r < self._cfg.p_system_mining + self._cfg.p_globals:
				yield self._gen_globals(dt)
			else:
				yield self._gen_public(dt)

			produced += 1
			self._maybe_sleep()

	def write_file(self, path: Path, start_dt: datetime | None = None, mode: str = "a") -> None:
		"""
		Write generated lines to a file.
		mode="a" for append (tail-friendly), mode="w" to overwrite.
		"""
		path.parent.mkdir(parents=True, exist_ok=True)
		with path.open(mode, encoding="utf-8", newline="\n") as f:
			for ln in self.iter_lines(start_dt=start_dt):
				f.write(ln)
				f.write("\n")
				f.flush()

	# ---------- Internals ----------

	def _maybe_sleep(self) -> None:
		if self._cfg.sleep_ms_max <= 0:
			return
		lo = max(0, self._cfg.sleep_ms_min)
		hi = max(lo, self._cfg.sleep_ms_max)
		time.sleep(self._rng.randint(lo, hi) / 1000.0)

	def _fmt(self, dt: datetime, channel: str, speaker: str, msg: str) -> str:
		# Matches: "YYYY-MM-DD HH:MM:SS [Channel] [Speaker] message"
		return f"{dt:%Y-%m-%d %H:%M:%S} [{channel}] [{speaker}] {msg}"

	def _gen_public(self, dt: datetime) -> str:
		ch = self._rng.choice(self._public_channels)
		who = self._rng.choice(self._avatars)
		msg = self._rng.choice(
			[
				"WTB:[Omegaton A101]",
				"WTS [Christmas Strongbox] 300 for 0.67",
				"selling SWEAT, Punk, Weeds, [Mind Essence]",
				"wrong chat",
				"wts laser amp alpha-beta lot of them",
			]
		)
		return self._fmt(dt, ch, who, msg)

	def _gen_globals(self, dt: datetime) -> str:
		who = self._rng.choice(self._avatars)
		mob = self._rng.choice(self._mobs)
		val = self._rng.choice([50, 54, 76, 83, 202])
		msg = f"{who} killed a creature ({mob}) with a value of {val} PED!"
		return self._fmt(dt, "Globals", "", msg)

	def _gen_system_mining(self, dt: datetime) -> str:
		kind = self._rng.random()
		res = self._rng.choice(self._resources)

		# Rough mix that resembles your samples
		if kind < 0.25:
			# Claim found
			msg = f"You have claimed a resource! ({res})"
			return self._fmt(dt, "System", "", msg)

		if kind < 0.50:
			# Loot line
			qty = self._rng.choice([3, 4, 8, 11, 12, 15, 16, 24, 28, 30])
			# keep values in 0.01 multiples to avoid floating drift in generator itself
			val = self._rng.choice([0.06, 0.08, 0.11, 0.12, 0.16, 0.24, 0.28, 0.30])
			msg = f"You received {res} x ({qty}) Value: {val:.4f} PED"
			return self._fmt(dt, "System", "", msg)

		if kind < 0.65:
			# Depleted
			msg = "This resource is depleted"
			return self._fmt(dt, "System", "", msg)

		if kind < 0.80:
			# Waypoint add
			lon = self._rng.randint(137650, 138300)
			lat = self._rng.randint(75100, 76600)
			alt = self._rng.randint(90, 140)
			msg = f"Added waypoint to map: [position:16$(200/0/11)${lon},{lat},{alt}${res}]"
			return self._fmt(dt, "System", "", msg)

		# Position share line (manual bind)
		lon = self._rng.randint(137650, 138300)
		lat = self._rng.randint(75100, 76600)
		alt = self._rng.randint(90, 140)
		planet = self._rng.choice(["Planet Cyrene", "Calypso", "Arkadia"])
		msg = f"[{planet}, {lon}, {lat}, {alt}, Waypoint]"
		return self._fmt(dt, "System", "", msg)

	def _gen_tower_multiline(self, dt: datetime) -> list[str]:
		"""
		Tower message sometimes appears as multi-line in chat.log (historical edge-case).
		We emit two separate log lines with the same timestamp to mimic that.
		"""
		line1 = self._fmt(dt, "System", "", "Drill tower is still processing the resource.")
		line2 = self._fmt(
			dt,
			"System",
			"",
			f"Time left before next batch: {self._rng.randint(1, 48)} hour(s), {self._rng.randint(0, 59)} minute(s).",
		)
		return [line1, line2]


# ---- Convenience entrypoint (manual use) ----


def generate_chat_log(path: str, cfg: GenConfig | None = None) -> None:
	gen = ChatLogGenerator(cfg or GenConfig())
	gen.write_file(Path(path), mode="a")


if __name__ == "__main__":
	# Example: append ~200 mixed lines with small delays for tailing tests
	generate_chat_log(
		path="chat.log",
		cfg=GenConfig(total_lines=200, sleep_ms_min=20, sleep_ms_max=80, seed=42),
	)
