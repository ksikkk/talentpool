import socket
import unittest
from unittest.mock import patch

import launch


class LauncherTests(unittest.TestCase):
    def test_empty_address_list_does_not_prevent_startup(self):
        class FakeProcess:
            def __call__(self, command):
                self.command = command
                return 0
        process = FakeProcess()
        with patch.object(launch, "network_addresses", return_value=[]), patch.object(launch.subprocess, "call", process):
            self.assertEqual(launch.main(), 0)
        self.assertEqual(process.command[process.command.index("--host") + 1], "0.0.0.0")
        self.assertIn("--no-proxy-headers", process.command)

    def test_local_addresses_filter_loopback_and_unbindable_addresses(self):
        rows=[(socket.AF_INET,socket.SOCK_STREAM,0,"",("127.0.0.1",0)),
              (socket.AF_INET,socket.SOCK_STREAM,0,"",("10.20.30.40",0))]
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def bind(self,address): pass
        with patch.object(launch.socket, "getaddrinfo", return_value=rows):
            with patch.object(launch.socket,"socket",return_value=FakeSocket()):
                self.assertEqual(launch.network_addresses(), ["10.20.30.40"])


if __name__=="__main__":
    unittest.main()
