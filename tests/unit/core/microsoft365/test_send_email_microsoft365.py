"""Tests for SendEmailMicrosoft365."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.microsoft365.send_email_microsoft365 import SendEmailMicrosoft365

MODULE = "assets_guardian.core.microsoft365.send_email_microsoft365"


@pytest.fixture
def sender():
    return SendEmailMicrosoft365(MagicMock(), "sender@apizee.com")


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_sets_attributes():
    graph = MagicMock()

    instance = SendEmailMicrosoft365(graph, "sender@apizee.com")

    assert instance.graph is graph
    assert instance.sender == "sender@apizee.com"


# ---------------------------------------------------------------------------
# from_context
# ---------------------------------------------------------------------------


def test_from_context_returns_none_when_no_instances_configured():
    ctx = MagicMock(spec=Context)
    ctx.app_config.integrations = {}

    result = SendEmailMicrosoft365.from_context(ctx)

    assert result is None


def test_from_context_returns_none_when_client_is_not_microsoft_graph():
    ctx = MagicMock(spec=Context)
    ctx.app_config.integrations = {"microsoft365": {"instance1": {"tenant_id": "t"}}}

    with patch(f"{MODULE}.ClientProviderRegistry") as mock_registry:
        provider = mock_registry.instantiates_clientprovider.return_value
        provider.instantiate_client.return_value = MagicMock()

        result = SendEmailMicrosoft365.from_context(ctx)

    assert result is None


def test_from_context_success_returns_sender():
    ctx = MagicMock(spec=Context)
    ctx.app_config.integrations = {"microsoft365": {"instance1": {"tenant_id": "t"}}}
    ctx.app_config.author.email = "author@example.com"
    fake_graph = MagicMock(spec=MicrosoftGraph)

    with patch(f"{MODULE}.ClientProviderRegistry") as mock_registry:
        provider = mock_registry.instantiates_clientprovider.return_value
        provider.instantiate_client.return_value = fake_graph

        result = SendEmailMicrosoft365.from_context(ctx)

    assert result is not None
    assert result.graph is fake_graph
    assert result.sender == "author@example.com"
    mock_registry.instantiates_clientprovider.assert_called_once_with(
        "microsoft365", {"tenant_id": "t"}
    )


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------


def test_send_email_success(sender):
    sender.graph._user_client.users.by_user_id.return_value.send_mail.post = AsyncMock(
        return_value=None
    )

    result = sender.send_email(
        subject="Report ready",
        text="See attached.",
        recipients={"to": ["a@b.com"], "cc": ["c@d.com"]},
    )

    assert result is True
    sender.graph._user_client.users.by_user_id.assert_called_once_with("sender@apizee.com")

    request_body = (
        sender.graph._user_client.users.by_user_id.return_value.send_mail.post.call_args.args[0]
    )
    assert request_body.message.subject == "Report ready"
    assert request_body.message.body.content == "See attached."
    assert [r.email_address.address for r in request_body.message.to_recipients] == ["a@b.com"]
    assert [r.email_address.address for r in request_body.message.cc_recipients] == ["c@d.com"]
    assert request_body.save_to_sent_items is False


def test_send_email_without_cc_recipients(sender):
    sender.graph._user_client.users.by_user_id.return_value.send_mail.post = AsyncMock(
        return_value=None
    )

    result = sender.send_email(subject="Subj", text="Body", recipients={"to": ["a@b.com"]})

    assert result is True
    request_body = (
        sender.graph._user_client.users.by_user_id.return_value.send_mail.post.call_args.args[0]
    )
    assert request_body.message.cc_recipients == []


def test_send_email_returns_false_on_exception(sender):
    sender.graph._user_client.users.by_user_id.return_value.send_mail.post = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    result = sender.send_email(subject="Subj", text="Body", recipients={"to": ["a@b.com"]})

    assert result is False
