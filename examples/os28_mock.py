"""Demonstrate the optional provider interface without a network."""

from integrations.os28 import MockOS28Provider

provider = MockOS28Provider()
print([tool.name for tool in provider.list_tools()])
print(provider.call("example.echo", {"text": "test"}))
