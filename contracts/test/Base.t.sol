// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Safe} from "safe-contracts/Safe.sol";
import {SafeProxyFactory} from "safe-contracts/proxies/SafeProxyFactory.sol";
import {Enum} from "safe-contracts/common/Enum.sol";
import {SecondSigGuard} from "../src/SecondSigGuard.sol";

/// Shared setup: a 2-of-3 Safe v1.4.1 created through SafeProxyFactory, with SecondSigGuard
/// installed by a real execTransaction(setGuard). Tests run against a local chain by default;
/// fork tests call _deploy with the mainnet singleton and factory instead.
abstract contract SecondSigTest is Test {
    // keccak256("guard_manager.guard.address")
    bytes32 internal constant GUARD_SLOT = 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8;
    bytes32 internal constant JUDGE_VERSION = keccak256("second-sig/test");
    uint256 internal constant OVERRIDE_DELAY = 50;
    uint256 internal constant START_BLOCK = 1_000;

    Safe internal safe;
    SecondSigGuard internal guard;

    uint256[] internal ownerKeys; // sorted by address
    address[] internal owners;
    uint256 internal judgeKey;
    address internal judge;

    function setUp() public virtual {
        vm.roll(START_BLOCK);
        _deploy(address(new Safe()), address(new SafeProxyFactory()));
    }

    function _deploy(address singleton, address factory) internal {
        delete ownerKeys;
        delete owners;
        (address a, uint256 ka) = makeAddrAndKey("owner-a");
        (address b, uint256 kb) = makeAddrAndKey("owner-b");
        (address c, uint256 kc) = makeAddrAndKey("owner-c");
        address[3] memory addrs = [a, b, c];
        uint256[3] memory keys = [ka, kb, kc];
        // insertion sort by address: the Safe wants signatures in ascending owner order
        for (uint256 i = 1; i < 3; ++i) {
            for (uint256 j = i; j > 0 && addrs[j] < addrs[j - 1]; --j) {
                (addrs[j], addrs[j - 1]) = (addrs[j - 1], addrs[j]);
                (keys[j], keys[j - 1]) = (keys[j - 1], keys[j]);
            }
        }
        for (uint256 i; i < 3; ++i) {
            owners.push(addrs[i]);
            ownerKeys.push(keys[i]);
        }
        (judge, judgeKey) = makeAddrAndKey("judge");

        bytes memory init =
            abi.encodeCall(Safe.setup, (owners, 2, address(0), "", address(0), address(0), 0, payable(address(0))));
        safe = Safe(payable(address(SafeProxyFactory(factory).createProxyWithNonce(singleton, init, 20251023))));
        vm.deal(address(safe), 1_000 ether);

        guard = new SecondSigGuard(address(safe), judge, JUDGE_VERSION, OVERRIDE_DELAY);
        // no guard yet, so this needs only the owners' signatures
        _exec(address(safe), 0, abi.encodeCall(safe.setGuard, (address(guard))), Enum.Operation.Call);
        assertEq(address(uint160(uint256(vm.load(address(safe), GUARD_SLOT)))), address(guard));
    }

    // ---------------------------------------------------------------- Safe transactions

    function _hash(address to, uint256 value, bytes memory data, Enum.Operation op) internal view returns (bytes32) {
        return safe.getTransactionHash(to, value, data, op, 0, 0, 0, address(0), address(0), safe.nonce());
    }

    /// Owners 0 and 1 sign (threshold 2), in ascending address order.
    function _sigs(bytes32 h) internal view returns (bytes memory sigs) {
        for (uint256 i; i < 2; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKeys[i], h);
            sigs = abi.encodePacked(sigs, r, s, v);
        }
    }

    function _exec(address to, uint256 value, bytes memory data, Enum.Operation op) internal returns (bool) {
        bytes memory sigs = _sigs(_hash(to, value, data, op));
        return safe.execTransaction(to, value, data, op, 0, 0, 0, address(0), payable(address(0)), sigs);
    }

    /// Signs first, then expects the revert: expectRevert latches onto the next external call,
    /// and _exec's nonce() and getTransactionHash() reads would otherwise be that call.
    function _execReverts(address to, uint256 value, bytes memory data, Enum.Operation op, bytes memory err) internal {
        bytes memory sigs = _sigs(_hash(to, value, data, op));
        vm.expectRevert(err);
        safe.execTransaction(to, value, data, op, 0, 0, 0, address(0), payable(address(0)), sigs);
    }

    // ---------------------------------------------------------------- stamps

    function _signStamp(SecondSigGuard g, SecondSigGuard.Stamp memory s, uint256 key)
        internal
        view
        returns (bytes memory)
    {
        (uint8 v, bytes32 r, bytes32 sv) = vm.sign(key, g.stampDigest(s));
        return abi.encodePacked(r, sv, v);
    }

    function _stamp(bytes32 h) internal view returns (SecondSigGuard.Stamp memory) {
        return SecondSigGuard.Stamp({safeTxHash: h, forkBlock: uint64(block.number), judgeVersion: JUDGE_VERSION});
    }

    /// Judge stamps the next transaction with these parameters, and anyone submits it.
    function _attest(address to, uint256 value, bytes memory data, Enum.Operation op) internal returns (bytes32 h) {
        h = _hash(to, value, data, op);
        SecondSigGuard.Stamp memory s = _stamp(h);
        guard.attest(s, _signStamp(guard, s, judgeKey));
    }

    function _approveOverrideByAll(bytes32 h) internal {
        for (uint256 i; i < owners.length; ++i) {
            vm.prank(owners[i]);
            guard.approveOverride(h);
        }
    }

    function _noStamp(bytes32 h) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(SecondSigGuard.SecondSig__NoStamp.selector, h);
    }
}
