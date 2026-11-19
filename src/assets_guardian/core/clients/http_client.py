import logging
import time
from typing import Any

import requests
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)


class HttpClient:
    """Generic HTTP client with retry logic, exponential backoff, and 429 handling.

    Args:
        base_url: The base URL for all requests.
        headers: Headers to include in each request.
        timeout: The default timeout in seconds.
        max_retries: The maximum number of attempts for 429 and 500+ errors.
    """

    base_url: str
    session: requests.Session
    timeout: int
    max_retries: int

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        sslVerify: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        """Initializes the HttpClient."""

        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        self.timeout = timeout
        self.sslVerify = sslVerify
        self.max_retries = max_retries

    def _get_full_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return f"{self.base_url}/{url.lstrip('/')}"

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Sends an HTTP request with retry logic.

        Args:
            method: The HTTP method (GET, POST, etc.).
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        
        full_url = self._get_full_url(url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.sslVerify)

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(method, full_url, **kwargs)

                if (response.status_code == 429 or 500 <= response.status_code < 600) and (
                    attempt < self.max_retries
                ):
                    wait_time = self._get_wait_time(response, attempt)
                    logger.warning(
                        "Request failed (%d) for %s. Retrying in %ds (Attempt %d/%d)",
                        response.status_code,
                        full_url,
                        wait_time,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()

            except RequestException as e:
                # Retry on network errors (ConnectionError, Timeout, etc.)
                # HTTPError (from raise_for_status) is not retried here because it is handled above
                # or represents a 4xx error that should not be retried.
                if attempt < self.max_retries and not isinstance(e, HTTPError):
                    wait_time = self._get_wait_time(None, attempt)
                    logger.warning(
                        "Request failed for %s: %s. Retrying in %ds (Attempt %d/%d)",
                        full_url,
                        str(e),
                        wait_time,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(wait_time)
                    continue
                raise

            else:
                return response

        # Should never be reached unless max_retries < 0
        raise RuntimeError(f"Max retries reached for {full_url}")

    def _get_wait_time(self, response: requests.Response | None, attempt: int) -> int:
        """Calculates the wait time based on the Retry-After header or exponential backoff.

        Args:
            response: The HTTP response.
            attempt: The attempt number.

        Returns:
            int: The wait time in seconds.
        """
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                return int(retry_after)
        return int(2**attempt)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a GET request.

        Args:
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a POST request.

        Args:
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PUT request.

        Args:
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a DELETE request.

        Args:
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PATCH request.

        Args:
            url: The URL or path (appended to base_url).
            **kwargs: Extra arguments for requests.request.

        Returns:
            requests.Response: The HTTP response.

        Raises:
            HTTPError: If the request fails after the maximum number of attempts.
            RequestException: For other errors related to the request.
        """
        return self.request("PATCH", url, **kwargs)
