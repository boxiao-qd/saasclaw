"""web_fetch tool — fetch URL content with SSRF protection, HTML→markdown conversion."""

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import httpx

from app.config import settings

# SSRF blacklist — private/reserved IP ranges (IPv4 + IPv6)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),     # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),    # IPv6 link-local
]


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address falls in any private/reserved network."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return True
    except ValueError:
        return True  # Invalid IP = block
    return False


def _resolve_and_check(hostname: str) -> list[str]:
    """Resolve hostname to IPs, check all against private network blacklist.

    Returns list of resolved public IPs, or raises ValueError if any IP is private.
    Raises ValueError if DNS resolution fails.
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"DNS resolution failed for '{hostname}' — request blocked")

    public_ips = []
    for _, _, _, _, addr in addr_infos:
        ip_str = addr[0]
        if _is_private_ip(ip_str):
            raise ValueError(f"Hostname '{hostname}' resolves to private IP '{ip_str}' — request blocked")
        if ip_str not in public_ips:
            public_ips.append(ip_str)
    return public_ips


def _check_url_ssrf(url: str) -> None:
    """Validate URL scheme and hostname against SSRF blacklist. Raises ValueError if blocked."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        raise ValueError("file:// protocol is not allowed")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.hostname in ("localhost", "0.0.0.0"):
        raise ValueError("localhost/0.0.0.0 is not allowed")
    # Resolve and check all IPs
    _resolve_and_check(parsed.hostname)


def _html_to_markdown(html: str) -> str:
    """HTML→markdown conversion via html2text, with plain-text fallback."""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html)
    except ImportError:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:5000]


# Shared httpx client — reused across calls
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=20, follow_redirects=False, max_redirects=0)
    return _client


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch content from a URL and convert to markdown format. Supports HTTP/HTTPS public URLs only.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch (public HTTP/HTTPS only)"},
                "format": {"type": "string", "enum": ["markdown", "text"], "default": "markdown", "description": "Output format"},
            },
            "required": ["url"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    url = args.get("url", "")
    format_type = args.get("format", "markdown")

    # Initial SSRF check
    try:
        _check_url_ssrf(url)
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    max_bytes = settings.web_fetch_max_content_bytes

    try:
        client = await _get_client()
        # Manual redirect handling — re-check SSRF on each redirect
        current_url = url
        redirects_followed = 0
        max_redirects = 5

        while redirects_followed < max_redirects:
            resp = await client.get(current_url, headers={"User-Agent": "Mozilla/5.0 (compatible; SuperAgent/1.0)"})

            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get("location", "")
                if not redirect_url:
                    return json.dumps({"error": f"Redirect without location header at {current_url}"}, ensure_ascii=False)
                # Re-check SSRF on redirect target
                try:
                    _check_url_ssrf(redirect_url)
                except ValueError as e:
                    return json.dumps({"error": f"Redirect target blocked: {e}"}, ensure_ascii=False)
                current_url = redirect_url
                redirects_followed += 1
                continue

            break  # Non-redirect response

        if redirects_followed >= max_redirects:
            return json.dumps({"error": f"Too many redirects (> {max_redirects})"}, ensure_ascii=False)

        if resp.status_code >= 400:
            return json.dumps({"error": f"HTTP error {resp.status_code}: {resp.reason_phrase}", "url": url}, ensure_ascii=False)

        # Byte-aware content truncation
        content_bytes = resp.content
        if len(content_bytes) > max_bytes:
            content_bytes = content_bytes[:max_bytes]
        content = content_bytes.decode("utf-8", errors="replace")

        content_type = resp.headers.get("content-type", "")

        # PDF detection
        if "application/pdf" in content_type or current_url.lower().endswith(".pdf"):
            return json.dumps({"content": f"PDF document detected. PDF content extraction is not supported in MVP.", "url": current_url, "content_type": "pdf"}, ensure_ascii=False)

        # HTML→markdown
        if format_type == "markdown" and "html" in content_type:
            content = _html_to_markdown(content)

        return json.dumps({"content": content, "url": current_url, "content_type": content_type, "content_length": len(content)}, ensure_ascii=False)

    except httpx.TimeoutException:
        return json.dumps({"error": f"Request timed out: {url}"}, ensure_ascii=False)
    except httpx.RequestError as e:
        return json.dumps({"error": f"Request failed: {e}"}, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)