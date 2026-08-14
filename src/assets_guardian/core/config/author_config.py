from dataclasses import dataclass
from typing import Any

from assets_guardian.core.config.loader import get_config_value
from assets_guardian.core.domain.models.validator import validate_field


@dataclass
class AuthorConfig:
    """Identity of the person running Assets Guardian.

    Attributes:
        fullname: Full name of the author.
        email: Email address of the author.
    """

    fullname: str
    email: str

    def __post_init__(self) -> None:
        validate_field(self, "fullname", str)
        validate_field(self, "email", str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorConfig":
        return cls(
            fullname=get_config_value("fullname", data, env_name="AUTHOR_FULLNAME"),
            email=get_config_value("email", data, env_name="AUTHOR_EMAIL"),
        )
