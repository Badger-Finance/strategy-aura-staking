import brownie
from brownie import *
from helpers.constants import MaxUint256
from helpers.SnapshotManager import SnapshotManager
from helpers.time import days

def test_claimRewardsOnWithdrawAll(deployer, vault, strategy, want, governance):
    startingBalance = want.balanceOf(deployer)

    aura = interface.IERC20Detailed(strategy.AURA())

    depositAmount = startingBalance // 2
    assert startingBalance >= depositAmount
    assert startingBalance >= 0
    # End Setup

    # Deposit
    assert want.balanceOf(vault) == 0

    want.approve(vault, MaxUint256, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    vault.earn({"from": governance})

    chain.sleep(10000 * 13)  # Mine so we get some interest

    chain.snapshot()

    vault.withdrawToVault({"from": governance})
    assert aura.balanceOf(strategy) > 0

    chain.revert()

    # Random can't call
    with brownie.reverts("onlyGovernanceOrStrategist"):
        strategy.setClaimRewardsOnWithdrawAll(False, {"from": accounts[5]})

    strategy.setClaimRewardsOnWithdrawAll(False)

    vault.withdrawToVault({"from": governance})
    assert aura.balanceOf(strategy) == 0
