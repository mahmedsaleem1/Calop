import io

import cloudinary
import cloudinary.uploader

from app.core.config import Settings
from app.integrations.storage.image_storage import ImageStorage, StorageError, StoredImage


class CloudinaryImageStorage(ImageStorage):
    def __init__(self, settings: Settings):
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )

    def upload(self, data: bytes) -> StoredImage:
        try:
            upload_result = cloudinary.uploader.upload(
                io.BytesIO(data), folder="calop/captures", resource_type="image"
            )
        except Exception as exc:
            raise StorageError(str(exc)) from exc
        return StoredImage(url=upload_result["secure_url"], public_id=upload_result["public_id"])

    def delete(self, public_id: str) -> None:
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image")
        except Exception as exc:
            raise StorageError(str(exc)) from exc
