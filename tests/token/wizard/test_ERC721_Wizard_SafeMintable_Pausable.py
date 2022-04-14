import pytest
from starkware.starknet.testing.starknet import Starknet
from utils import (
    Signer, str_to_felt, ZERO_ADDRESS, INVALID_UINT256, assert_revert,
    assert_event_emitted, get_contract_def, cached_contract, to_uint, sub_uint, TRUE, FALSE
)


signer = Signer(123456789987654321)

URI = str_to_felt("http://my.uri")

# random token IDs
TOKENS = [to_uint(5042), to_uint(793)]
TOKEN_TO_MINT = to_uint(33)
# random data (mimicking bytes in Solidity)
DATA = [0x42, 0x89, 0x55]



@pytest.fixture(scope='module')
def contract_defs():
    account_def = get_contract_def('openzeppelin/account/Account.cairo')
    erc721_def = get_contract_def('tests/mocks/wizard/ERC721_Wizard_SafeMintable_Pausable.cairo')
    erc721_holder_def = get_contract_def(
        'openzeppelin/token/erc721/utils/ERC721_Holder.cairo')
    unsupported_def = get_contract_def(
        'openzeppelin/security/initializable.cairo')

    return account_def, erc721_def, erc721_holder_def, unsupported_def


@pytest.fixture(scope='module')
async def erc721_init(contract_defs):
    account_def, erc721_def, erc721_holder_def, unsupported_def = contract_defs
    starknet = await Starknet.empty()
    account1 = await starknet.deploy(
        contract_def=account_def,
        constructor_calldata=[signer.public_key]
    )
    account2 = await starknet.deploy(
        contract_def=account_def,
        constructor_calldata=[signer.public_key]
    )
    erc721 = await starknet.deploy(
        contract_def=erc721_def,
        constructor_calldata=[
            account1.contract_address
        ]
    )
    erc721_holder = await starknet.deploy(
        contract_def=erc721_holder_def,
        constructor_calldata=[]
    )
    unsupported = await starknet.deploy(
        contract_def=unsupported_def,
        constructor_calldata=[]
    )
    return (
        starknet.state,
        account1,
        account2,
        erc721,
        erc721_holder,
        unsupported
    )


@pytest.fixture
def erc721_factory(contract_defs, erc721_init):
    account_def, erc721_def, erc721_holder_def, unsupported_def = contract_defs
    state, account1, account2, erc721, erc721_holder, unsupported = erc721_init
    _state = state.copy()
    account1 = cached_contract(_state, account_def, account1)
    account2 = cached_contract(_state, account_def, account2)
    erc721 = cached_contract(_state, erc721_def, erc721)
    erc721_holder = cached_contract(_state, erc721_holder_def, erc721_holder)
    unsupported = cached_contract(_state, unsupported_def, unsupported)

    return erc721, account1, account2, erc721_holder, unsupported



#
# pause
#

# Note that depending on what's being tested, test cases alternate between
# accepting `erc721_minted`, `erc721_factory`, and `erc721_unsupported` fixtures
@pytest.fixture
async def erc721_minted(erc721_factory):
    erc721, account, account2, erc721_holder, _ = erc721_factory
    # mint tokens to account
    for token in TOKENS:
        await signer.send_transaction(
            account, erc721.contract_address, 'safeMint', [
                account.contract_address,
                *token,
                len(DATA),
                *DATA,
                URI
            ]
        )

    return erc721, account, account2, erc721_holder

@pytest.mark.asyncio
async def test_pause(erc721_minted):
    erc721, owner, other, erc721_holder = erc721_minted

    # pause
    await signer.send_transaction(owner, erc721.contract_address, 'pause', [])

    execution_info = await erc721.paused().invoke()
    assert execution_info.result.paused == TRUE

    await assert_revert(signer.send_transaction(
        owner, erc721.contract_address, 'approve', [
            other.contract_address,
            *TOKENS[0]
        ]),
        reverted_with="Pausable: contract is paused"
    )

    await assert_revert(signer.send_transaction(
        owner, erc721.contract_address, 'setApprovalForAll', [
            other.contract_address,
            TRUE
        ]),
        reverted_with="Pausable: contract is paused"
    )

    await assert_revert(signer.send_transaction(
        owner, erc721.contract_address, 'transferFrom', [
            owner.contract_address,
            other.contract_address,
            *TOKENS[0]
        ]),
        reverted_with="Pausable: contract is paused"
    )

    await assert_revert(signer.send_transaction(
        owner, erc721.contract_address, 'safeTransferFrom', [
            owner.contract_address,
            erc721_holder.contract_address,
            *TOKENS[1],
            len(DATA),
            *DATA
        ]),
        reverted_with="Pausable: contract is paused"
    )

    await assert_revert(signer.send_transaction(
        owner, erc721.contract_address, 'safeMint', [
            other.contract_address,
            *TOKEN_TO_MINT,
            len(DATA),
            *DATA,
            URI
        ]),
        reverted_with="Pausable: contract is paused"
    )


@pytest.mark.asyncio
async def test_unpause(erc721_minted):
    erc721, owner, other, erc721_holder = erc721_minted

    # pause
    await signer.send_transaction(owner, erc721.contract_address, 'pause', [])

    # unpause
    await signer.send_transaction(owner, erc721.contract_address, 'unpause', [])

    execution_info = await erc721.paused().invoke()
    assert execution_info.result.paused == FALSE

    await signer.send_transaction(
        owner, erc721.contract_address, 'approve', [
            other.contract_address,
            *TOKENS[0]
        ]
    )

    await signer.send_transaction(
        owner, erc721.contract_address, 'setApprovalForAll', [
            other.contract_address,
            TRUE
        ]
    )

    await signer.send_transaction(
        owner, erc721.contract_address, 'transferFrom', [
            owner.contract_address,
            other.contract_address,
            *TOKENS[0]
        ]
    )

    await signer.send_transaction(
        other, erc721.contract_address, 'safeTransferFrom', [
            owner.contract_address,
            erc721_holder.contract_address,
            *TOKENS[1],
            len(DATA),
            *DATA
        ]
    )

    await signer.send_transaction(
        owner, erc721.contract_address, 'safeMint', [
            other.contract_address,
            *TOKEN_TO_MINT,
            len(DATA),
            *DATA,
            URI
        ]
    )


@pytest.mark.asyncio
async def test_only_owner(erc721_minted):
    erc721, owner, other, _ = erc721_minted

    # not-owner pause should revert
    await assert_revert(
        signer.send_transaction(
            other, erc721.contract_address, 'pause', []),
        reverted_with="Ownable: caller is not the owner"
    )

    # owner pause
    await signer.send_transaction(owner, erc721.contract_address, 'pause', [])

    # not-owner unpause should revert
    await assert_revert(
        signer.send_transaction(
            other, erc721.contract_address, 'unpause', []),
        reverted_with="Ownable: caller is not the owner"
    )

    # owner unpause
    await signer.send_transaction(owner, erc721.contract_address, 'unpause', [])
