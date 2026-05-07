"""
secrets_manager.py
------------------
Dos usos:

1. TÚ lo ejecutas UNA VEZ para encriptar tus credenciales:
       python secrets_manager.py

   Te pregunta el Client ID y Client Secret, los encripta con XOR
   y genera el bloque listo para pegar en oauth_server.py.

2. La app lo importa en runtime para obtener los valores reales:
       from secrets_manager import get_client_id, get_client_secret
"""

import os
import base64

# ══════════════════════════════════════════════════════════════════════
#  PEGA AQUÍ LOS VALORES QUE GENERA ESTE SCRIPT (después de ejecutarlo)
#  Ejemplo de cómo quedan — reemplaza con los tuyos reales:
_KEY  = b'\xc7\x52\x85\xa0\xbc\xf5\x0b\xc3\x69\x65\x5f\x5e\x1c\xa3\x46\xbb'   # clave XOR (autogenerada)
_CID  = b'\xf3\x26\xb2\xcb\xc8\x9d\x3c\xa1\x13\x1c\x31\x34\x6c\xd7\x35\xc1\xb0\x26\xe8\xda\xce\xc2\x7d\xb4\x5e\x0c\x36\x67\x28\x97'   # Client ID  encriptado
_CSEC = b'\xbf\x6a\xf5\xc7\xd3\x9f\x6d\xf1\x0a\x1c\x69\x2b\x70\xcd\x3e\x8c\xa6\x20\xf1\xcc\xc4\x9a\x71\xa6\x1f\x07\x2b\x2f\x6f\xdb'   # Client Secret encriptado
# ══════════════════════════════════════════════════════════════════════


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def get_client_id() -> str:
    return _xor(_CID, _KEY).decode()


def get_client_secret() -> str:
    return _xor(_CSEC, _KEY).decode()


# ── Herramienta de encriptación (solo tú la corres) ────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Encriptador de credenciales — VTuber IA")
    print("=" * 55)
    print("Ingresa tus credenciales. NO se guardan en ningún archivo.")
    print()

    cid  = input("Client ID     → ").strip()
    csec = input("Client Secret → ").strip()

    if not cid or not csec:
        print("\n❌  Credenciales vacías. Abortando.")
        exit(1)

    # Generar clave aleatoria
    key = os.urandom(16)

    cid_enc  = _xor(cid.encode(),  key)
    csec_enc = _xor(csec.encode(), key)

    def fmt(b: bytes) -> str:
        return "b'" + "".join(f"\\x{byte:02x}" for byte in b) + "'"

    print()
    print("✅  Copia este bloque y pégalo en secrets_manager.py")
    print("    (reemplaza las líneas _KEY, _CID, _CSEC):")
    print()
    print(f"_KEY  = {fmt(key)}")
    print(f"_CID  = {fmt(cid_enc)}")
    print(f"_CSEC = {fmt(csec_enc)}")
    print()
    print("⚠️  Guarda bien tu Client ID y Secret originales")
    print("    por si necesitas regenerar esto en el futuro.")
    print("=" * 55)
