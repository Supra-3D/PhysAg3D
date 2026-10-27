"""Offline checks for bounded broker framing and receipt-preserving errors."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import trellis2_tool as client


class Stream:
    def __init__(self, response, binary=b""):
        data = json.dumps(response).encode()
        self.incoming = io.BytesIO(struct.pack("!I", len(data)) + data + binary)
        self.sent = b""
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def sendall(self, data): self.sent += data
    def recv(self, count): return self.incoming.read(min(count, 3))


class BrokerTests(unittest.TestCase):
    def request(self):
        return {"action": "doctor", "config": {
            "transport": "broker_tcp", "broker_host": "127.0.0.1", "broker_port": 23921,
            "server_config": {"transport": "unix", "socket": "/trusted/broker.sock"}}}

    def test_fragmented_frame_and_server_profile(self):
        stream = Stream({"ok": True, "result": {"ok": True}})
        with patch.object(client.socket, "create_connection", return_value=stream) as connect:
            self.assertEqual(client.rpc(self.request()), {"ok": True})
        connect.assert_called_once_with(("127.0.0.1", 23921), timeout=120)
        payload = json.loads(stream.sent[4:])
        self.assertEqual(payload["config"], self.request()["config"]["server_config"])
        self.assertNotIn("broker_port", payload["config"])

    def test_binary_collection_is_exclusive_and_exact(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "artifact"
            stream = Stream({"ok": True, "binary_bytes": 7}, b"example")
            with patch.object(client.socket, "create_connection", return_value=stream):
                client.rpc(self.request(), out)
            self.assertEqual(out.read_bytes(), b"example")
            stream = Stream({"ok": True, "binary_bytes": 7}, b"changed")
            with patch.object(client.socket, "create_connection", return_value=stream), self.assertRaises(RuntimeError):
                client.rpc(self.request(), out)
            self.assertEqual(out.read_bytes(), b"example")

    def test_external_endpoint_rejected_and_no_transport_retry(self):
        request = self.request()
        request["config"]["broker_host"] = "external.example"
        with patch.object(client.socket, "create_connection") as connect, self.assertRaises(ValueError):
            client.rpc(request)
        connect.assert_not_called()
        with patch.object(client.socket, "create_connection", side_effect=TimeoutError) as connect:
            with self.assertRaisesRegex(RuntimeError, "saved receipt"):
                client.rpc(self.request())
            self.assertEqual(connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
