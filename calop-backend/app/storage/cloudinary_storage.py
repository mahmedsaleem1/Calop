import io

import cloudinary
import cloudinary.uploader

from app.config import Settings
from app.storage.base import ImageStorage, StorageError, StoredImage


class CloudinaryStorage(ImageStorage):
    def __init__(self, settings: Settings):
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )

    def upload(self, data: bytes) -> StoredImage:
        try:
            res = cloudinary.uploader.upload(
                io.BytesIO(data), folder="calop/captures", resource_type="image"
            )
        except Exception as exc:
            raise StorageError(str(exc)) from exc
        return StoredImage(url=res["secure_url"], public_id=res["public_id"])

    def delete(self, public_id: str) -> None:
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image")
        except Exception as exc:
            raise StorageError(str(exc)) from exc
