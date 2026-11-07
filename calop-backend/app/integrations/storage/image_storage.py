from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(Exception):
    pass


@dataclass
class StoredImage:
    url: str
    public_id: str


class ImageStorage(ABC):
    """Cloudinary today; local disk / S3-style storage can implement this later."""

    @abstractmethod
    def upload(self, data: bytes) -> StoredImage: ...

    @abstractmethod
    def delete(self, public_id: str) -> None: ...
