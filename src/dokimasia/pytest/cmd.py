from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

MatcherMode = Literal["ordered", "contains", "span", "prefix", "exact"]
PatternInput = Sequence[str | Sequence[str]]
PatternAlternativesInput = Sequence[PatternInput]
TokenGroup = tuple[str, ...]
CompiledPattern = tuple[TokenGroup, ...]
WherePredicate = Callable[["CommandInvocation"], bool]

_SUPPORTED_MODES = {"ordered", "contains", "span", "prefix", "exact"}
_MISSING = object()


@dataclass(frozen=True)
class CommandInvocation:
    """Normalized top-level command invocation consumed by command matchers."""

    executable: str
    argv: list[str]
    raw: Any
    source: str | None = None
    root: str | None = None
    exit_code: int | None = None


@dataclass(frozen=True)
class CommandMatcher:
    """Static matcher for observed top-level executable invocations."""

    executable: str
    patterns: tuple[CompiledPattern, ...]
    mode: MatcherMode
    label: str
    where: WherePredicate | None = None

    def matches(self, invocation: Any) -> bool:
        command = normalize_invocation(invocation)
        if command.executable != self.executable:
            return False
        if not any(_pattern_matches(command.argv, pattern, self.mode) for pattern in self.patterns):
            return False
        if self.where is not None and not self.where(command):
            return False
        return True

    def __call__(self, invocation: Any) -> bool:
        return self.matches(invocation)

    def filter(self, invocations: Sequence[Any]) -> list[CommandInvocation]:
        return [normalize_invocation(invocation) for invocation in invocations if self.matches(invocation)]


def match(
    executable: str,
    *,
    pattern: PatternInput | None = None,
    patterns: PatternAlternativesInput | None = None,
    mode: MatcherMode = "ordered",
    where: WherePredicate | None = None,
    label: str | None = None,
) -> CommandMatcher:
    """Create a static command matcher for a top-level executable invocation."""

    if not executable:
        raise ValueError("executable is required")
    if mode not in _SUPPORTED_MODES:
        raise ValueError(f"unsupported command matcher mode: {mode}")
    if pattern is not None and patterns is not None:
        raise ValueError("use either pattern or patterns, not both")

    compiled_patterns = _compile_patterns(pattern=pattern, patterns=patterns)
    return CommandMatcher(
        executable=executable,
        patterns=compiled_patterns,
        mode=mode,
        label=label or _generate_label(executable, compiled_patterns),
        where=where,
    )


def normalize_invocation(invocation: Any) -> CommandInvocation:
    if isinstance(invocation, CommandInvocation):
        return invocation

    executable = _field(invocation, "executable")
    source = _field(invocation, "source")
    root = _field(invocation, "root")
    if executable is _MISSING:
        executable = source if source is not _MISSING else root
    if executable is _MISSING or executable is None or executable == "":
        raise ValueError("command invocation must include executable, source, or root")

    argv = _field(invocation, "argv")
    if argv is _MISSING or argv is None:
        argv = []

    exit_code = _field(invocation, "exit_code")
    if exit_code is _MISSING:
        exit_code = None

    return CommandInvocation(
        executable=str(executable),
        argv=[str(token) for token in argv],
        raw=invocation,
        source=None if source is _MISSING else str(source),
        root=None if root is _MISSING else str(root),
        exit_code=None if exit_code is None else int(exit_code),
    )


def _field(invocation: Any, name: str) -> Any:
    if isinstance(invocation, Mapping):
        return invocation.get(name, _MISSING)
    return getattr(invocation, name, _MISSING)


def _compile_patterns(
    *,
    pattern: PatternInput | None,
    patterns: PatternAlternativesInput | None,
) -> tuple[CompiledPattern, ...]:
    if patterns is None:
        return (_compile_pattern(pattern),)

    if len(patterns) == 0:
        raise ValueError("patterns must include at least one alternative")
    return tuple(_compile_pattern(alternative) for alternative in patterns)


def _compile_pattern(pattern: PatternInput | None) -> CompiledPattern:
    if pattern is None:
        return ()
    if isinstance(pattern, str):
        return ((pattern,),)

    groups: list[TokenGroup] = []
    for item in pattern:
        if isinstance(item, str):
            group = (item,)
        else:
            group = tuple(str(token) for token in item)
        if len(group) == 0:
            raise ValueError("pattern token groups must not be empty")
        groups.append(group)
    return tuple(groups)


def _generate_label(executable: str, patterns: tuple[CompiledPattern, ...]) -> str:
    first_pattern = patterns[0] if patterns else ()
    parts = [executable]
    parts.extend(group[0] for group in first_pattern)
    return ".".join(parts)


def _pattern_matches(argv: list[str], pattern: CompiledPattern, mode: MatcherMode) -> bool:
    if mode == "ordered":
        return _matches_ordered(argv, pattern)
    if mode == "contains":
        return _matches_contains(argv, pattern)
    if mode == "span":
        return _matches_span(argv, pattern)
    if mode == "prefix":
        return _matches_prefix(argv, pattern)
    if mode == "exact":
        return _matches_exact(argv, pattern)
    raise ValueError(f"unsupported command matcher mode: {mode}")


def _token_matches(token: str, group: TokenGroup) -> bool:
    return token in group


def _matches_ordered(argv: list[str], pattern: CompiledPattern) -> bool:
    position = 0
    for group in pattern:
        for index in range(position, len(argv)):
            if _token_matches(argv[index], group):
                position = index + 1
                break
        else:
            return False
    return True


def _matches_contains(argv: list[str], pattern: CompiledPattern) -> bool:
    return all(any(_token_matches(token, group) for token in argv) for group in pattern)


def _matches_span(argv: list[str], pattern: CompiledPattern) -> bool:
    if len(pattern) == 0:
        return True
    if len(pattern) > len(argv):
        return False
    width = len(pattern)
    return any(_tokens_match_groups(argv[start : start + width], pattern) for start in range(0, len(argv) - width + 1))


def _matches_prefix(argv: list[str], pattern: CompiledPattern) -> bool:
    if len(pattern) > len(argv):
        return False
    return _tokens_match_groups(argv[: len(pattern)], pattern)


def _matches_exact(argv: list[str], pattern: CompiledPattern) -> bool:
    if len(argv) != len(pattern):
        return False
    return _tokens_match_groups(argv, pattern)


def _tokens_match_groups(tokens: Sequence[str], pattern: CompiledPattern) -> bool:
    return all(_token_matches(token, group) for token, group in zip(tokens, pattern, strict=True))


__all__ = [
    "CommandInvocation",
    "CommandMatcher",
    "match",
    "normalize_invocation",
]
