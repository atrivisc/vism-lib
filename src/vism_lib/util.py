"""Utility functions for VISM components."""
import ipaddress
import base64

import pkcs11
from starlette.requests import Request

def is_valid_ip(ip_str):
    """Check if a string is a valid IP address."""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def is_valid_subnet(subnet_str):
    """Check if a string is a valid subnet."""
    try:
        ipaddress.ip_network(subnet_str, strict=False)
        return True
    except ValueError:
        return False


def b64u_decode(data: str) -> bytes:
    """Decode base64url encoded data."""
    if data is None:
        return b""

    if isinstance(data, bytes):
        data = data.decode("ascii")

    data = data.strip()
    if data == "":
        return b""

    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)

    return base64.urlsafe_b64decode(data)


def snake_to_camel(name):
    """Convert snake_case to camelCase."""
    split = name.split('_')
    return split[0] + ''.join(word.capitalize() for word in split[1:])


def absolute_url(request: Request, path: str) -> str:
    """Build absolute URL from request and path."""
    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")

    base = str(request.base_url.replace(scheme=scheme)).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path

    return f"{base}{path}"


def get_client_ip(request: Request):
    """Get client IP address from request, respecting X-Forwarded-For."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host
    return ip


def fix_base64_padding(base64_string):
    """Fix base64 string padding if missing."""
    padding_needed = len(base64_string) % 4
    if padding_needed != 0:
        base64_string += "=" * (4 - padding_needed)
    return base64_string
