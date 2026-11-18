import ipaddress
import unittest
from unittest.mock import patch

import launch

class LauncherTests(unittest.TestCase):
    def test_single_managed_corporate_ip_accepted(self):
        adapters=[{"ip":"11.22.33.44","prefix":24,"alias":"Ethernet","gateway":True,"category":"DomainAuthenticated"}]
        self.assertEqual(launch.pick_adapter(adapters)["ip"],"11.22.33.44")
    def test_prefer_gateway_if_multiple(self):
        adapters=[
          {"ip":"192.168.99.1","prefix":24,"alias":"vEthernet","gateway":False,"category":"Private"},
          {"ip":"10.20.30.40","prefix":23,"alias":"Ethernet","gateway":True,"category":"DomainAuthenticated"}
        ]
        with patch("builtins.input",return_value=""):
            self.assertEqual(launch.pick_adapter(adapters)["ip"],"10.20.30.40")
    def test_narrow_subnet(self):
        ip=ipaddress.IPv4Address("11.22.33.44")
        subnet=ipaddress.ip_network(f"{ip}/{max(16,24)}",strict=False)
        self.assertEqual(str(subnet),"11.22.33.0/24")
        self.assertNotIn(ipaddress.IPv4Address("11.22.34.1"),subnet)

if __name__=="__main__":
    unittest.main()
