import brownie
import time
import pytest

from brownie import interface, accounts, StrategyAuraStaking, AdminUpgradeabilityProxy, Contract, chain
from helpers.constants import AddressZero, MaxUint256
from helpers.time import days
from rich.console import Console

C = Console()

CURRENT_BOOSTER = "0x7818A1DA7BD1E64c199029E86Ba244a9798eEE10"
NEW_BOOSTER = "0xA57b8d98dAE62B26Ec3bcC4a365338157060B234"
CURRENT_PIDS = {
    "b80BADGER_20WBTC": 33,
    "b40WBTC_40DIGG_20graviAURA": 34
}
NEW_PIDS = {
    "b80BADGER_20WBTC": 18,
    "b40WBTC_40DIGG_20graviAURA": 19
}
VAULTS = {
    "b80BADGER_20WBTC": "0x63ad745506BD6a3E57F764409A47ed004BEc40b1",
    "b40WBTC_40DIGG_20graviAURA": "0x371B7C451858bd88eAf392B383Df8bd7B8955d5a"
}
STRATEGIES = {
    "b80BADGER_20WBTC": "0xe43857fE16D18b6633A663389934d6c64D5E81FD",
    "b40WBTC_40DIGG_20graviAURA": "0xD87F2cdE238D0122b3865164359CFF6b2431d927"
}

LAST_PERIOD_FINISH = 1671696167

@pytest.mark.parametrize('VAULT_ID', ["b80BADGER_20WBTC", "b40WBTC_40DIGG_20graviAURA"])
def test_aura_contracts_migration(VAULT_ID):
    C.log(f"Migration test for: {VAULT_ID}")
    vault = interface.IVault(VAULTS[VAULT_ID])
    gov = accounts.at(vault.governance(), force=True)
    strat_current = StrategyAuraStaking.at(STRATEGIES[VAULT_ID], owner=gov)
    want = interface.ERC20(vault.token())
    assert vault.strategy() == strat_current.address

    # Aura contracts
    assert strat_current.BOOSTER() == CURRENT_BOOSTER
    booster_current = interface.IBooster(CURRENT_BOOSTER)

    # Fast forward to end of rewards period for current contracts
    C.print(f"Sleeping for {(LAST_PERIOD_FINISH - chain.time())/(days(1))} days")
    chain.sleep(LAST_PERIOD_FINISH - chain.time())
    assert strat_current.pid() == CURRENT_PIDS[VAULT_ID]
    _, _, _, rewards_address, _, _ = booster_current.poolInfo(strat_current.pid())
    assert strat_current.baseRewardPool() == rewards_address
    (bal, aura) = strat_current.balanceOfRewards()
    # Check that rewards are accrued
    bal_earned = bal[1]
    C.log(f"BAL earned: {bal_earned / 1e18}")


    ### 1. Harvest
    tx = strat_current.harvest()
    for event in tx.events["Transfer"]:
        if event["from"] == rewards_address and event["to"] == strat_current.address:
            value = event["value"]
            assert value > bal_earned
            C.log(f"BAL harvested: {value / 1e18}")
    for event in tx.events["Transfer"]:
        if event["from"] == AddressZero and event["to"] == strat_current.address:
            value = event["value"]
            C.log(f"AURA harvested: {value / 1e18}") 
            break

    
    (bal, aura) = strat_current.balanceOfRewards()
    # Check that rewards are accrued
    bal_remaining = bal[1]
    assert bal_remaining == 0


    ### 2. Withdraw assets to vault
    balance_of_pool = strat_current.balanceOfPool()
    balanace_of_vault = want.balanceOf(vault.address)
    balance_total = balanace_of_vault + balance_of_pool

    vault.withdrawToVault({"from": gov})
    assert want.balanceOf(vault.address) == balance_total


    ### 3. Migrate strategy
    # Deploy new strat
    strat_new_logic = StrategyAuraStaking.deploy({"from": accounts[0]})
    strat_new = AdminUpgradeabilityProxy.deploy(
        strat_new_logic.address, 
        accounts[1], 
        strat_new_logic.initialize.encode_input(vault.address, NEW_PIDS[VAULT_ID]), 
        {"from": accounts[0]}
    )
    AdminUpgradeabilityProxy.remove(strat_new)
    strat_new = StrategyAuraStaking.at(strat_new.address, owner=gov)
    
    # Confirm parameters
    assert strat_new.BOOSTER() == NEW_BOOSTER
    booster_new = interface.IBooster(NEW_BOOSTER)
    _, _, _, rewards_address, _, _ = booster_new.poolInfo(strat_new.pid())
    assert strat_new.baseRewardPool() == rewards_address
    assert strat_new.pid() == NEW_PIDS[VAULT_ID]

    # Set new strategy
    vault.setStrategy(strat_new.address, {"from": gov})
    assert vault.strategy() == strat_new.address


    ### 4. Earn vault
    vault.earn({"from": gov})
    balance_of_pool = strat_new.balanceOfPool()
    balanace_of_vault = want.balanceOf(vault.address)
    assert balance_total == balance_of_pool + balanace_of_vault

    C.log("[green]Migration test successful![/green]\n")


    ### 5. Advance a few days in time and harvest
    chain.sleep(days(3))
    C.log("Fast-forwarding 3 days and harvesting...")

    # Earmark rewards 
    booster_new.earmarkRewards(NEW_PIDS[VAULT_ID], {"from": accounts[0]})

    tx = strat_new.harvest()
    for event in tx.events["Transfer"]:
        if event["from"] == rewards_address and event["to"] == strat_new.address:
            value = event["value"]
            C.log(f"BAL harvested: {value / 1e18}")
    for event in tx.events["Transfer"]:
        if event["from"] == AddressZero and event["to"] == strat_new.address:
            value = event["value"]
            C.log(f"AURA harvested: {value / 1e18}\n")
            break

