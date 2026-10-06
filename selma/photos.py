"""Fotos do checklist: compressão, envio ao Supabase Storage e registro em
`checklist_photo` (ver supabase/migrations/20261006000000_checklist_photo.sql).

As fotos vão para o bucket PRIVADO `checklist-photos` na hora da captura (não só no
fim), para que perder a sessão do celular não perca as imagens. Não há análise de IA:
elas só ficam guardadas para entrar no relatório final.
"""
import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from . import db

BUCKET = "checklist-photos"
MAX_SIDE_PX = 1600      # fotos de celular têm 4000+ px: reduz para caber no PDF/Word
JPEG_QUALITY = 82
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


class PhotoError(Exception):
    """Erro apresentável ao usuário (arquivo inválido, falha de envio...)."""


def compress_image(raw: bytes) -> bytes:
    """Corrige a rotação (EXIF), limita o lado maior e converte para JPEG."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as e:
        raise PhotoError("Não consegui abrir a imagem. Envie um arquivo JPG, PNG ou WEBP.") from e

    if img.mode not in ("RGB", "L"):
        # PNG/WEBP com transparência: compõe sobre fundo branco antes de virar JPEG.
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode == "L":
        img = img.convert("RGB")

    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def upload_photo(service_order_id: int, part_key: str, instance: int, slot: str,
                 raw: bytes, technical_id: int | None = None,
                 caption: str | None = None) -> dict:
    """Comprime, envia ao bucket e registra a foto. Devolve a linha de `checklist_photo`."""
    data = compress_image(raw)
    path = f"os-{service_order_id}/{part_key}/{instance}/{slot}-{uuid.uuid4().hex}.jpg"
    sb = db.client()
    try:
        sb.storage.from_(BUCKET).upload(
            path, data, {"content-type": "image/jpeg", "upsert": "false"})
    except Exception as e:  # noqa: BLE001
        raise PhotoError(f"Falha ao enviar a foto: {e}") from e

    try:
        res = sb.table("checklist_photo").insert({
            "service_order_id": service_order_id,
            "part_key": part_key,
            "instance_number": instance,
            "slot": slot,
            "storage_path": path,
            "mime_type": "image/jpeg",
            "size_bytes": len(data),
            "taken_by_technical_id": technical_id,
            "caption": caption,
        }).execute()
    except Exception as e:  # noqa: BLE001
        # Não deixa arquivo órfão no bucket se o registro falhar.
        try:
            sb.storage.from_(BUCKET).remove([path])
        except Exception:  # noqa: BLE001
            pass
        raise PhotoError(f"Falha ao registrar a foto: {e}") from e
    return (res.data or [{}])[0]


def list_slot_photos(service_order_id: int, part_key: str, instance: int, slot: str) -> list[dict]:
    res = (
        db.client().table("checklist_photo").select("id, storage_path, created_at")
        .eq("service_order_id", service_order_id).eq("part_key", part_key)
        .eq("instance_number", instance).eq("slot", slot)
        .order("created_at").execute()
    )
    return res.data or []


def delete_slot_photos(service_order_id: int, part_key: str, instance: int, slot: str) -> int:
    """Remove as fotos do item (arquivos e registros). Devolve quantas foram removidas."""
    rows = list_slot_photos(service_order_id, part_key, instance, slot)
    if not rows:
        return 0
    sb = db.client()
    sb.storage.from_(BUCKET).remove([r["storage_path"] for r in rows])
    sb.table("checklist_photo").delete().in_("id", [r["id"] for r in rows]).execute()
    return len(rows)


def signed_url(storage_path: str, expires_in: int = 3600) -> str | None:
    try:
        res = db.client().storage.from_(BUCKET).create_signed_url(storage_path, expires_in)
    except Exception:  # noqa: BLE001
        return None
    return res.get("signedURL") or res.get("signedUrl")
