import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address, IPv6Address, ip_address
from itertools import batched
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from assets_guardian.core.config.cache_config import CacheConfig

from assets_guardian.core.config.app_config import AppEnv
from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.asset import Asset
from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.identity import Identity, IdentityState, IdentityType

logger = logging.getLogger(__name__)

# Defines model types (assets, identities, accesses)
ModelType = TypeVar("ModelType")


class LazyCacheIterable[ModelType]:
    """Iterable that reloads data from the disk at each iteration."""

    service: "CacheManager"
    file_path: Path
    item_type: type[ModelType]

    def __init__(self, service: "CacheManager", file_path: Path, item_type: type[ModelType]):
        self.service = service
        self.file_path = file_path
        self.item_type = item_type

    def __iter__(self) -> Iterator[ModelType]:
        return self.service.load(self.file_path, self.item_type)


class CacheManager:
    """Temporary cache and JSONL persistence manager.

    Allows offloading RAM by writing collected data to disk
    and managing checkpoints for crash recovery.
    """

    def __init__(self, config: "CacheConfig | None" = None):
        if config:
            self.cache_dir = Path(config.cache_dir)
            self.batch_size = config.batch_size

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_file_path(self, command: str, source: str, instance_id: str, data_type: str) -> Path:
        """Generates a unique, command-isolated file path.

        Args:
            command: Name of the command (e.g., 'sync', 'audit').
            source: Source name (e.g., 'gitlab').
            instance_id: Instance ID (e.g., 'prod').
            data_type: Data type (e.g., 'identities', 'assets', 'accesses').
        """
        # Clean special characters for the filename
        cleaned_instance = instance_id.replace(":", "_").replace("/", "_").replace(".", "_")
        filename = f"{command}_{source}_{cleaned_instance}_{data_type}.jsonl"
        return self.cache_dir / filename

    def save(self, items: Iterable[Any], file_path: Path) -> None:
        """Saves a list or an iterator of objects atomically.

        Args:
            items: The objects to persist (can be a generator).
            file_path: Target path for the JSONL file.
        """

        temp_path = file_path.with_suffix(".tmp")
        logger.debug("Temporary save to %s", temp_path)

        try:
            with temp_path.open("w", encoding="utf-8") as file:
                for item in items:
                    serialized = self.__serialize(item)
                    file.write(json.dumps(serialized) + "\n")

            # If we reach this point, the file is complete and is the file that engines will read
            temp_path.replace(file_path)
            logger.debug("Final save confirmed: %s", file_path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()
                logger.debug("temporary file %s deleted", temp_path)

    def load[ModelType](self, file_path: Path, item_type: type[ModelType]) -> Iterator[ModelType]:
        """Loads a JSONL file as an iterator of typed objects by reading in blocks.

        Reads the file in batches of N lines to optimize performance
        without saturating RAM.

        Args:
            file_path: Path of the JSONL file to read.
            item_type: The class (dataclass) to deserialize into.

        Yields:
            ModelType: The deserialized objects one by one.
        """
        if not file_path.exists():
            logger.debug("File not found: %s", file_path)
            return

        logger.debug("Loading from %s (reading in blocks of %d)", file_path, self.batch_size)
        with file_path.open(encoding="utf-8") as file:
            # batched splits the iterator into tuples of up to N elements
            for lines_batch in batched(file, self.batch_size, strict=False):
                for line in lines_batch:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        yield self.__deserialize(data, item_type)
                    except Exception:
                        logger.warning("Error reading line in %s", file_path)

    def load_iterable[ModelType](
        self, file_path: Path, item_type: type[ModelType]
    ) -> LazyCacheIterable[ModelType]:
        """Returns an iterable object that reloads from disk without loading into RAM.

        Args:
            file_path: Path of the JSONL file.
            item_type: The class to deserialize into.

        Returns:
            LazyCacheIterable: A reusable iterable tied to the file.
        """
        return LazyCacheIterable(self, file_path, item_type)

    def has_checkpoint(self, path: Path) -> bool:
        """Checks if a checkpoint file exists.

        Args:
            path: Path of the checkpoint file.
        """
        return path.exists()

    def cleanup(self, command: str, env: AppEnv) -> None:
        """Deletes all temporary files associated with a given command.

        Args:
            command: Name of the command concerned.
        """
        logger.info("Cleaning cache for command '%s'...", command)
        for file in self.cache_dir.iterdir():
            if not file.is_file():
                continue
            try:
                # Outside of production, keep the cache to reduce collection times
                if env == AppEnv.PROD:
                    file.unlink()
                    logger.debug("File deleted: %s", file)
            except Exception:
                logger.warning("Unable to delete temporary file: %s", file)

    def __serialize(self, object_to_serialize: Any) -> Any:
        """Recursive serialization of domain objects (Dataclasses, Enums, Dates, IP).

        Args:
            object_to_serialize: Object to serialize.

        Returns:
            Any: Serialized object.
        """

        if is_dataclass(object_to_serialize):
            return self.__serialize_dataclass(object_to_serialize)

        if isinstance(object_to_serialize, datetime):
            return object_to_serialize.isoformat()

        if isinstance(object_to_serialize, (IPv4Address, IPv6Address)):
            return str(object_to_serialize)

        if isinstance(object_to_serialize, Enum):
            return object_to_serialize.value

        if isinstance(object_to_serialize, list | tuple):
            return self.__serialize_iterable(object_to_serialize)

        if isinstance(object_to_serialize, dict):
            return self.__serialize_mapping(object_to_serialize)

        return object_to_serialize

    def __serialize_dataclass(self, dataclass_object: Any) -> dict[str, Any]:
        """Converts a dataclass into a dictionary, excluding None values.

        Args:
            dataclass_object: Dataclass to serialize.

        Returns:
            dict[str, Any]: Serialized object.
        """
        object_dict = asdict(dataclass_object)
        cleaned_dict = {}

        for field_name, value in object_dict.items():
            if value is not None:
                cleaned_dict[field_name] = self.__serialize(value)

        return cleaned_dict

    def __serialize_iterable(self, iterable_object: list[Any] | tuple[Any, ...]) -> list[Any]:
        """Recursively serializes a list or tuple.

        Args:
            iterable_object: Object to serialize.

        Returns:
            list[Any]: Serialized object.
        """
        serialized_list = []
        for item in iterable_object:
            serialized_list.append(self.__serialize(item))
        return serialized_list

    def __serialize_mapping(self, mapping_object: dict[str, Any]) -> dict[str, Any]:
        """Recursively serializes the values of a dictionary.

        Args:
            mapping_object: Object to serialize.

        Returns:
            dict[str, Any]: Serialized object.
        """
        serialized_dict = {}
        for key, value in mapping_object.items():
            serialized_dict[key] = self.__serialize(value)
        return serialized_dict

    def __deserialize[ModelType](
        self, data: dict[str, Any], item_type: type[ModelType]
    ) -> ModelType:
        """Basic deserialization to a domain dataclass.

        Args:
            data: Dictionary to deserialize.
            item_type: The class to deserialize into.

        Returns:
            ModelType: Deserialized object.
        """

        annotations = getattr(item_type, "__annotations__", {})
        init_kwargs: dict[str, Any] = {}

        for field_name, value in data.items():
            if field_name not in annotations:
                continue

            field_type = str(annotations[field_name])

            if value is None:
                init_kwargs[field_name] = None
                continue

            init_kwargs[field_name] = self.__deserialize_field_value(field_name, value, field_type)

        return item_type(**init_kwargs)

    def __deserialize_field_value(self, field_name: str, value: Any, field_type: str) -> Any:
        """Converts a raw value to its expected type based on the annotation.

        Args:
            field_name: Name of the field to deserialize.
            value: Raw value to deserialize.
            field_type: Expected field type.

        Returns:
            Any: Deserialized value.
        """

        try:
            # 1. Dates and IP addresses
            value = self.__deserialize_network_or_temporal(value, field_type)

            # 2. Complex models (Asset, Access)
            value = self.__deserialize_domain_model(value, field_type)

            # 3. Enums
            return self.__deserialize_enums(value, field_type)

        except Exception:
            logger.warning("Deserialization error for field %s", field_name)
            return value

    def __deserialize_network_or_temporal(self, value: Any, field_type: str) -> Any:
        """Deserializes datetime types and IP addresses.

        Args:
            value: Raw value to deserialize.
            field_type: Expected field type.

        Returns:
            Any: Deserialized value.
        """

        if "datetime" in field_type and isinstance(value, str):
            return datetime.fromisoformat(value)

        if "IPv4Address" in field_type or "IPv6Address" in field_type:
            return ip_address(value)

        return value

    def __deserialize_domain_model(self, value: Any, field_type: str) -> Any:
        """Deserializes complex domain objects (Asset, Access, Identity, Finding).

        Args:
            value: Raw value to deserialize.
            field_type: Expected field type.

        Returns:
            Any: Deserialized value.
        """
        model_registry = {
            "Asset": Asset,
            "Identity": Identity,
            "Finding": Finding,
            "Access": Access,
        }

        for model_name, model_class in model_registry.items():
            if model_name in field_type:
                return self.__deserialize_into_model(value, model_class)

        return value

    def __deserialize_into_model(self, value: Any, model_class: type) -> Any:
        """Deserializes either a single dictionary or a list of dictionaries.

        Args:
            value: Value (dict or list) to transform.
            model_class: Target domain class.

        Returns:
            Any: Instance(s) of the model.
        """
        if isinstance(value, list):
            return [self.__deserialize(i, model_class) for i in value if isinstance(i, dict)]

        if isinstance(value, dict):
            return self.__deserialize(value, model_class)

        return value

    def __deserialize_enums(self, value: Any, field_type: str) -> Any:
        """Deserializes domain enums.

        Args:
            value: Raw value to deserialize.
            field_type: Expected field type.

        Returns:
            Any: Deserialized value.
        """
        enum_registry = {
            "IdentityType": IdentityType,
            "IdentityState": IdentityState,
            "RuleCategory": RuleCategory,
            "SeverityType": SeverityType,
        }

        for enum_name, enum_class in enum_registry.items():
            if enum_name in field_type:
                return enum_class(value)

        return value
