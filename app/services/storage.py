import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

UPLOAD_DIR = Path("./uploads")
ALLOWED_MIME_TYPES: dict[str, list[str]] = {
    "video": ["video/mp4", "video/webm", "video/x-msvideo"],
    "pdf": ["application/pdf"],
    "audio": ["audio/mpeg", "audio/wav", "audio/ogg"],
    "image": ["image/jpeg", "image/png", "image/webp"],
    "scorm": ["application/zip"],
    "document": [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ],
}
FLAT_ALLOWED = {mime for group in ALLOWED_MIME_TYPES.values() for mime in group}


async def _upload_local(file: UploadFile, folder: str) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = UPLOAD_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "file").suffix
    filename = f"{uuid.uuid4().hex}{ext}"
    path = target_dir / filename
    content = await file.read()
    path.write_bytes(content)
    return f"/uploads/{folder}/{filename}"


async def _delete_local(url: str) -> None:
    path = UPLOAD_DIR / url.replace("/uploads/", "")
    if path.exists():
        path.unlink()


async def _upload_s3(file: UploadFile, folder: str) -> str:
    try:
        import aioboto3
    except ImportError:
        raise RuntimeError("aioboto3 is required for S3 storage")

    ext = Path(file.filename or "file").suffix
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    content = await file.read()
    session = aioboto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    async with session.client("s3", endpoint_url=settings.S3_ENDPOINT or None) as s3:
        await s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content)
    endpoint = settings.S3_ENDPOINT or f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com"
    return f"{endpoint}/{key}"


async def _delete_s3(url: str) -> None:
    try:
        import aioboto3
    except ImportError:
        raise RuntimeError("aioboto3 is required for S3 storage")

    bucket, key = _parse_s3_url(url)
    session = aioboto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    async with session.client("s3", endpoint_url=settings.S3_ENDPOINT or None) as s3:
        await s3.delete_object(Bucket=bucket, Key=key)


def _parse_s3_url(url: str) -> tuple[str, str]:
    parts = url.replace("https://", "").split("/")
    bucket = parts[0].split(".")[0]
    key = "/".join(parts[1:])
    return bucket, key


async def validate_mime(file: UploadFile) -> str:
    if file.content_type not in FLAT_ALLOWED:
        raise ValueError(f"Tipo de arquivo não permitido: {file.content_type}")
    return file.content_type


async def validate_size(file: UploadFile) -> None:
    content = await file.read()
    await file.seek(0)
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise ValueError(f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")


async def upload_file(file: UploadFile, folder: str) -> str:
    mime = await validate_mime(file)
    await validate_size(file)
    if settings.STORAGE_BACKEND == "s3":
        return await _upload_s3(file, folder)
    return await _upload_local(file, folder)


async def delete_file(url: str) -> None:
    if settings.STORAGE_BACKEND == "s3":
        await _delete_s3(url)
    else:
        await _delete_local(url)


async def get_presigned_url(key: str, expires_in: int = 3600) -> str | None:
    if settings.STORAGE_BACKEND != "s3":
        return None
    try:
        import aioboto3
    except ImportError:
        return None
    session = aioboto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    async with session.client("s3", endpoint_url=settings.S3_ENDPOINT or None) as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
