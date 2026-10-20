"""Validation for user-configurable outbound provider URLs."""
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeProviderURL(ValueError):
    pass


PUBLIC_PROVIDER_HOSTS = {
    "openai": {"api.openai.com"},
    "openrouter": {"openrouter.ai"},
    "anthropic": {"api.anthropic.com"},
    "gemini": {"generativelanguage.googleapis.com"},
}


def validate_provider_url(url: str, *, allow_private: bool = False) -> str:
    parsed = urlsplit((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeProviderURL("Provider URL must use http or https")
    if parsed.username or parsed.password:
        raise UnsafeProviderURL("Provider URL must not contain credentials")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeProviderURL("Provider URL has an invalid port") from exc

    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except (socket.gaierror, ValueError) as exc:
        raise UnsafeProviderURL("Provider hostname could not be resolved") from exc

    if not addresses:
        raise UnsafeProviderURL("Provider hostname could not be resolved")
    if not allow_private and any(not address.is_global for address in addresses):
        raise UnsafeProviderURL("Private or local provider addresses require admin access")
    return parsed.geturl().rstrip("/")


def provider_allows_private_network(provider: dict) -> bool:
    return provider.get("provider_key") in {"lmstudio", "ollama"}


def validate_provider_destination(url: str, provider_key: str, *, is_admin: bool) -> str:
    """Bind non-admin providers to known public hosts; admins may add custom/local providers."""
    parsed = urlsplit((url or "").strip())
    if not is_admin:
        allowed_hosts = PUBLIC_PROVIDER_HOSTS.get(provider_key, set())
        if not parsed.hostname or parsed.hostname.casefold() not in allowed_hosts:
            raise UnsafeProviderURL("This provider host requires admin access")
    allow_private = is_admin and provider_key in {"lmstudio", "ollama"}
    return validate_provider_url(url, allow_private=allow_private)
