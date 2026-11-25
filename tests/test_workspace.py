import unittest
from workspace_acceptance import run_workspace_acceptance
class WorkspaceTests(unittest.TestCase):
    def test_offline_integration(self):
        r=run_workspace_acceptance()
        self.assertEqual(len(r["checks"]),21)
        self.assertTrue(all(x["Kết quả"]=="Đạt" for x in r["checks"]))
if __name__=="__main__": unittest.main()
