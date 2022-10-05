import brownie
import time

from brownie import interface, chain, accounts, StrategyAuraStaking
from helpers.constants import AddressZero, MaxUint256
from helpers.time import days
from rich.console import Console
from _setup.config import PID
from helpers.utils import (
    approx,
)

console = Console()


def test_expected_aura_rewards_match_minted(
    strategy, keeper, state_setup
):
    (bal, aura) = strategy.balanceOfRewards()
    # Check that rewards are accrued
    bal_amount = bal[1]
    aura_amount = aura[1]
    assert bal_amount > 0
    assert aura_amount > 0

    # Check that aura amount calculating function matches the result
    assert aura_amount == strategy.getMintableAuraRewards(bal_amount)

    # First Transfer event from harvest() function is emitted by aura._mint()
    tx = strategy.harvest({"from": keeper})

    for event in tx.events["Transfer"]:
        if event["from"] == AddressZero and event["to"] == strategy:
            assert approx(
                event["value"],
                aura_amount,
                1,
            )
            break


def test_claimRewardsOnWithdrawAll(
    deployer, vault, strategy, want, governance, topup_rewards
):
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

    chain.sleep(days(1))
    topup_rewards()

    chain.sleep(days(1))
    chain.mine()

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


def test_set_wrong_pid(governance, strategy):
    with brownie.reverts("token mismatch"):
        strategy.setPid(PID - 1, {"from": governance})


def test_set_pid_while_deposits(want, deployer, governance, vault, strategy):
    startingBalance = want.balanceOf(deployer)

    depositAmount = startingBalance // 2
    assert depositAmount > 0

    want.approve(vault, MaxUint256, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    vault.earn({"from": governance})

    with brownie.reverts("cannot change pid if pending deposits"):
        strategy.setPid(PID, {"from": governance})


def test_initialize_wrong_pid(vault, deployer):
    strategy = StrategyAuraStaking.deploy({"from": deployer})
    with brownie.reverts("token mismatch"):
        strategy.initialize(vault, PID - 1)


def test_sweep_pid(strategy, governance):
    with brownie.reverts("token mismatch"):
        strategy.setPid(PID - 1, {"from": governance})


def test_aura_harvest_swapping(
    strategy, keeper, make_graviaura_pool_profitable, graviaura
):
    # Harvesting should handle Aura -> graviaURA via swap
    initial_total_supply = graviaura.totalSupply()

    tx = strategy.harvest({"from": keeper})

    assert initial_total_supply == graviaura.totalSupply()


def test_aura_harvest_depositing(
    strategy, keeper, make_graviaura_pool_unprofitable, graviaura
):
    # Harvesting should handle Aura -> graviaURA via swap
    initial_total_supply = graviaura.totalSupply()

    tx = strategy.harvest({"from": keeper})

    assert initial_total_supply < graviaura.totalSupply()


    
    

