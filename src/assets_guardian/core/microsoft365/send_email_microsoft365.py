import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
    SendMailPostRequestBody,
)

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry

logger = logging.getLogger(__name__)


class SendEmailMicrosoft365:
    def __init__(self, graph: MicrosoftGraph, sender: str):
        self.graph = graph
        self.sender = sender
        self.__loop = asyncio.new_event_loop()

    def __run(self, coro: Coroutine[Any, Any, bool]) -> bool:
        return self.__loop.run_until_complete(coro)

    @classmethod
    def from_context(cls, ctx: Context) -> "SendEmailMicrosoft365 | None":
        """Builds a SendEmailMicrosoft365 sending as ctx.app_config.author.email, using
        the first configured microsoft365 instance."""
        instances = ctx.app_config.integrations.get("microsoft365", {})
        if not instances:
            logger.warning("No microsoft365 instance configured, cannot send email.")
            return None

        params = next(iter(instances.values()))
        client_provider = ClientProviderRegistry.instantiates_clientprovider("microsoft365", params)
        graph = client_provider.instantiate_client()
        if not isinstance(graph, MicrosoftGraph):
            logger.warning("Expected a MicrosoftGraph client, got %s", type(graph).__name__)
            return None

        return cls(graph, ctx.app_config.author.email)

    def send_email(self, subject: str, text: str, recipients: dict[str, list[str]]) -> bool:
        """Sends an email as self.sender (equivalent to POST /users/{sender}/sendMail)."""

        async def _send() -> bool:
            to_recipients = [
                Recipient(email_address=EmailAddress(address=email))
                for email in recipients.get("to", [])
            ]
            cc_recipients = [
                Recipient(email_address=EmailAddress(address=email))
                for email in recipients.get("cc", [])
            ]
            request_body = SendMailPostRequestBody(
                message=Message(
                    subject=subject,
                    body=ItemBody(
                        content_type=BodyType.Text,
                        content=text,
                    ),
                    to_recipients=to_recipients,
                    cc_recipients=cc_recipients,
                ),
                save_to_sent_items=False,
            )
            try:
                await self.graph._user_client.users.by_user_id(self.sender).send_mail.post(
                    request_body
                )
            except Exception as e:
                logger.warning("Unable to send email: %s", e)
                return False
            return True

        return self.__run(_send())
