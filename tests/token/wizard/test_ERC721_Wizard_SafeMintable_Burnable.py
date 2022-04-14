import pytest
from starkware.starknet.testing.starknet import Starknet
from utils import (
    Signer, str_to_felt, ZERO_ADDRESS, INVALID_UINT256, assert_revert,
    assert_event_emitted, get_contract_def, cached_contract, to_uint, sub_uint
)


signer = Signer(123456789987654321)

URI = str_to_felt("http://my.uri")

NONEXISTENT_TOKEN = to_uint(999)
# random token IDs
TOKENS = [to_uint(5042), to_uint(793)]
# test token
TOKEN = TOKENS[0]
# random user address
RECIPIENT = 555
# random data (mimicking bytes in Solidity)
DATA = [0x42, 0x89, 0x55]
# random URIs
SAMPLE_URI_1 = str_to_felt('mock://mytoken.v1')
SAMPLE_URI_2 = str_to_felt('mock://mytoken.v2')

# selector ids
IERC165_ID = 0x01ffc9a7
IERC721_ID = 0x80ac58cd
IERC721_METADATA_ID = 0x5b5e139f
INVALID_ID = 0xffffffff
UNSUPPORTED_ID = 0xabcd1234


@pytest.fixture(scope='module')
def contract_defs():
    account_def = get_contract_def('openzeppelin/account/Account.cairo')
    erc721_def = get_contract_def('tests/mocks/wizard/ERC721_Wizard_SafeMintable_Burnable.cairo')
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


@pytest.mark.asyncio
async def test_safeMint_to_erc721_supported_contract(erc721_factory):
    erc721, account, _, erc721_holder, _ = erc721_factory

    await signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            erc721_holder.contract_address,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ]
    )

    # check balance
    execution_info = await erc721.balanceOf(erc721_holder.contract_address).call()
    assert execution_info.result == (to_uint(1),)

    # check owner
    execution_info = await erc721.ownerOf(TOKEN).call()
    assert execution_info.result == (erc721_holder.contract_address,)


@pytest.mark.asyncio
async def test_safeMint_emits_event(erc721_factory):
    erc721, account, _, erc721_holder, _ = erc721_factory

    tx_exec_info = await signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            erc721_holder.contract_address,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ]
    )

    assert_event_emitted(
        tx_exec_info,
        from_address=erc721.contract_address,
        name='Transfer',
        data=[
            ZERO_ADDRESS,
            erc721_holder.contract_address,
            *TOKEN
        ]
    )


@pytest.mark.asyncio
async def test_safeMint_to_account(erc721_factory):
    erc721, account, recipient, _, _ = erc721_factory

    await signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            recipient.contract_address,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ]
    )

    # check balance
    execution_info = await erc721.balanceOf(recipient.contract_address).call()
    assert execution_info.result == (to_uint(1),)

    # check owner
    execution_info = await erc721.ownerOf(TOKEN).call()
    assert execution_info.result == (recipient.contract_address,)


@pytest.mark.asyncio
async def test_safeMint_to_zero_address(erc721_factory):
    erc721, account, _, _, _ = erc721_factory

    # to zero address should be rejected
    await assert_revert(signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            ZERO_ADDRESS,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ]),
        reverted_with="ERC721: cannot mint to the zero address"
    )


@pytest.mark.asyncio
async def test_safeMint_from_zero_address(erc721_factory):
    erc721, _, _, erc721_holder, _ = erc721_factory

    # Caller address is `0` when not using an account contract
    await assert_revert(
        erc721.safeMint(
            erc721_holder.contract_address,
            TOKEN,
            DATA,
            URI
        ).invoke(),
        reverted_with="Ownable: caller is not the owner"
    )


@pytest.mark.asyncio
async def test_safeMint_from_not_owner(erc721_factory):
    erc721, _, other, erc721_holder, _ = erc721_factory

    await assert_revert(signer.send_transaction(
        other, erc721.contract_address, 'safeMint', [
            erc721_holder.contract_address,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ]),
        reverted_with="Ownable: caller is not the owner"
    )


@pytest.mark.asyncio
async def test_safeMint_to_unsupported_contract(erc721_factory):
    erc721, account, _, _, unsupported = erc721_factory

    await assert_revert(signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            unsupported.contract_address,
            *TOKEN,
            len(DATA),
            *DATA,
            URI
        ])
    )


@pytest.mark.asyncio
async def test_safeMint_invalid_uint256(erc721_factory):
    erc721, account, recipient, _, _ = erc721_factory

    await assert_revert(signer.send_transaction(
        account, erc721.contract_address, 'safeMint', [
            recipient.contract_address,
            *INVALID_UINT256,
            len(DATA),
            *DATA,
            URI
        ]),
        reverted_with="ERC721: token_id is not a valid Uint256"
    )


#
# burn
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
async def test_burn(erc721_minted):
    erc721, account, _, _ = erc721_minted

    execution_info = await erc721.balanceOf(account.contract_address).invoke()
    previous_balance = execution_info.result.balance

    # burn token
    await signer.send_transaction(
        account, erc721.contract_address, 'burn', [*TOKEN]
    )

    # account balance should subtract one
    execution_info = await erc721.balanceOf(account.contract_address).invoke()
    assert execution_info.result.balance == sub_uint(
        previous_balance, to_uint(1)
    )

    # approve should be cleared to zero, therefore,
    # 'getApproved()' call should fail
    await assert_revert(
        erc721.getApproved(TOKEN).invoke(),
        reverted_with="ERC721: approved query for nonexistent token"
    )

    # 'token_to_burn' owner should be zero; therefore,
    # 'ownerOf()' call should fail
    await assert_revert(
        erc721.ownerOf(TOKEN).invoke(),
        reverted_with="ERC721: owner query for nonexistent token"
    )


@pytest.mark.asyncio
async def test_burn_emits_event(erc721_minted):
    erc721, account, _, _ = erc721_minted

    # mint token to account
    tx_exec_info = await signer.send_transaction(
        account, erc721.contract_address, 'burn', [
            *TOKEN
        ]
    )

    assert_event_emitted(
        tx_exec_info,
        from_address=erc721.contract_address,
        name='Transfer',
        data=[
            account.contract_address,
            ZERO_ADDRESS,
            *TOKEN
        ]
    )


@pytest.mark.asyncio
async def test_burn_nonexistent_token(erc721_minted):
    erc721, account, _, _ = erc721_minted

    await assert_revert(signer.send_transaction(
        account, erc721.contract_address, 'burn', [
            *NONEXISTENT_TOKEN
        ]),
        reverted_with="ERC721: owner query for nonexistent token"
    )


@pytest.mark.asyncio
async def test_burn_unowned_token(erc721_minted):
    erc721, account, other, _ = erc721_minted

    # other should not be able to burn account's token
    await assert_revert(
        signer.send_transaction(
            other, erc721.contract_address, 'burn', [*TOKEN]
        ),
        reverted_with="ERC721: caller is not the token owner"
    )

    # account can burn their own token
    await signer.send_transaction(
        account, erc721.contract_address, 'burn', [*TOKEN]
    )


@pytest.mark.asyncio
async def test_burn_from_zero_address(erc721_minted):
    erc721, _, _, _ = erc721_minted

    await assert_revert(
        erc721.burn(TOKEN).invoke(),
        reverted_with="ERC721: caller is not the token owner"
    )
