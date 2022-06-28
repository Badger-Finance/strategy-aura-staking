// SPDX-License-Identifier: MIT

pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {Initializable} from "@openzeppelin-contracts-upgradeable/proxy/Initializable.sol";

import {AdminUpgradeabilityProxy} from "./proxy/AdminUpgradeabilityProxy.sol";
import {IBadgerRegistry} from "../interfaces/badger/IBadgerRegistry.sol";
import {IBooster} from "../interfaces/aura/IBooster.sol";
import {IVault} from "../interfaces/badger/IVault.sol";

contract StrategyAuraStakingFactory is Initializable {
    // =====================
    // ===== Constants =====
    // =====================

    IBooster public constant BOOSTER =
        IBooster(0x7818A1DA7BD1E64c199029E86Ba244a9798eEE10);

    // TODO: Maybe make settable and not constants
    uint256 public constant PERFORMANCE_FEE_GOVERNANCE = 1000;
    uint256 public constant PERFORMANCE_FEE_STRATEGIST = 1000;
    uint256 public constant WITHDRAWAL_FEE = 100;
    uint256 public constant MANAGEMENT_FEE = 0;

    IBadgerRegistry public constant REGISTRY =
        IBadgerRegistry(0xFda7eB6f8b7a9e9fCFd348042ae675d1d652454f);

    // =======================
    // ===== Definitions =====
    // =======================

    struct Deployment {
        address vault;
        address strategy;
    }

    // =================
    // ===== State =====
    // =================

    address public strategyLogic;
    address public vaultLogic;

    mapping(address => Deployment) public deployments;

    address public governance;
    address public strategist;
    address public keeper;
    address public treasury;
    address public badgerTree;
    address public guardian;
    address public proxyAdmin;

    // ==================
    // ===== Events =====
    // ==================

    event Deployed(
        address indexed want,
        address indexed vault,
        address indexed strategy
    );

    function initialize(address _strategyLogic, address _vaultLogic)
        public
        initializer
    {
        address _governance = REGISTRY.get("governance");
        address _keeper = REGISTRY.get("keeperAccessControl");
        address _guardian = REGISTRY.get("guardian");
        address _badgerTree = REGISTRY.get("badgerTree");
        address _proxyAdminTimelock = REGISTRY.get("proxyAdminTimelock");

        require(_governance != address(0), "ZERO ADDRESS");
        require(_keeper != address(0), "ZERO ADDRESS");
        require(_guardian != address(0), "ZERO ADDRESS");
        require(_badgerTree != address(0), "ZERO ADDRESS");
        require(_proxyAdminTimelock != address(0), "ZERO ADDRESS");

        governance = _governance;
        strategist = _governance;
        keeper = _keeper;
        guardian = _guardian;
        badgerTree = _badgerTree;
        treasury = _governance;
        proxyAdmin = _proxyAdminTimelock;

        strategyLogic = _strategyLogic;
        vaultLogic = _vaultLogic;
    }

    // ====================
    // ===== External =====
    // ====================

    function deploy(uint256 _pid)
        external
        returns (address strategy_, address vault_)
    {
        (address want, , , , , ) = BOOSTER.poolInfo(_pid);

        vault_ = deployVault(want);
        strategy_ = deployStrategy(vault_, _pid);

        IVault(vault_).setStrategy(strategy_);
        IVault(vault_).setGovernance(governance);

        deployments[want] = Deployment(vault_, strategy_);

        emit Deployed(want, vault_, strategy_);
    }

    // ============================
    // ===== Internal helpers =====
    // ============================

    function deployVault(address _want) internal returns (address vault_) {
        require(deployments[_want].vault == address(0), "already deployed");

        vault_ = deployProxy(
            vaultLogic,
            proxyAdmin,
            abi.encodeWithSignature(
                "initialize(address,address,address,address,address,address,string,string,uint256[4])",
                _want,
                address(this), // governance
                keeper,
                guardian,
                treasury,
                strategist,
                badgerTree,
                ""
                "",
                [
                    PERFORMANCE_FEE_GOVERNANCE,
                    PERFORMANCE_FEE_STRATEGIST,
                    WITHDRAWAL_FEE,
                    MANAGEMENT_FEE
                ]
            )
        );
    }

    function deployStrategy(address _vault, uint256 _pid)
        internal
        returns (address strategy_)
    {
        strategy_ = deployProxy(
            strategyLogic,
            proxyAdmin,
            abi.encodeWithSignature("initialize(address,address)", _vault, _pid)
        );
    }

    function deployProxy(
        address _logic,
        address _admin,
        bytes memory _data
    ) internal returns (address proxy_) {
        proxy_ = address(new AdminUpgradeabilityProxy(_logic, _admin, _data));
    }
}

/*
TODO:
- Deterministic proxy deployments using create2 with bytecode as salt?
- setVaultLogic/setStrategyLogic by owner? Ownable?
- Only strategy/vault deployments?
- Parameter settings (fees etc.)?
*/
