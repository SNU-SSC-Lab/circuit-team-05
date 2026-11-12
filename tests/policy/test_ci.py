import tempfile
from pathlib import Path
import sys
import unittest
SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'scripts'))
from ci_policy import check_event
from policy import PolicyError
from run_rtl import validate_results
import test_policy


class EventTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_policy.RepositoryTest(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_pull_request_event(self):
        f=self.fixture
        event={'pull_request':{'base':{'sha':f.base},'head':{'sha':f.base},'body':f.body()}}
        self.assertEqual(check_event(f.root,event)['pr_check'],'passed')

    def test_non_pr_event(self):
        self.assertEqual(check_event(self.fixture.root,{})['pr_check'],'not_applicable')

    def test_non_sha_and_empty_body_are_rejected(self):
        f=self.fixture
        for base,body in [('HEAD',f.body()),(f.base,'')]:
            with self.subTest(base=base),self.assertRaises(PolicyError):
                check_event(f.root,{'pull_request':{'base':{'sha':base},'head':{'sha':f.base},'body':body}})

    def test_shell_text_in_body_remains_data(self):
        f=self.fixture
        body=f.body()+'\n$(touch SHOULD_NOT_EXIST)\n'
        check_event(f.root,{'pull_request':{'base':{'sha':f.base},'head':{'sha':f.base},'body':body}})
        self.assertFalse((f.root/'SHOULD_NOT_EXIST').exists())


class ResultTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='ssc-results-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.xml=self.root/'results.xml';self.stats=self.root/'stats.json'
        self.stats.write_text('{}')

    def test_selected_pass_and_nonselected_skip(self):
        self.xml.write_text('<testsuites><testcase name="selected"/><testcase name="other"><skipped/></testcase></testsuites>')
        validate_results(self.xml,'selected',self.stats)

    def test_no_test_failure_error_skip_and_missing_stats(self):
        cases=['', '<testcase name="selected"><failure/></testcase>',
               '<testcase name="selected"><error/></testcase>',
               '<testcase name="selected"><skipped/></testcase>']
        for inner in cases:
            self.xml.write_text(f'<testsuites>{inner}</testsuites>')
            with self.subTest(inner=inner),self.assertRaises(RuntimeError):
                validate_results(self.xml,'selected',self.stats)
        self.xml.write_text('<testsuites><testcase name="selected"/></testsuites>')
        self.stats.unlink()
        with self.assertRaises(RuntimeError):validate_results(self.xml,'selected',self.stats)


if __name__=='__main__':unittest.main()
