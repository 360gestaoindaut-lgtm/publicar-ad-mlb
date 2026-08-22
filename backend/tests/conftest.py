"""Configuração compartilhada da suíte.

O bloqueio de rede é o ponto central deste arquivo: nenhum teste deve sair
para a internet. Um teste que chama a API do Gemini/OpenAI/ML de verdade é
lento, custa dinheiro, falha sem internet e — pior — passa por acidente
quando deveria estar exercitando um mock. Aqui a falha é explícita e diz
qual URL escapou.

O patch é aplicado na camada de **transporte**, não no `AsyncClient`, porque
é o transporte que de fato abre o socket. Isso mantém funcionando tudo que
já é legítimo hoje:

- teste que faz `patch("...httpx.AsyncClient")` ou mocka `client.post` →
  nunca chega no transporte;
- `ASGITransport` (usado em `test_health.py` para falar com o app FastAPI
  em memória) é outra classe, não é interceptada;
- `httpx.MockTransport`, se alguém usar, idem.

Ou seja: só quebra o que realmente tentaria sair para a rede.
"""
import pytest

_ALLOW_MARK = "allow_network"


class NetworkAccessAttempted(RuntimeError):
    """Levantada quando um teste tenta abrir uma conexão real."""


def _blocked(method: str, url: object) -> NetworkAccessAttempted:
    return NetworkAccessAttempted(
        f"Chamada de rede real bloqueada na suíte: {method} {url}\n"
        "Mocke o cliente HTTP no teste. Se a chamada real for mesmo "
        f"intencional, marque o teste com @pytest.mark.{_ALLOW_MARK}."
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{_ALLOW_MARK}: permite que o teste faça requisições de rede reais.",
    )


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """Faz qualquer egresso HTTP real levantar exceção durante os testes."""
    if request.node.get_closest_marker(_ALLOW_MARK):
        return

    import httpx

    async def _async_guard(self, request_obj, *args, **kwargs):
        raise _blocked(request_obj.method, request_obj.url)

    def _sync_guard(self, request_obj, *args, **kwargs):
        raise _blocked(request_obj.method, request_obj.url)

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", _async_guard, raising=True
    )
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", _sync_guard, raising=True
    )

    # boto3/botocore (R2) sai por um caminho próprio, fora do httpx.
    try:
        from botocore.httpsession import URLLib3Session
    except ImportError:
        return

    def _botocore_guard(self, request_obj, *args, **kwargs):
        raise _blocked(getattr(request_obj, "method", "?"), getattr(request_obj, "url", "?"))

    monkeypatch.setattr(URLLib3Session, "send", _botocore_guard, raising=True)
