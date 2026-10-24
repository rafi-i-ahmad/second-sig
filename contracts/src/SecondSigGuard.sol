// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {BaseGuard} from "safe-contracts/base/GuardManager.sol";
import {Enum} from "safe-contracts/common/Enum.sol";

interface ISafe {
    function nonce() external view returns (uint256);
    function isOwner(address owner) external view returns (bool);
    function getOwners() external view returns (address[] memory);
    function getTransactionHash(
        address to,
        uint256 value,
        bytes calldata data,
        Enum.Operation operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address refundReceiver,
        uint256 _nonce
    ) external view returns (bytes32);
}

/// @title SecondSigGuard
/// @notice Safe transaction guard: nothing executes without a judge stamp for its exact safeTxHash,
///         or an override approved by every owner and aged past OVERRIDE_DELAY blocks.
/// @dev Stamp (EIP-712): { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }
///      Domain: { name: "SecondSig", version: "1", chainId, verifyingContract: this }
///      The Safe increments its nonce before checkTransaction, so the hash is recomputed with nonce() - 1.
contract SecondSigGuard is BaseGuard {
    struct Stamp {
        bytes32 safeTxHash;
        uint64 forkBlock;
        bytes32 judgeVersion;
    }

    bytes32 public constant STAMP_TYPEHASH =
        keccak256("Stamp(bytes32 safeTxHash,uint64 forkBlock,bytes32 judgeVersion)");
    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    uint256 public constant MAX_STAMP_AGE = 100;
    // secp256k1n / 2: signatures with a higher s are malleable copies
    uint256 private constant HALF_N = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    ISafe public immutable SAFE;
    address public immutable JUDGE;
    bytes32 public immutable JUDGE_VERSION;
    uint256 public immutable OVERRIDE_DELAY;

    /// safeTxHash => forkBlock of the attested stamp (0 = none)
    mapping(bytes32 => uint64) public stamps;
    /// safeTxHash => owner => approved
    mapping(bytes32 => mapping(address => bool)) public overrideApproved;
    /// safeTxHash => block from which the override may execute (0 = not every owner has approved)
    mapping(bytes32 => uint256) public overrideReadyAt;

    event Attested(bytes32 indexed safeTxHash, uint64 forkBlock, bytes32 judgeVersion, address indexed submitter);
    event OverrideApproved(bytes32 indexed safeTxHash, address indexed owner);
    event OverrideReady(bytes32 indexed safeTxHash, uint256 readyAt);
    event OverrideExecuted(bytes32 indexed safeTxHash);

    error SecondSig__ZeroAddress();
    error SecondSig__ZeroOverrideDelay();
    error SecondSig__NotSafe(address caller);
    error SecondSig__NotOwner(address caller);
    error SecondSig__BadSignature();
    error SecondSig__WrongSigner(address signer);
    error SecondSig__WrongJudgeVersion(bytes32 judgeVersion);
    error SecondSig__StaleStamp(bytes32 safeTxHash, uint64 forkBlock);
    error SecondSig__NoStamp(bytes32 safeTxHash);
    error SecondSig__OverrideNotReady(bytes32 safeTxHash, uint256 readyAt);

    constructor(address safe, address judge, bytes32 judgeVersion, uint256 overrideDelay) {
        if (safe == address(0) || judge == address(0)) revert SecondSig__ZeroAddress();
        if (overrideDelay == 0) revert SecondSig__ZeroOverrideDelay();
        SAFE = ISafe(safe);
        JUDGE = judge;
        JUDGE_VERSION = judgeVersion;
        OVERRIDE_DELAY = overrideDelay;
    }

    // ---------------------------------------------------------------- stamps

    function domainSeparator() public view returns (bytes32) {
        return
            keccak256(abi.encode(DOMAIN_TYPEHASH, keccak256("SecondSig"), keccak256("1"), block.chainid, address(this)));
    }

    function stampDigest(Stamp calldata s) public view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(STAMP_TYPEHASH, s.safeTxHash, s.forkBlock, s.judgeVersion));
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
    }

    /// @notice Record a judge stamp. Callable by anyone; only the judge's signature counts.
    function attest(Stamp calldata s, bytes calldata sig) external {
        if (s.judgeVersion != JUDGE_VERSION) revert SecondSig__WrongJudgeVersion(s.judgeVersion);
        if (_isStale(s.forkBlock)) revert SecondSig__StaleStamp(s.safeTxHash, s.forkBlock);
        address signer = _recover(stampDigest(s), sig);
        if (signer != JUDGE) revert SecondSig__WrongSigner(signer);
        stamps[s.safeTxHash] = s.forkBlock;
        emit Attested(s.safeTxHash, s.forkBlock, s.judgeVersion, msg.sender);
    }

    // ---------------------------------------------------------------- override

    /// @notice Each current owner approves directly. Once every owner has, the override
    ///         may execute after OVERRIDE_DELAY blocks. Exists so a dead judge can't brick the Safe.
    function approveOverride(bytes32 safeTxHash) external {
        if (!SAFE.isOwner(msg.sender)) revert SecondSig__NotOwner(msg.sender);
        if (!overrideApproved[safeTxHash][msg.sender]) {
            overrideApproved[safeTxHash][msg.sender] = true;
            emit OverrideApproved(safeTxHash, msg.sender);
        }
        if (overrideReadyAt[safeTxHash] != 0) return;
        address[] memory owners = SAFE.getOwners();
        for (uint256 i; i < owners.length; ++i) {
            if (!overrideApproved[safeTxHash][owners[i]]) return;
        }
        uint256 readyAt = block.number + OVERRIDE_DELAY;
        overrideReadyAt[safeTxHash] = readyAt;
        emit OverrideReady(safeTxHash, readyAt);
    }

    // ---------------------------------------------------------------- guard

    function checkTransaction(
        address to,
        uint256 value,
        bytes memory data,
        Enum.Operation operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address payable refundReceiver,
        bytes memory, /* signatures */
        address /* msgSender */
    ) external override {
        if (msg.sender != address(SAFE)) revert SecondSig__NotSafe(msg.sender);
        bytes32 h = SAFE.getTransactionHash(
            to, value, data, operation, safeTxGas, baseGas, gasPrice, gasToken, refundReceiver, SAFE.nonce() - 1
        );

        uint256 readyAt = overrideReadyAt[h];
        if (readyAt != 0) {
            if (block.number < readyAt) revert SecondSig__OverrideNotReady(h, readyAt);
            emit OverrideExecuted(h);
            return;
        }

        uint64 forkBlock = stamps[h];
        if (forkBlock == 0) revert SecondSig__NoStamp(h);
        if (_isStale(forkBlock)) revert SecondSig__StaleStamp(h, forkBlock);
    }

    function checkAfterExecution(bytes32, bool) external view override {}

    // ---------------------------------------------------------------- internal

    function _isStale(uint64 forkBlock) private view returns (bool) {
        return forkBlock == 0 || forkBlock > block.number || block.number - forkBlock > MAX_STAMP_AGE;
    }

    function _recover(bytes32 digest, bytes calldata sig) private pure returns (address signer) {
        if (sig.length != 65) revert SecondSig__BadSignature();
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        if (uint256(s) > HALF_N || (v != 27 && v != 28)) revert SecondSig__BadSignature();
        signer = ecrecover(digest, v, r, s);
        if (signer == address(0)) revert SecondSig__BadSignature();
    }
}
