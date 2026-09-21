import unittest
from backend.range_compiler import compile_range

class RangeCompilerTests(unittest.TestCase):
    def test_compiles_approved_isolated_graph(self):
        result=compile_range({"name":"demo","review":{"status":"approved"},"isolation":{"production_bridge":False,"internet_egress":False},"nodes":[{"id":"fw","name":"Firewall","type":"firewall","zone":"dmz"},{"id":"hmi","name":"HMI","type":"hmi","zone":"control"}],"links":[{"id":"l1","source":"fw","target":"hmi"}]})
        self.assertIn('fw:eth1',result['containerlab']); self.assertEqual(result['inventory']['nodes'][0]['template'],'firewall-gateway')
    def test_refuses_unapproved_or_unsafe_graph(self):
        base={"name":"demo","nodes":[{"id":"a","name":"A","type":"server","zone":"dmz"}],"links":[]}
        with self.assertRaises(ValueError): compile_range(base)
        base.update({"review":{"status":"approved"},"isolation":{"production_bridge":True}})
        with self.assertRaises(ValueError): compile_range(base)
if __name__ == '__main__': unittest.main()