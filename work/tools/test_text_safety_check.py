import unittest
from text_safety_check import apply_capacities, assess_record, load_exceptions, EXCEPTIONS
from text_expansion_check import measure_expansion

class SafetyTests(unittest.TestCase):
    def contract(self, **extra):
        return dict(bank='a027/0000', ids=None, capacity_units=3, stage='stored',
                    evidence_level='rom_guarded', status='passed', **extra)
    def test_exact_and_one_over(self):
        c=self.contract()
        for units,status in [([1,2,65535],'passed'),([1,2,3,65535],'failed')]:
            self.assertEqual(apply_capacities(units,measure_expansion(units),[c],'a027/0000',0)[0]['status'],status)
    def test_known_consumer_does_not_certify_other_consumers(self):
        r=assess_record([1,65535],[2,65535],'a027/0000#0',[self.contract()])
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(r['capacity'][0]['status'],'passed')
    def test_unmapped_text_is_accounted_incomplete(self):
        r=assess_record([1,65535],[2,65535],'a027/0001#0',[self.contract()])
        self.assertIn('no_capacity_contract',r['gaps'])
    def test_missing_guard_cannot_pass(self):
        c=self.contract();c['status']='incomplete'
        self.assertEqual(apply_capacities([1,65535],measure_expansion([1,65535]),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_unknown_variable_cannot_fit_by_stored_length(self):
        c=self.contract();c['stage']='expanded'
        u=[65534,256,1,0,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_policy_overflow_detected_without_promoting_policy_fit(self):
        c=self.contract();c.update(status='incomplete',evidence_level='policy_only')
        for u,status in [([1,65535],'incomplete'),([1,2,3,65535],'failed')]:
            self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],status)
    def test_decoded_command_needs_expansion_contract(self):
        c=self.contract();c['stage']='decompressed'
        u=[65534,256,1,0,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_removed_variable_fails_even_when_capacity_unknown(self):
        r=assess_record([65534,256,1,0,65535],[2,65535],'a027/0001#0',[])
        self.assertEqual(r['status'],'failed')

    def test_missing_guard_status_is_incomplete(self):
        c=self.contract();del c['status']
        u=[1,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_inherited_overflow_is_explicit_not_new_bug(self):
        u=[1,2,3,65535]
        r=assess_record(u,u,'a027/0000#0',[self.contract()])
        self.assertEqual(r['status'],'incomplete')
        self.assertTrue(r['capacity'][0]['inherited'])

    def exception(self, **extra):
        e=dict(check='controls',ref='a027/0001#0',code='substitution_contract_changed',source=[[259,[0]]],candidate=[],decisions=['D-0000'],reason='approved')
        e.update(extra);return {e['ref']:[e]}
    def test_exception_waives_only_exact_finding(self):
        src=[65534,259,1,0,65535]
        r=assess_record(src,[2,65535],'a027/0001#0',[],exceptions=self.exception())
        self.assertNotEqual(r['status'],'failed')
        self.assertEqual(r['waived'][0]['decisions'],['D-0000'])
        # A different candidate change on the same string still fails.
        r=assess_record(src,[65534,259,1,1,65535],'a027/0001#0',[],exceptions=self.exception())
        self.assertEqual(r['status'],'failed')
        # Same finding on another string is not waived.
        r=assess_record(src,[2,65535],'a027/0002#0',[],exceptions=self.exception())
        self.assertEqual(r['status'],'failed')
    def test_repository_exceptions_are_valid_and_cite_decisions(self):
        entries=load_exceptions(EXCEPTIONS)
        self.assertEqual(sorted(entries),['a027/0448#163','a027/0466#199'])
        for es in entries.values():
            self.assertTrue(all(any(d.startswith('D-') for d in e['decisions']) for e in es))

