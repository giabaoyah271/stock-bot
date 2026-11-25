import unittest
from paper_acceptance import run_acceptance,event
from paper_trading_core import new_account,append_session,replay,config,COHORT,readiness
class PaperIntegrationTests(unittest.TestCase):
    def test_all_modules(self):
        result=run_acceptance()
        self.assertEqual(len(result["checks"]),11)
        self.assertEqual(len(result["result"]["daily"]),3)
    def test_fixed_cohort(self):
        self.assertEqual(len(COHORT),115)
        self.assertEqual(len(config()["symbols"]),115)
        self.assertEqual(config()["policy"]["max_positions"],5)
    def test_freeze_blocks_same_day(self):
        a=new_account("TEST","2026-11-24T09:00:00+07:00")
        with self.assertRaises(ValueError): append_session(a,event("2026-11-24"))
    def test_empty_account_not_ready(self):
        a=new_account("PAPER","2026-11-25T16:00:00+07:00")
        r=replay(a)
        self.assertEqual(r["cash"],100000000)
        self.assertFalse(all(x["Đạt"] for x in readiness(r,"PAPER")))
if __name__=="__main__": unittest.main()
