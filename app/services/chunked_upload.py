import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

CHUNK_DIR = Path("./uploads/_chunks")


class ChunkedUploadTracker:
    """Gerencia uploads chunked (retomáveis) no disco."""

    @staticmethod
    def init_upload(filename: str, folder: str, total_chunks: int) -> str:
        CHUNK_DIR.mkdir(parents=True, exist_ok=True)
        upload_id = uuid.uuid4().hex
        meta = {
            "upload_id": upload_id,
            "filename": filename,
            "folder": folder,
            "total_chunks": total_chunks,
            "received_chunks": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        with open(CHUNK_DIR / f"{upload_id}.json", "w") as f:
            json.dump(meta, f)
        return upload_id

    @staticmethod
    def save_chunk(upload_id: str, chunk_index: int, data: bytes) -> dict:
        meta_path = CHUNK_DIR / f"{upload_id}.json"
        if not meta_path.exists():
            raise ValueError("Upload nao encontrado")
        with open(meta_path) as f:
            meta = json.load(f)

        if chunk_index in meta["received_chunks"]:
            return meta

        chunk_dir = CHUNK_DIR / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / str(chunk_index)).write_bytes(data)
        meta["received_chunks"].append(chunk_index)
        meta["received_chunks"].sort()
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        return meta

    @staticmethod
    def get_status(upload_id: str) -> dict:
        meta_path = CHUNK_DIR / f"{upload_id}.json"
        if not meta_path.exists():
            raise ValueError("Upload nao encontrado")
        with open(meta_path) as f:
            return json.load(f)

    @staticmethod
    def is_complete(upload_id: str) -> bool:
        meta = ChunkedUploadTracker.get_status(upload_id)
        return len(meta["received_chunks"]) == meta["total_chunks"]

    @staticmethod
    def list_missing(upload_id: str) -> list[int]:
        meta = ChunkedUploadTracker.get_status(upload_id)
        received = set(meta["received_chunks"])
        return [i for i in range(meta["total_chunks"]) if i not in received]

    @staticmethod
    def assemble(upload_id: str) -> tuple[bytes, str, str]:
        meta = ChunkedUploadTracker.get_status(upload_id)
        if not ChunkedUploadTracker.is_complete(upload_id):
            raise ValueError("Upload ainda incompleto")
        chunks = bytearray()
        for i in range(meta["total_chunks"]):
            chunk_path = CHUNK_DIR / upload_id / str(i)
            chunks.extend(chunk_path.read_bytes())
        meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        with open(CHUNK_DIR / f"{upload_id}.json", "w") as f:
            json.dump(meta, f)
        return bytes(chunks), meta["filename"], meta["folder"]

    @staticmethod
    def cleanup(upload_id: str):
        meta_path = CHUNK_DIR / f"{upload_id}.json"
        chunk_dir = CHUNK_DIR / upload_id
        if meta_path.exists():
            meta_path.unlink()
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir)

    @staticmethod
    def complete_and_store(upload_id: str) -> str:
        content, filename, folder = ChunkedUploadTracker.assemble(upload_id)
        target_dir = Path("./uploads") / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix
        name = f"{uuid.uuid4().hex}{ext}"
        path = target_dir / name
        path.write_bytes(content)
        ChunkedUploadTracker.cleanup(upload_id)
        return f"/uploads/{folder}/{name}"
