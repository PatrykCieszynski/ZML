from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from zml_backend.domain.money import Mpec
from zml_backend.domain.position import WorldPos
from zml_backend.inputs.chat.model import ChannelType, ChatLine
from zml_backend.inputs.chat.signals import (
    ChatSignalBase,
    EnhancerBrokeSignal,
    ItemReceivedSignal,
    PlayerPosWaypointSignal,
    ResourceClaimedSignal,
    ResourceDepletedSignal,
    SkillGainedSignal,
)

RE_ENHANCER_BROKE = re.compile(
    r"^Your enhancer (?P<enhancer_name>.+?) on your (?P<item_name>.+?) broke\."
    r" You have (?P<remaining>\d+) enhancers remaining on the item\."
    r"(?: You received (?P<value_ped>\d+(?:\.\d+)?) PED (?P<received_item>.+?)\.)?$"
)

RE_ITEM_RECEIVED = re.compile(
    r"^You received (?P<item_name>.+?) x \((?P<qty>\d+)\) Value: (?P<value_ped>\d+(?:\.\d+)?) PED$"
)

RE_RESOURCE_CLAIMED = re.compile(r"^You have claimed a resource! \((?P<resource_name>.+?)\)$")

RE_RESOURCE_DEPLETED = re.compile(r"^This resource is depleted$")

RE_POSITION_PING = re.compile(
    r"^\[(?P<planet_name>[^,\]]+),\s*(?P<x>-?\d+),\s*(?P<y>-?\d+),\s*(?P<z>-?\d+),\s*Waypoint]$"
)

RE_SKILL_GAINED = re.compile(
    r"^You have gained (?P<amount>\d+(?:\.\d+)?) experience in your (?P<skill>.+?) skill$"
)


def interpret_chat_line(line: ChatLine) -> ChatSignalBase | None:
    match line.channel_type:
        case ChannelType.SYSTEM:
            return _interpret_system(line)
        case ChannelType.GLOBALS:
            return _interpret_globals(line)
        case _:
            return None


def _interpret_system(line: ChatLine) -> ChatSignalBase | None:
    for matcher in _SYSTEM_MATCHERS:
        try:
            signal_output = matcher(line)
        except Exception:
            continue
        if signal_output is not None:
            return signal_output
    return None


# TODO track user globals and hofs
def _interpret_globals(_line: ChatLine) -> ChatSignalBase | None:
    return None


def _try_match_enhancer_broke(line: ChatLine) -> EnhancerBrokeSignal | None:
    matches = RE_ENHANCER_BROKE.match(line.message)
    if matches is None:
        return None

    enhancer_name = matches.group("enhancer_name")
    item_name = matches.group("item_name")
    remaining_str = matches.group("remaining")

    remaining = _parse_int(remaining_str)

    if remaining is None:
        return None

    return EnhancerBrokeSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
        enhancer_name=enhancer_name,
        item_name=item_name,
        remaining=remaining,
    )


def _try_match_item_received(line: ChatLine) -> ItemReceivedSignal | None:
    matches = RE_ITEM_RECEIVED.match(line.message)
    if matches is None:
        return None

    item_name = matches.group("item_name")
    qty_str = matches.group("qty")
    value_ped_str = matches.group("value_ped")

    qty = _parse_int(qty_str)
    value_mpec = _parse_ped_to_mpec(value_ped_str)

    if qty is None or value_mpec is None:
        return None

    return ItemReceivedSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
        item_name=item_name,
        qty=qty,
        value_mpec=value_mpec,
    )


def _try_match_resource_claimed(line: ChatLine) -> ResourceClaimedSignal | None:
    matches = RE_RESOURCE_CLAIMED.match(line.message)
    if matches is None:
        return None

    resource_name = matches.group("resource_name")

    return ResourceClaimedSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
        resource_name=resource_name,
    )


def _try_match_resource_depleted(line: ChatLine) -> ResourceDepletedSignal | None:
    matches = RE_RESOURCE_DEPLETED.match(line.message)
    if matches is None:
        return None

    return ResourceDepletedSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
    )


def _try_match_position_ping(line: ChatLine) -> PlayerPosWaypointSignal | None:
    matches = RE_POSITION_PING.match(line.message)
    if matches is None:
        return None

    planet_name = matches.group("planet_name")
    x_str = matches.group("x")
    y_str = matches.group("y")
    z_str = matches.group("z")

    x = _parse_int(x_str)
    y = _parse_int(y_str)
    z = _parse_int(z_str)

    if x is None or y is None or z is None:
        return None

    return PlayerPosWaypointSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
        position=WorldPos(planet_name=planet_name, x=x, y=y, z=z),
    )


def _try_match_skill_gained(line: ChatLine) -> SkillGainedSignal | None:
    matches = RE_SKILL_GAINED.match(line.message)
    if matches is None:
        return None

    skill = matches.group("skill")
    amount_str = matches.group("amount")

    amount = _parse_decimal(amount_str)
    if amount is None:
        return None

    return SkillGainedSignal(
        event_dt=line.event_dt,
        channel_type=line.channel_type,
        channel_token=line.channel_token,
        raw=line.raw,
        skill=skill,
        amount=amount,
    )


def _parse_decimal(s: str) -> Decimal | None:
    try:
        return Decimal(s)
    except (InvalidOperation, TypeError):
        return None


def _parse_int(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _parse_ped_to_mpec(s: str) -> Mpec | None:
    ped = _parse_decimal(s)
    if ped is None:
        return None

    mpec = ped * Decimal("100000")
    if mpec != mpec.to_integral_value():
        return None  # refuse lossy conversion

    return Mpec(int(mpec))


_SYSTEM_MATCHERS: tuple[Callable[[ChatLine], ChatSignalBase | None], ...] = (
    _try_match_enhancer_broke,
    _try_match_item_received,
    _try_match_resource_claimed,
    _try_match_resource_depleted,
    _try_match_position_ping,
    _try_match_skill_gained,
)
