import logging

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError
from unittest.mock import MagicMock

from assets_guardian.core.clients.http_client import HttpClient

# Desactivate logging for tests to avoid cluttering output
logging.getLogger("assets_guardian.core.clients.http_client").setLevel(logging.CRITICAL)


@pytest.fixture
def http_client():
    return HttpClient(base_url="https://api.example.com", max_retries=2)


@responses.activate
def test_successful_get(http_client):
    responses.add(responses.GET, "https://api.example.com/test", json={"status": "ok"}, status=200)

    response = http_client.get("test")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(responses.calls) == 1


@responses.activate
def test_base_url_normalization():
    # Test normalization with slash and without
    c1 = HttpClient(base_url="https://api.com/")
    c2 = HttpClient(base_url="https://api.com")

    responses.add(responses.GET, "https://api.com/endpoint", status=200)

    c1.get("/endpoint")
    c1.get("endpoint")
    c2.get("/endpoint")
    c2.get("endpoint")

    for call in responses.calls:
        assert call.request.url == "https://api.com/endpoint"


@responses.activate
def test_full_url_bypass():
    client = HttpClient(base_url="https://api.com")
    responses.add(responses.GET, "https://other.com/ext", status=200)

    client.get("https://other.com/ext")
    assert responses.calls[0].request.url == "https://other.com/ext"


@responses.activate
def test_default_headers():
    client = HttpClient(headers={"Authorization": "Bearer token"})
    responses.add(responses.GET, "https://test.com", status=200)

    client.get("https://test.com")

    assert responses.calls[0].request.headers["Authorization"] == "Bearer token"


@responses.activate
def test_retry_on_5xx(http_client, mocker):
    mocker.patch("time.sleep")

    responses.add(responses.GET, "https://api.example.com/fail", status=500)
    responses.add(responses.GET, "https://api.example.com/fail", status=503)
    responses.add(responses.GET, "https://api.example.com/fail", status=200)

    response = http_client.get("fail")

    assert response.status_code == 200
    assert len(responses.calls) == 3


@responses.activate
def test_retry_on_429_with_retry_after(http_client, mocker):
    mock_sleep = mocker.patch("time.sleep")

    responses.add(
        responses.GET, "https://api.example.com/limit", status=429, headers={"Retry-After": "5"}
    )
    responses.add(responses.GET, "https://api.example.com/limit", status=200)

    response = http_client.get("limit")

    assert response.status_code == 200
    assert len(responses.calls) == 2
    mock_sleep.assert_called_once_with(5)


@responses.activate
def test_retry_on_429_without_retry_after(http_client, mocker):
    mock_sleep = mocker.patch("time.sleep")

    responses.add(responses.GET, "https://api.example.com/limit-no-header", status=429)
    responses.add(responses.GET, "https://api.example.com/limit-no-header", status=200)

    response = http_client.get("limit-no-header")

    assert response.status_code == 200
    assert len(responses.calls) == 2
    mock_sleep.assert_called_once_with(1)  # 2**0 backoff


@responses.activate
def test_max_retries_exceeded_raises_http_error(http_client, mocker):
    mocker.patch("time.sleep")
    responses.add(responses.GET, "https://api.example.com/always-500", status=500)

    with pytest.raises(HTTPError):
        http_client.get("always-500")

    assert len(responses.calls) == 3  # Initial + 2 retries


@responses.activate
def test_404_not_retried(http_client, mocker):
    mocker.patch("time.sleep")
    responses.add(responses.GET, "https://api.example.com/notfound", status=404)

    with pytest.raises(HTTPError):
        http_client.get("notfound")

    assert len(responses.calls) == 1  # Should not retry 404


@responses.activate
def test_retry_on_connection_error(http_client, mocker):
    mocker.patch("time.sleep")

    responses.add(
        responses.GET, "https://api.example.com/conn-fail", body=RequestsConnectionError("Failed")
    )
    responses.add(responses.GET, "https://api.example.com/conn-fail", status=200)

    response = http_client.get("conn-fail")

    assert response.status_code == 200
    assert len(responses.calls) == 2


@responses.activate
def test_max_retries_network_error_raises_exception(http_client, mocker):
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        "https://api.example.com/hard-fail",
        body=RequestsConnectionError("Hard Fail"),
    )

    with pytest.raises(RequestsConnectionError):
        http_client.get("hard-fail")

    assert len(responses.calls) == 3


@responses.activate
def test_http_methods(http_client: HttpClient) -> None:
    responses.add(responses.POST, "https://api.example.com/post", status=201)
    responses.add(responses.PUT, "https://api.example.com/put", status=200)
    responses.add(responses.DELETE, "https://api.example.com/delete", status=204)
    responses.add(responses.PATCH, "https://api.example.com/patch", status=200)

    assert http_client.post("post").status_code == 201
    assert http_client.put("put").status_code == 200
    assert http_client.delete("delete").status_code == 204
    assert http_client.patch("patch").status_code == 200


@responses.activate
def test_max_retries_minus_one() -> None:
    # Case where the loop won't even start
    client = HttpClient(base_url="https://api.com", max_retries=-1)

    # This should raise RuntimeError since the loop is skipped
    with pytest.raises(RuntimeError, match="Max retries reached"):
        client.get("test")


@responses.activate
def test_ssl_disable() -> None:
    http_client_no_ssl = HttpClient(base_url="https://api.example.com", max_retries=2, sslVerify=False)
    http_client_no_ssl.session = MagicMock()
    http_client_no_ssl.session.request.return_value = MagicMock(
        status_code=200
    )
    
    responses.add(responses.GET, "https://api.example.com/test", json={"status": "ok"}, status=200)

    http_client_no_ssl.get("test")

    assert http_client_no_ssl.sslVerify == False
    http_client_no_ssl.session.request.assert_called_once_with(
        "GET",
        "https://api.example.com/test",
        timeout=30,
        verify=False
    )
    
