import brownie
from brownie import *
from helpers.constants import MaxUint256
from helpers.SnapshotManager import SnapshotManager

MAX_BPS = 10_000


def test_is_profitable(vault, strategy, want, randomUser, deployer):
    initial_balance = want.balanceOf(deployer)

    settKeeper = accounts.at(vault.keeper(), force=True)

    snap = SnapshotManager(vault, strategy, "StrategySnapshot")

    # Deposit
    assert want.balanceOf(deployer) > 0

    depositAmount = int(want.balanceOf(deployer) * 0.8)
    assert depositAmount > 0

    want.approve(vault.address, MaxUint256, {"from": deployer})

    snap.settDeposit(depositAmount, {"from": deployer})

    # Earn
    with brownie.reverts("onlyAuthorizedActors"):
        vault.earn({"from": randomUser})

    snap.settEarn({"from": settKeeper})

    chain.sleep(15)
    chain.mine(1)

    strategy.harvest({"from": settKeeper})

    snap.settWithdrawAll({"from": deployer})

    ending_balance = want.balanceOf(deployer)

    initial_balance_with_fees = initial_balance * (
        1 - (vault.withdrawalFee() / MAX_BPS)
    )

    print("Initial Balance")
    print(initial_balance)
    print("initial_balance_with_fees")
    print(initial_balance_with_fees)
    print("Ending Balance")
    print(ending_balance)

    assert ending_balance > initial_balance_with_fees
