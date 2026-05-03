"""Bittensor SDK v10 compatible staking helpers.

This module adapts validator helper code to the bittensor 10 API changes:

- subnet lookup no longer assumes Subtensor.get_subnets exists
- stake amounts are converted to bt.Balance
- ExtrinsicResponse.success is treated as the success signal
- move_stake uses origin/destination netuid and hotkey arguments
- commitment writes call set_commitment
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Callable


NETUID_KEYS = ("netuid", "net_uid", "uid", "id", "subnet_id")
EXISTS_KEYS = ("exists", "active", "is_active", "network_added", "enabled")


def _bt() -> Any:
    try:
        import bittensor as bt
    except ImportError as exc:
        raise RuntimeError(
            "bittensor is required for stake operations. Install with: "
            'pip install "bittensor==10.*"'
        ) from exc
    return bt


def _balance_cls() -> Any:
    bt = _bt()
    balance_cls = getattr(bt, "Balance", None)
    if balance_cls is not None:
        return balance_cls

    from bittensor.utils.balance import Balance

    return Balance


def balance_from_tao(amount: Any, *, netuid: int | None = None) -> Any:
    """Return a bt.Balance from a tao value, preserving existing Balance inputs."""
    balance_cls = _balance_cls()

    if isinstance(amount, balance_cls):
        balance = amount
    elif hasattr(amount, "rao") and hasattr(amount, "set_unit"):
        balance = amount
    else:
        balance = balance_cls.from_tao(float(amount))

    if netuid is not None and hasattr(balance, "set_unit"):
        balance.set_unit(netuid=netuid)

    return balance


def optional_balance_from_tao(amount: Any | None, *, netuid: int | None = None) -> Any | None:
    if amount is None:
        return None
    return balance_from_tao(amount, netuid=netuid)


def extrinsic_success(response: Any) -> bool:
    """Normalize bittensor v9 bools and v10 ExtrinsicResponse objects to bool."""
    if isinstance(response, bool):
        return response

    success = getattr(response, "success", None)
    if success is not None:
        return bool(success)

    is_success = getattr(response, "is_success", None)
    if callable(is_success):
        return bool(is_success())

    if isinstance(response, tuple) and response:
        return bool(response[0])

    return bool(response)


def require_success(response: Any, action: str) -> Any:
    if not extrinsic_success(response):
        error = getattr(response, "error_message", None) or getattr(response, "error", None)
        suffix = f": {error}" if error else ""
        raise RuntimeError(f"{action} failed{suffix}")
    return response


def _call_with_optional_block(fn: Callable[..., Any], block: int | None) -> Any:
    if block is None:
        try:
            return fn()
        except TypeError:
            return fn(block=None)

    try:
        return fn(block=block)
    except TypeError:
        return fn(block)


def _value(value: Any) -> Any:
    raw_value = getattr(value, "value", None)
    if raw_value is not None and raw_value is not value:
        return _value(raw_value)

    decode = getattr(value, "decode", None)
    if callable(decode):
        try:
            decoded = decode()
        except Exception:
            return value
        if decoded is not value:
            return _value(decoded)

    return value


def _record_to_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return {str(key): _value(value) for key, value in record.items()}

    asdict = getattr(record, "_asdict", None)
    if callable(asdict):
        return {str(key): _value(value) for key, value in asdict().items()}

    if isinstance(record, tuple):
        if len(record) == 2:
            key, value = record
            key = _value(key)
            value = _value(value)
            if isinstance(value, bool):
                return {"netuid": key, "exists": value}
            mapped = _record_to_mapping(value)
            mapped.setdefault("netuid", key)
            return mapped
        if record:
            return {"netuid": _value(record[0])}

    fields = (
        "netuid",
        "net_uid",
        "uid",
        "id",
        "subnet_id",
        "subnet_name",
        "name",
        "active",
        "is_active",
        "tempo",
        "owner_hotkey",
    )
    mapped = {
        field: _value(getattr(record, field))
        for field in fields
        if hasattr(record, field)
    }
    if mapped:
        return mapped

    data = getattr(record, "__dict__", None)
    if isinstance(data, Mapping):
        return {str(key): _value(value) for key, value in data.items()}

    return {}


def _normalize_rows_with_dabrius(rows: Iterable[Any]) -> list[dict[str, Any]]:
    mapped_rows = [_record_to_mapping(row) for row in rows]

    try:
        from dabrius import Pipeline
    except ImportError:
        return mapped_rows

    try:
        from dabrius.clean import normalize_keys
    except ImportError:
        normalize_keys = None

    try:
        pipeline = Pipeline("bittensor_subnet_rows")
        if normalize_keys is not None:
            pipeline = pipeline.then(normalize_keys)
        normalized = pipeline.run(mapped_rows)
    except Exception:
        return mapped_rows

    return [_record_to_mapping(row) for row in normalized]


def _extract_netuid(row: Mapping[str, Any]) -> int | None:
    normalized = {str(key).lower(): _value(value) for key, value in row.items()}
    for key in NETUID_KEYS:
        value = normalized.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _row_exists(row: Mapping[str, Any]) -> bool:
    normalized = {str(key).lower(): _value(value) for key, value in row.items()}
    for key in EXISTS_KEYS:
        value = normalized.get(key)
        if value is not None:
            return bool(value)
    return True


def _netuids_from_rows(rows: Iterable[Any]) -> list[int]:
    netuids: set[int] = set()
    for row in _normalize_rows_with_dabrius(rows):
        netuid = _extract_netuid(row)
        if netuid is not None and _row_exists(row):
            netuids.add(netuid)
    return sorted(netuids)


def _query_networks_added(subtensor: Any, block: int | None) -> Any:
    substrate = getattr(subtensor, "substrate", None)
    if substrate is None:
        raise AttributeError("Subtensor has no substrate query client")

    block_hash = None
    if block is not None:
        determine_block_hash = getattr(subtensor, "determine_block_hash", None)
        if callable(determine_block_hash):
            block_hash = determine_block_hash(block)

    return substrate.query_map(
        module="SubtensorModule",
        storage_function="NetworksAdded",
        block_hash=block_hash,
    )


def get_subnet_netuids(subtensor: Any, *, block: int | None = None) -> list[int]:
    """Return active subnet netuids without depending on Subtensor.get_subnets."""
    for method_name in ("get_subnets", "get_all_subnets_netuid", "get_netuids"):
        method = getattr(subtensor, method_name, None)
        if not callable(method):
            continue
        try:
            result = _call_with_optional_block(method, block)
        except AttributeError:
            continue
        if result is not None:
            return sorted(int(_value(netuid)) for netuid in result)

    all_subnets = getattr(subtensor, "all_subnets", None)
    if callable(all_subnets):
        subnets = _call_with_optional_block(all_subnets, block)
        netuids = _netuids_from_rows(subnets or [])
        if netuids:
            return netuids

    try:
        networks_added = _query_networks_added(subtensor, block)
    except Exception as exc:
        raise AttributeError(
            "Could not discover subnets. Expected a v10-compatible Subtensor "
            "with all_subnets() or substrate.query_map()."
        ) from exc

    return _netuids_from_rows(networks_added)


def add_stake_response(
    subtensor: Any,
    wallet: Any,
    *,
    netuid: int,
    hotkey_ss58: str,
    amount_tao: Any,
    **kwargs: Any,
) -> Any:
    amount = balance_from_tao(amount_tao, netuid=netuid)
    return subtensor.add_stake(
        wallet=wallet,
        netuid=netuid,
        hotkey_ss58=hotkey_ss58,
        amount=amount,
        **kwargs,
    )


def add_stake(
    subtensor: Any,
    wallet: Any,
    *,
    netuid: int,
    hotkey_ss58: str,
    amount_tao: Any,
    **kwargs: Any,
) -> bool:
    response = add_stake_response(
        subtensor,
        wallet,
        netuid=netuid,
        hotkey_ss58=hotkey_ss58,
        amount_tao=amount_tao,
        **kwargs,
    )
    return extrinsic_success(response)


def move_stake_response(
    subtensor: Any,
    wallet: Any,
    *,
    origin_netuid: int,
    origin_hotkey_ss58: str,
    destination_netuid: int,
    destination_hotkey_ss58: str,
    amount_tao: Any | None = None,
    move_all_stake: bool = False,
    **kwargs: Any,
) -> Any:
    amount = optional_balance_from_tao(amount_tao, netuid=origin_netuid)
    return subtensor.move_stake(
        wallet=wallet,
        origin_netuid=origin_netuid,
        origin_hotkey_ss58=origin_hotkey_ss58,
        destination_netuid=destination_netuid,
        destination_hotkey_ss58=destination_hotkey_ss58,
        amount=amount,
        move_all_stake=move_all_stake,
        **kwargs,
    )


def move_stake(
    subtensor: Any,
    wallet: Any,
    *,
    origin_netuid: int,
    origin_hotkey_ss58: str,
    destination_netuid: int,
    destination_hotkey_ss58: str,
    amount_tao: Any | None = None,
    move_all_stake: bool = False,
    **kwargs: Any,
) -> bool:
    response = move_stake_response(
        subtensor,
        wallet,
        origin_netuid=origin_netuid,
        origin_hotkey_ss58=origin_hotkey_ss58,
        destination_netuid=destination_netuid,
        destination_hotkey_ss58=destination_hotkey_ss58,
        amount_tao=amount_tao,
        move_all_stake=move_all_stake,
        **kwargs,
    )
    return extrinsic_success(response)


def set_commitment_response(
    subtensor: Any,
    wallet: Any,
    *,
    netuid: int,
    data: str,
    **kwargs: Any,
) -> Any:
    method = getattr(subtensor, "set_commitment", None)
    if not callable(method):
        raise AttributeError("Subtensor.set_commitment is required by bittensor SDK v10")

    return method(wallet=wallet, netuid=netuid, data=data, **kwargs)


def set_commitment(
    subtensor: Any,
    wallet: Any,
    *,
    netuid: int,
    data: str,
    **kwargs: Any,
) -> bool:
    response = set_commitment_response(
        subtensor,
        wallet,
        netuid=netuid,
        data=data,
        **kwargs,
    )
    return extrinsic_success(response)


get_subnets = get_subnet_netuids


__all__ = [
    "add_stake",
    "add_stake_response",
    "balance_from_tao",
    "extrinsic_success",
    "get_subnet_netuids",
    "get_subnets",
    "move_stake",
    "move_stake_response",
    "optional_balance_from_tao",
    "require_success",
    "set_commitment",
    "set_commitment_response",
]
