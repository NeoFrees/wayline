"""Guardian's language layer: understanding occupants and writing the alert.

Design rule: **AI helps the call happen faster and clearer; it never decides whether
help is called.** Escalation timing lives in deterministic code (incident.py). Every
AI path here has a deterministic twin that is used whenever the model is unavailable,
slow, refuses, or returns anything that fails validation:

    KeywordInterpreter  <- ClaudeInterpreter falls back to it (and it may veto a cancel)
    TemplateComposer    <- ClaudeComposer falls back to it

Privacy: the model never receives coordinates or timestamps. It writes {location},
{maps_url} and {time} placeholders that code fills in with the latest GPS fix.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

from .report import IncidentReport
from .types import IncidentKind, Severity

DEFAULT_MODEL = os.environ.get("WAYLINE_AI_MODEL", "claude-opus-5-5")


# --------------------------------------------------------------------------------------
# Understanding what the occupant said
# --------------------------------------------------------------------------------------

class Intent(str, Enum):
    OKAY = "okay"        # clearly fine, cancel
    HELP = "help"        # wants help / not okay / danger
    INJURY = "injury"    # injury or medical symptoms mentioned
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class Interpretation:
    intent: Intent
    injuries: tuple[str, ...] = ()
    summary: str = ""
    source: str = "keywords"


class ResponseInterpreter(Protocol):
    def interpret(self, text: str, *, asked_if_okay: bool = True) -> Interpretation: ...


# Longest phrases first so "no need to call" is removed before "no need".
_CANCEL_PHRASES = sorted([
    "i'm okay", "i am okay", "im okay", "i'm ok", "i am ok", "im ok", "i'm fine", "i am fine",
    "im fine", "i'm alright", "i'm all right", "i am alright", "i'm good", "we're fine",
    "we are fine", "we're okay", "we are okay", "we're ok", "we're good", "all good",
    "everyone's fine", "everyone is fine", "everybody's fine", "everyone's okay",
    "nobody's hurt", "nobody is hurt", "no one is hurt", "no one's hurt", "not hurt",
    "don't call", "do not call", "dont call", "don't call anyone", "no need to call",
    "no need for help", "no need", "don't need help", "do not need help", "dont need help",
    "don't need an ambulance", "no ambulance", "cancel", "false alarm", "never mind",
    "nevermind", "no help needed", "it's fine", "it's okay",
], key=len, reverse=True)
_NOT_OKAY = ("not okay", "not ok", "not fine", "not alright", "not all right", "not good")
_INJURY_TERMS = (
    "hurt", "injur", "bleed", "blood", "pain", "broken", "broke my", "unconscious",
    "passed out", "not breathing", "can't breathe", "cannot breathe", "chest", "dizzy",
    "seizure", "heart attack", "stroke", "can't feel", "cannot feel", "burn", "concussion",
    "pregnant", "not waking", "won't wake", "wont wake", "fainted",
)
_HELP_TERMS = (
    "help", "call", "emergency", "ambulance", "police", "fire", "smoke", "trapped", "stuck",
    "pinned", "can't move", "cannot move", "can't get out", "911", "112", "999", "sos",
)
_SOS_PHRASES = (
    "call for help", "call 911", "call nine one one", "call an ambulance", "call the police",
    "call 112", "call 999", "emergency", "i need help", "we need help", "help me", "sos",
    "get help", "send help",
)
_YES = {"yes", "yeah", "yep", "yup", "yes i am", "i am"}
_NO = {"no", "nope", "nah", "no i'm not", "no im not"}


def _normalize(text: str) -> str:
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_help_request(text: str) -> bool:
    """Wake-phrase style SOS detection used while no incident is active (on-device only)."""
    t = _normalize(text)
    for phrase in _CANCEL_PHRASES:
        t = t.replace(phrase, " ")
    return any(p in t for p in _SOS_PHRASES)


class KeywordInterpreter:
    """Deterministic, offline interpretation. Conservative: mixed signals mean HELP."""

    def interpret(self, text: str, *, asked_if_okay: bool = True) -> Interpretation:
        t = _normalize(text)
        if not t:
            return Interpretation(Intent.UNCLEAR)
        if asked_if_okay and t in _YES:
            return Interpretation(Intent.OKAY, summary="Said yes to 'are you okay'")
        if asked_if_okay and t in _NO:
            return Interpretation(Intent.HELP, summary="Said no to 'are you okay'")

        not_okay = any(p in t for p in _NOT_OKAY)
        rest = t
        for p in _NOT_OKAY:
            rest = rest.replace(p, " ")
        has_okay = False
        for phrase in _CANCEL_PHRASES:
            if phrase in rest:
                has_okay = True
                rest = rest.replace(phrase, " ")
        injury = any(term in rest for term in _INJURY_TERMS)
        helpish = not_okay or any(term in rest for term in _HELP_TERMS)

        if injury:
            return Interpretation(Intent.INJURY, injuries=(text.strip(),), summary="Reported injury or symptoms")
        if helpish:
            return Interpretation(Intent.HELP, summary="Asked for help")
        if has_okay:
            return Interpretation(Intent.OKAY, summary="Said they are okay")
        return Interpretation(Intent.UNCLEAR)


# --------------------------------------------------------------------------------------
# Writing the alert
# --------------------------------------------------------------------------------------

PLACEHOLDERS = ("{location}", "{maps_url}", "{time}")


@dataclass(frozen=True)
class IncidentBrief:
    dispatcher_script: str   # read aloud to a response-center / emergency operator
    contact_message: str     # SMS to emergency contacts
    source: str = "template"  # "template" | "ai"

    def finalize(self, report: IncidentReport) -> "IncidentBrief":
        """Fill placeholders with the latest facts (location is never paraphrased by AI)."""
        def fill(s: str) -> str:
            return (s.replace("{location}", report.location_spoken)
                     .replace("{maps_url}", report.maps_url)
                     .replace("{time}", report.time_utc[11:16] + " UTC"))
        return replace(self, dispatcher_script=fill(self.dispatcher_script),
                       contact_message=fill(self.contact_message))


class BriefComposer(Protocol):
    remote: bool

    def compose(self, report: IncidentReport) -> IncidentBrief: ...


def _quote(s: str, limit: int = 120) -> str:
    s = s.strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _said(prefix: str, s: str, limit: int = 120) -> str:
    """'Occupant said: "Please hurry."' — closing punctuation stays inside the quote, once."""
    q = _quote(s, limit)
    end = "" if q.endswith((".", "!", "?", "…")) else "."
    return f'{prefix}: "{q}{end}"'


class TemplateComposer:
    """Deterministic wording. Always available, used as the fallback for AI."""

    remote = False

    def compose(self, report: IncidentReport) -> IncidentBrief:
        what = report.what
        verb = "came from a vehicle at" if report.kind == IncidentKind.MANUAL_SOS else "was detected at"
        parts = [
            "This is an automated emergency alert from the Wayline vehicle safety system.",
            f"{what[0].upper() + what[1:]} {verb} {{location}}.",
            f"Vehicle: {report.vehicle}. Driver: {report.driver_name}.",
        ]
        c = report.crash
        if c is not None:
            crash_bits = []
            if c.delta_v_kph > 0:
                crash_bits.append(f"Estimated change in speed {c.delta_v_kph:.0f} kilometers per hour.")
            if c.airbag:
                crash_bits.append("Airbags deployed.")
            if c.rollover:
                crash_bits.append("Possible rollover.")
            parts.extend(crash_bits)
        if report.injuries:
            parts.append(_said("Occupant reports", report.injuries[-1]))
        elif report.statements:
            parts.append(_said("Occupant said", report.statements[-1]))
        else:
            parts.append("Occupants did not respond to voice prompts.")
        for action in report.actions_taken:
            if "stop" in action.lower():
                parts.append(action.rstrip(".") + ".")
        if report.medical_notes:
            parts.append(f"Medical notes shared by the driver: {_quote(report.medical_notes, 160)}.")
        script = " ".join(parts)

        first = report.driver_name.split()[0] if report.driver_name else "The driver"
        if report.kind == IncidentKind.UNRESPONSIVE_DRIVER:
            lead = f"{first} stopped responding while driving at {{time}}. Wayline is stopping the car safely in its lane."
        elif report.kind == IncidentKind.MANUAL_SOS:
            lead = f"{first}'s car requested emergency help at {{time}}."
        else:
            lead = f"{first} may need help: {what} was detected at {{time}}."
        if report.injuries:
            status = "Injury reported."
        elif report.statements:
            status = _said("They said", report.statements[-1], 60)
        else:
            status = "No answer to the voice check-in."
        sent = ("Wayline's response center is arranging help." if report.plan == "plus"
                else "Please call them or emergency services.")
        sms = f"Wayline Guardian: {lead} {status} {sent} Location: {{maps_url}}"
        if len(sms) > 280:
            sms = f"Wayline Guardian: {lead} {sent} Location: {{maps_url}}"
        return IncidentBrief(script, sms, "template")


# --------------------------------------------------------------------------------------
# Claude-backed implementations
# --------------------------------------------------------------------------------------

class AIUnavailable(RuntimeError):
    """The model could not produce a usable answer in time; callers fall back."""


class ClaudeJSON:
    """Small structured-output helper with an emergency-grade latency budget."""

    def __init__(self, client: Any = None, *, model: str = DEFAULT_MODEL,
                 timeout_s: float = 8.0, effort: str = "low"):
        if client is None:
            import anthropic  # optional dependency: pip install "wayline[ai]"

            client = anthropic.Anthropic(timeout=timeout_s, max_retries=1)
        self.client = client
        self.model = model
        self.effort = effort

    def ask(self, system: str, payload: dict, schema: dict) -> dict:
        try:
            import anthropic
            api_errors: tuple = (anthropic.APITimeoutError, anthropic.APIConnectionError,
                                 anthropic.RateLimitError, anthropic.APIStatusError)
        except ImportError:  # running with an injected test client
            api_errors = ()
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=2048,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except api_errors as exc:
            raise AIUnavailable(f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:  # never let the language layer break an emergency flow
            raise AIUnavailable(f"unexpected {type(exc).__name__}: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIUnavailable("model declined")
        if response.stop_reason == "max_tokens":
            raise AIUnavailable("output truncated")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
        if not text:
            raise AIUnavailable("no text in response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIUnavailable("invalid JSON") from exc
        if not isinstance(data, dict):
            raise AIUnavailable("unexpected JSON shape")
        return data


_INTERPRET_SYSTEM = """You classify what a vehicle occupant said in reply to an automated safety \
check-in from Wayline Guardian after a possible emergency (crash, unresponsive driver, or SOS).
The input JSON has the check-in question and what the occupant said (speech-to-text, may be garbled).
Choose exactly one intent:
- "okay": they clearly say they are fine and do not want help.
- "help": they want help, say they are not okay, mention danger (fire, smoke, trapped), or ask you to call someone.
- "injury": anyone mentions an injury, pain, bleeding, unconsciousness, or medical symptoms.
- "unclear": anything else, including partial, garbled, or ambiguous speech.
If the reply mixes "okay" with any sign of help or injury, do not choose "okay".
injuries: injuries or symptoms mentioned, in the occupant's own words (empty list if none).
summary: one short factual sentence a dispatcher could read."""

_INTERPRET_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["okay", "help", "injury", "unclear"]},
        "injuries": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["intent", "injuries", "summary"],
    "additionalProperties": False,
}


class ClaudeInterpreter:
    """Claude understands nuanced replies; keywords stay in charge of the risky direction.

    - Keywords say HELP/INJURY  -> escalate immediately, without waiting for the model.
    - Model says HELP/INJURY    -> escalate.
    - Cancel needs the model to say OKAY and the keywords not to object.
    - Model unavailable          -> keyword result.
    """

    def __init__(self, llm: ClaudeJSON | None = None, keywords: KeywordInterpreter | None = None):
        self.llm = llm or ClaudeJSON()
        self.keywords = keywords or KeywordInterpreter()
        self.last_error: str | None = None

    def interpret(self, text: str, *, asked_if_okay: bool = True) -> Interpretation:
        kw = self.keywords.interpret(text, asked_if_okay=asked_if_okay)
        if kw.intent in (Intent.HELP, Intent.INJURY):
            return kw
        question = "Are you okay?" if asked_if_okay else "Say 'cancel' to stop the call for help."
        try:
            data = self.llm.ask(_INTERPRET_SYSTEM, {"check_in_question": question, "occupant_said": text},
                                _INTERPRET_SCHEMA)
            ai_intent = Intent(data["intent"])
            injuries = tuple(str(i) for i in data.get("injuries", []) if str(i).strip())
            summary = str(data.get("summary", ""))[:200]
        except (AIUnavailable, KeyError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return kw
        if injuries and ai_intent != Intent.INJURY:
            ai_intent = Intent.INJURY  # any injury mention is treated as an injury report
        # kw can only be OKAY or UNCLEAR here. kw OKAY + model UNCLEAR stays UNCLEAR (keep asking).
        return Interpretation(ai_intent, injuries, summary, source="ai")


_COMPOSE_SYSTEM = """You write emergency notifications for Wayline Guardian, an in-vehicle safety system.
Use only the facts in the incident JSON. Never invent injuries, people, places, landmarks or numbers. \
Never give medical advice. Never write coordinates, addresses or clock times yourself — use the placeholders.
Return two texts:
1. dispatcher_script: read aloud by a voice line to an emergency response operator. At most 70 words, \
plain sentences, most important first: what happened, where (write the literal placeholder {location} \
exactly once), vehicle description, occupant status and their own words, crash indicators (change in \
speed, airbag, rollover), and medical notes only if provided.
2. contact_message: a text message to the driver's emergency contact. At most 260 characters before \
placeholders are filled. Calm and factual: who may need help, what happened, when (write {time}), \
what is already being done according to actions_taken, and where (end the message with the \
literal placeholder {maps_url}, used exactly once)."""

_COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "dispatcher_script": {"type": "string"},
        "contact_message": {"type": "string"},
    },
    "required": ["dispatcher_script", "contact_message"],
    "additionalProperties": False,
}

_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


def validate_ai_brief(script: str, sms: str) -> str | None:
    """Return a reason the AI wording is unusable, or None if it passes."""
    if script.count("{location}") != 1:
        return "dispatcher script must contain {location} exactly once"
    if sms.count("{maps_url}") != 1:
        return "contact message must contain {maps_url} exactly once"
    for text in (script, sms):
        unknown = [p for p in _PLACEHOLDER_RE.findall(text) if p not in PLACEHOLDERS]
        if unknown:
            return f"unknown placeholder {unknown[0]}"
    if len(script) > 700 or len(script.split()) > 90:
        return "dispatcher script too long"
    if len(sms) > 280:
        return "contact message too long"
    if re.search(r"-?\d{1,3}\.\d{3,}", script + " " + sms):
        return "model wrote coordinates"
    return None


class ClaudeComposer:
    """Writes clearer, situation-aware alerts; falls back to the template on any doubt."""

    remote = True

    def __init__(self, llm: ClaudeJSON | None = None, fallback: TemplateComposer | None = None):
        self.llm = llm or ClaudeJSON()
        self.fallback = fallback or TemplateComposer()
        self.last_error: str | None = None

    def compose(self, report: IncidentReport) -> IncidentBrief:
        try:
            data = self.llm.ask(_COMPOSE_SYSTEM, report.facts_for_ai(), _COMPOSE_SCHEMA)
            script = str(data["dispatcher_script"]).strip()
            sms = str(data["contact_message"]).strip()
        except (AIUnavailable, KeyError, TypeError) as exc:
            self.last_error = str(exc)
            return self.fallback.compose(report)
        problem = validate_ai_brief(script, sms)
        if problem:
            self.last_error = problem
            return self.fallback.compose(report)
        return IncidentBrief(script, sms, "ai")


def severity_for_sos(interp: Interpretation) -> Severity:
    return Severity.SEVERE if interp.intent == Intent.INJURY else Severity.MODERATE


__all__ = [
    "AIUnavailable", "BriefComposer", "ClaudeComposer", "ClaudeInterpreter", "ClaudeJSON",
    "DEFAULT_MODEL", "IncidentBrief", "Intent", "Interpretation", "IncidentKind",
    "KeywordInterpreter", "ResponseInterpreter", "TemplateComposer", "is_help_request",
    "severity_for_sos", "validate_ai_brief",
]
