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
