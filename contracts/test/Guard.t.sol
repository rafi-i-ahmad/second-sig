// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Enum} from "safe-contracts/common/Enum.sol";
import {Guard} from "safe-contracts/base/GuardManager.sol";
import {IERC165} from "safe-contracts/interfaces/IERC165.sol";
import {SecondSigGuard} from "../src/SecondSigGuard.sol";
import {SecondSigTest} from "./Base.t.sol";

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IAavePool {
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
}

interface IMultiSend {
    function multiSend(bytes memory transactions) external payable;
}

contract GuardTest is SecondSigTest {
    // The Bybit attackers' contract and the address its transfer(...) writes into the Safe's slot 0
    address internal constant BYBIT_TARGET = 0x96221423681A6d52E184D440a8eFCEbB105C7242;
    address internal constant BYBIT_IMPL = 0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516;

    function test_supportsGuardInterface() public view {
        assertTrue(guard.supportsInterface(type(Guard).interfaceId));
        assertTrue(guard.supportsInterface(type(IERC165).interfaceId));
        assertFalse(guard.supportsInterface(0xdeadbeef));
    }

    function test_noStampRevertsWithTwoValidSignatures() public {
        address bob = makeAddr("bob");
        bytes32 h = _hash(bob, 1 ether, "", Enum.Operation.Call);
        _execReverts(bob, 1 ether, "", Enum.Operation.Call, _noStamp(h));
        assertEq(bob.balance, 0);
    }

    function test_onlySafeCanCallCheckTransaction() public {
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__NotSafe.selector, address(this)));
        guard.checkTransaction(
            address(0), 0, "", Enum.Operation.Call, 0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    /// Scenario 1: the Bybit shape. Two valid owner signatures, no stamp, and the guard reverts
    /// before the delegatecall runs, so the Safe's singleton is untouched.
    function test_bybitShapeRevertsAtGuard() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", BYBIT_IMPL, 0);
        bytes32 slot0Before = vm.load(address(safe), bytes32(0));
        bytes32 h = _hash(BYBIT_TARGET, 0, data, Enum.Operation.DelegateCall);
        _execReverts(BYBIT_TARGET, 0, data, Enum.Operation.DelegateCall, _noStamp(h));
        assertEq(vm.load(address(safe), bytes32(0)), slot0Before);
    }

    function test_stampedTransferExecutes() public {
        address bob = makeAddr("bob");
        _attest(bob, 5 ether, "", Enum.Operation.Call);
        assertTrue(_exec(bob, 5 ether, "", Enum.Operation.Call));
        assertEq(bob.balance, 5 ether);
    }

    function testFuzz_unstampedTransactionsRevert(address to, uint96 value, bytes calldata data, bool delegate) public {
        Enum.Operation op = delegate ? Enum.Operation.DelegateCall : Enum.Operation.Call;
        bytes32 h = _hash(to, value, data, op);
        _execReverts(to, value, data, op, _noStamp(h));
    }
}

/// Runs against a mainnet fork at the Bybit block, with the real Safe singleton, factory,
/// MultiSendCallOnly, USDC and Aave v3. Skipped when MAINNET_RPC is not set.
contract GuardForkTest is SecondSigTest {
    uint256 internal constant FORK_BLOCK = 21_895_238;
    address internal constant SINGLETON_141 = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    address internal constant FACTORY_141 = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    address internal constant MULTISEND_CALL_ONLY = 0x9641d764fc13c8B624c04430C7356C1C7C8102e2;
    address internal constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address internal constant AAVE_POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;
    address internal constant A_USDC = 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c;
    address internal constant BYBIT_TARGET = 0x96221423681A6d52E184D440a8eFCEbB105C7242;
    address internal constant BYBIT_IMPL = 0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516;
    uint256 internal constant AMOUNT = 10_000e6;

    function setUp() public override {
        string memory rpc = vm.envOr("MAINNET_RPC", string(""));
        if (bytes(rpc).length == 0) vm.skip(true);
        vm.createSelectFork(rpc, FORK_BLOCK);
        _deploy(SINGLETON_141, FACTORY_141);
        deal(USDC, address(safe), 50_000e6);
    }

    function _aaveBatch() internal view returns (bytes memory) {
        bytes memory approveCall = abi.encodeCall(IERC20.approve, (AAVE_POOL, AMOUNT));
        bytes memory supplyCall = abi.encodeCall(IAavePool.supply, (USDC, AMOUNT, address(safe), 0));
        bytes memory txs = abi.encodePacked(
            uint8(0),
            USDC,
            uint256(0),
            approveCall.length,
            approveCall,
            uint8(0),
            AAVE_POOL,
            uint256(0),
            supplyCall.length,
            supplyCall
        );
        return abi.encodeCall(IMultiSend.multiSend, (txs));
    }

    /// Scenario 2: the Aave deposit, stamped, executes and the Safe holds aUSDC.
    function test_aaveBatchWithStampExecutes() public {
        bytes memory data = _aaveBatch();
        _attest(MULTISEND_CALL_ONLY, 0, data, Enum.Operation.DelegateCall);
        assertTrue(_exec(MULTISEND_CALL_ONLY, 0, data, Enum.Operation.DelegateCall));
        assertEq(IERC20(USDC).balanceOf(address(safe)), 40_000e6);
        assertApproxEqAbs(IERC20(A_USDC).balanceOf(address(safe)), AMOUNT, 1);
    }

    function test_aaveBatchWithoutStampReverts() public {
        bytes memory data = _aaveBatch();
        bytes32 h = _hash(MULTISEND_CALL_ONLY, 0, data, Enum.Operation.DelegateCall);
        _execReverts(MULTISEND_CALL_ONLY, 0, data, Enum.Operation.DelegateCall, _noStamp(h));
    }

    /// Scenario 1 against the attackers' real contract: reverts at the guard, slot 0 untouched.
    function test_bybitShapeRevertsOnFork() public {
        assertGt(BYBIT_TARGET.code.length, 0);
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", BYBIT_IMPL, 0);
        bytes32 h = _hash(BYBIT_TARGET, 0, data, Enum.Operation.DelegateCall);
        _execReverts(BYBIT_TARGET, 0, data, Enum.Operation.DelegateCall, _noStamp(h));
        assertEq(address(uint160(uint256(vm.load(address(safe), bytes32(0))))), SINGLETON_141);
    }

    /// Control: the same transaction with the guard zeroed, as in the rehearsal, does hijack slot 0.
    /// This is what the guard is preventing.
    function test_bybitShapeHijacksWithoutGuard() public {
        vm.store(address(safe), GUARD_SLOT, bytes32(0));
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", BYBIT_IMPL, 0);
        _exec(BYBIT_TARGET, 0, data, Enum.Operation.DelegateCall);
        assertEq(address(uint160(uint256(vm.load(address(safe), bytes32(0))))), BYBIT_IMPL);
    }
}
