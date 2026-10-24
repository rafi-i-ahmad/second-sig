// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Enum} from "safe-contracts/common/Enum.sol";
import {SecondSigGuard} from "../src/SecondSigGuard.sol";
import {SecondSigTest} from "./Base.t.sol";

contract StampTest is SecondSigTest {
    address internal constant BOB = address(0xB0B);

    function test_stampForAPassesA() public {
        _attest(BOB, 1 ether, "", Enum.Operation.Call);
        assertTrue(_exec(BOB, 1 ether, "", Enum.Operation.Call));
        assertEq(BOB.balance, 1 ether);
    }

    function test_stampForADoesNotPassB() public {
        _attest(BOB, 1 ether, "", Enum.Operation.Call);
        bytes32 hB = _hash(BOB, 2 ether, "", Enum.Operation.Call);
        _execReverts(BOB, 2 ether, "", Enum.Operation.Call, _noStamp(hB));
    }

    function test_stampCannotBeReplayedAtLaterNonce() public {
        _attest(BOB, 1 ether, "", Enum.Operation.Call);
        _exec(BOB, 1 ether, "", Enum.Operation.Call);
        // identical parameters, next nonce: a different safeTxHash
        bytes32 next = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        _execReverts(BOB, 1 ether, "", Enum.Operation.Call, _noStamp(next));
    }

    function test_wrongSignerReverts() public {
        (address mallory, uint256 malloryKey) = makeAddrAndKey("mallory");
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        bytes memory sig = _signStamp(guard, s, malloryKey);
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__WrongSigner.selector, mallory));
        guard.attest(s, sig);
    }

    function test_ownerCannotSignStamp() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        bytes memory sig = _signStamp(guard, s, ownerKeys[0]);
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__WrongSigner.selector, owners[0]));
        guard.attest(s, sig);
    }

    function test_wrongJudgeVersionReverts() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        s.judgeVersion = keccak256("second-sig/old");
        bytes memory sig = _signStamp(guard, s, judgeKey);
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__WrongJudgeVersion.selector, s.judgeVersion));
        guard.attest(s, sig);
    }

    function test_staleForkBlockRevertsAtAttest() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        s.forkBlock = uint64(block.number - guard.MAX_STAMP_AGE() - 1);
        bytes memory sig = _signStamp(guard, s, judgeKey);
        vm.expectRevert(
            abi.encodeWithSelector(SecondSigGuard.SecondSig__StaleStamp.selector, s.safeTxHash, s.forkBlock)
        );
        guard.attest(s, sig);
    }

    function test_oldestAllowedForkBlockAttests() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        s.forkBlock = uint64(block.number - guard.MAX_STAMP_AGE());
        guard.attest(s, _signStamp(guard, s, judgeKey));
        assertTrue(_exec(BOB, 1 ether, "", Enum.Operation.Call));
    }

    function test_futureForkBlockReverts() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        s.forkBlock = uint64(block.number + 1);
        bytes memory sig = _signStamp(guard, s, judgeKey);
        vm.expectRevert(
            abi.encodeWithSelector(SecondSigGuard.SecondSig__StaleStamp.selector, s.safeTxHash, s.forkBlock)
        );
        guard.attest(s, sig);
    }

    function test_stampExpiresBeforeExecution() public {
        bytes32 h = _attest(BOB, 1 ether, "", Enum.Operation.Call);
        uint64 forkBlock = guard.stamps(h);
        vm.roll(block.number + guard.MAX_STAMP_AGE() + 1);
        _execReverts(
            BOB,
            1 ether,
            "",
            Enum.Operation.Call,
            abi.encodeWithSelector(SecondSigGuard.SecondSig__StaleStamp.selector, h, forkBlock)
        );
    }

    function test_stampForAnotherGuardDoesNotVerify() public {
        // same judge, same Safe, but the domain names a different guard contract
        SecondSigGuard other = new SecondSigGuard(address(safe), judge, JUDGE_VERSION, OVERRIDE_DELAY);
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        bytes memory sig = _signStamp(other, s, judgeKey);
        vm.expectPartialRevert(SecondSigGuard.SecondSig__WrongSigner.selector);
        guard.attest(s, sig);
    }

    function test_stampForAnotherChainDoesNotVerify() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        bytes memory sig = _signStamp(guard, s, judgeKey);
        vm.chainId(block.chainid + 1);
        vm.expectPartialRevert(SecondSigGuard.SecondSig__WrongSigner.selector);
        guard.attest(s, sig);
    }

    function test_malleableSignatureRejected() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        (uint8 v, bytes32 r, bytes32 sv) = vm.sign(judgeKey, guard.stampDigest(s));
        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes memory flipped = abi.encodePacked(r, bytes32(n - uint256(sv)), v == 27 ? uint8(28) : uint8(27));
        vm.expectRevert(SecondSigGuard.SecondSig__BadSignature.selector);
        guard.attest(s, flipped);
    }

    function test_shortSignatureRejected() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        vm.expectRevert(SecondSigGuard.SecondSig__BadSignature.selector);
        guard.attest(s, new bytes(64));
    }

    function test_anyoneCanSubmitAndEventIsEmitted() public {
        SecondSigGuard.Stamp memory s = _stamp(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        bytes memory sig = _signStamp(guard, s, judgeKey);
        address relayer = makeAddr("relayer");
        vm.expectEmit(address(guard));
        emit SecondSigGuard.Attested(s.safeTxHash, s.forkBlock, s.judgeVersion, relayer);
        vm.prank(relayer);
        guard.attest(s, sig);
        assertEq(guard.stamps(s.safeTxHash), s.forkBlock);
    }

    /// Pins the EIP-712 encoding so judge/stamp.py can be checked against the same digest.
    function test_digestMatchesManualEip712() public view {
        SecondSigGuard.Stamp memory s = _stamp(keccak256("tx"));
        bytes32 domain = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("SecondSig"),
                keccak256("1"),
                block.chainid,
                address(guard)
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("Stamp(bytes32 safeTxHash,uint64 forkBlock,bytes32 judgeVersion)"),
                s.safeTxHash,
                s.forkBlock,
                s.judgeVersion
            )
        );
        assertEq(guard.stampDigest(s), keccak256(abi.encodePacked("\x19\x01", domain, structHash)));
    }
}
