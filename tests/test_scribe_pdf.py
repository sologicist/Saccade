"""Production Scribe contracts with synthetic PDFs and a stub network boundary."""
import base64
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from AutoCua.saccade import scribe_pdf
from AutoCua.saccade.business_contract import BusinessError, digest
from AutoCua.saccade.capabilities import catalogue, execute_worker
from AutoCua.saccade.platform_learning import PlatformLearningControl
from AutoCua.saccade.operator_requests import OperatorRequests
from tests.business_fixtures import BusinessFixture

class ProductionScribe(unittest.TestCase):
    def test_navigation_click_does_not_create_or_consume_a_download_decision(self):
        pending=copy.deepcopy(self.c.execution.pending)
        decision=self.c.authorize_execution({'type':'click','id':2,'times':1},self.stamp,self.elements)
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['effect'],'interaction')
        self.assertEqual(self.c.execution.pending,pending)

    def setUp(self):
        self.f=BusinessFixture(); self.addCleanup(self.f.close)
        self.f.registration['clients']['synthetic-alpha']['synthetic']=False
        self.f.write_registration()
        self.c=PlatformLearningControl(self.f.context,'chat',project_root=self.f.root)
        self.stamp={'platform_id':'dext','profile':'saccade-dext','config_revision':self.f.context['config_revision'],
                    'session':'owned-browser','tab':'1','page':'current-record'}
        self.elements={'2':{'role':'link','name':'Invoice PDF','line':'<a href="/invoice.pdf">Invoice PDF</a>'},
                       '3':{'role':'heading','name':'Purchases'}}
        download={'type':'download','target_id':2}
        self.c.authorize_execution(download,self.stamp,self.elements)
        self.c.execution.review(self.c.execution.pending['id'],True)
        self.c.authorize_execution(download,self.stamp,self.elements)
        body=b'%PDF-1.4 Synthetic accounting test, no client data'
        receipt=self.c.save_download({'base64':base64.b64encode(body).decode(),'size':len(body),'mime':'application/pdf'})
        self.action={'type':'call_function','version':1,'name':scribe_pdf.NAME,'arguments':
            {'document':'receipt:'+receipt['receipt_id'],'client_id':'synthetic-alpha','sens':'achat'}}
        self.raw=json.dumps(self.f.invoice()['fixture-one']['expected'])

    def request(self):
        decision=self.c.authorize_execution(self.action,self.stamp,self.elements)
        self.assertFalse(decision['allowed'])
        self.c.execution.review(self.c.execution.pending['id'],True)
        self.assertTrue(self.c.authorize_execution(self.action,self.stamp,self.elements)['allowed'])
        return {'version':2,'project_root':str(self.f.root),'context':self.f.context,'session_id':'chat',
                'name':scribe_pdf.NAME,'arguments':self.action['arguments'],
                'revision':catalogue(self.f.root,'dext')['revision'],'authorization':copy.deepcopy(self.c.execution.pending)}

    def test_real_client_full_current_reference_and_actual_multimodal_provider_contract(self):
        reference=self.f.data/'synthetic-alpha/comptable_achats.md'
        text='Synthetic reference start '+('entire history '*1000)+' FINAL CURRENT RULE'
        reference.write_text(text,encoding='utf-8')
        request=self.request()
        fake=types.SimpleNamespace(suppress_debug_info=False)
        fake.completion=unittest.mock.Mock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(
            finish_reason='stop',message=types.SimpleNamespace(content=self.raw))]))
        with patch.dict('sys.modules',{'litellm':fake}), patch.dict('os.environ',{'GEMINI_API_KEY':'synthetic-test-key'}):
            result=execute_worker(request)
        self.assertEqual(result['status'],'success')
        self.assertTrue(result['result']['proposal']['ecriture'])
        self.assertFalse(result['result']['posted_to_dext'])
        self.assertTrue(result['result']['operator_review_required'])
        sent=fake.completion.call_args.kwargs
        self.assertEqual(sent['num_retries'],0)
        self.assertIn(text,sent['messages'][1]['content'][0]['text'])
        self.assertTrue(sent['messages'][1]['content'][1]['file']['file_data'].startswith('data:application/pdf;base64,'))
        self.assertFalse(self.f.registration['clients']['synthetic-alpha']['synthetic'])

    def test_wrong_client_direction_path_page_and_platform_are_rejected_before_provider(self):
        for key,value in [('client_id','synthetic-other'),('sens','vente'),('document','C:/private/invoice.pdf')]:
            action=copy.deepcopy(self.action); action['arguments'][key]=value
            with self.assertRaises((BusinessError,ValueError)):
                self.c.authorize_execution(action,self.stamp,self.elements)
        with self.assertRaises(BusinessError):
            self.c.authorize_execution(self.action,{**self.stamp,'page':'other-record'},self.elements)
        from tests.platform_learning_fixtures import install_synthetic
        other=install_synthetic(self.f.root)
        self.assertNotIn(scribe_pdf.NAME,catalogue(self.f.root,other['platform_id'])['functions'])

    def test_reference_registration_pdf_tampering_invalidates_consent(self):
        for mutation in ('reference','registration','pdf'):
            with self.subTest(mutation=mutation):
                request=self.request()
                if mutation=='reference':
                    path=self.f.data/'synthetic-alpha/comptable_achats.md'; old=path.read_bytes(); path.write_bytes(old+b'changed')
                elif mutation=='registration':
                    path=self.f.data/'registration.json'; old=path.read_bytes()
                    value=json.loads(old); value['active_client']='synthetic-other'; path.write_text(json.dumps(value),encoding='utf-8')
                else:
                    from AutoCua.saccade.capabilities import verified_download
                    receipt=verified_download(self.f.root,self.f.context,'chat',self.action['arguments']['document'])
                    path=Path(receipt['path']); old=path.read_bytes(); path.write_bytes(b'%PDF-CHANGED')
                try:
                    with patch.object(scribe_pdf,'complete') as provider:
                        with self.assertRaises(BusinessError): execute_worker(request)
                        provider.assert_not_called()
                finally:
                    path.write_bytes(old); self.c.execution.pending=None

    def test_specific_identity_and_external_disclosure_approval_not_learning_yes(self):
        self.c.authorize_execution(self.action,self.stamp,self.elements)
        broker=OperatorRequests(); broker.configure_teaching('chat',self.c)
        broker.suspend('chat','run',{'platform_id':'dext','task':'Analyze current document'},
            {'category':'confirmation','reason':'condition_confirmation','request':'Review this disclosure.'})
        broker.present_execution('chat',self.c)
        def answer(text):
            state=broker.status('chat')
            event={k:state[k] for k in ('run_id','intervention_id','revision','token','presentation_digest')}
            return broker.chat('chat',{**event,'action':'chat','answer':text,'non_sensitive':True},control=self.c)
        self.assertEqual(answer('Approve this disclosure')[0],'waiting')
        self.assertEqual(answer('Yes, remember this')[0],'waiting')
        self.assertEqual(answer('Confirm document identity and approve Gemini disclosure')[0],'resume')

    def test_provider_failure_truncation_and_invalid_accounting_never_succeed(self):
        request=self.request()
        for raw in ('{}', self.raw.replace('10000','10001')):
            with patch.object(scribe_pdf,'complete',return_value=raw):
                with self.assertRaises(BusinessError): execute_worker(request)
        with patch.object(scribe_pdf,'complete',side_effect=BusinessError('scribe_provider_failed')):
            from AutoCua.saccade.business_worker import execute
            self.assertEqual(execute(request)['error'],'scribe_provider_failed')
        fake=types.SimpleNamespace(completion=unittest.mock.Mock(side_effect=RuntimeError('PRIVATE')))
        with patch.dict('sys.modules',{'litellm':fake}),patch.dict('os.environ',{'GEMINI_API_KEY':'synthetic'}):
            with self.assertRaisesRegex(BusinessError,'^scribe_provider_failed$'): scribe_pdf.complete([],scribe_pdf.DEFAULT_MODEL)
            fake.completion.side_effect=None
            fake.completion.return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='length')])
            with self.assertRaisesRegex(BusinessError,'scribe_provider_truncated'): scribe_pdf.complete([],scribe_pdf.DEFAULT_MODEL)

    def test_same_conversation_host_runs_existing_worker_with_consumed_grant_and_keeps_result_private(self):
        self.request()
        def worker(request,**options):
            self.assertEqual(request['authorization']['state'],'consumed')
            self.assertEqual(set(options['provider_environment']),{'GEMINI_API_KEY','COMPTABLE_LLM_MODEL'})
            with patch.object(scribe_pdf,'complete',return_value=self.raw): return execute_worker(request)
        with patch('AutoCua.saccade.business_process.run_worker',side_effect=worker),patch.object(scribe_pdf,'credentials',return_value={'GEMINI_API_KEY':'synthetic','COMPTABLE_LLM_MODEL':scribe_pdf.DEFAULT_MODEL}):
            result=self.c.execute_capability(self.action)
        self.assertEqual(result['status'],'success')
        self.assertNotIn('result',result)
        self.assertTrue(self.c.execution.receipts[result['result_receipt']]['proposal']['ecriture'])

    def test_real_child_reports_missing_configuration_without_inheriting_credentials(self):
        from AutoCua.saccade.business_process import run_worker
        request=self.request()
        response=run_worker(request,package_root=Path(scribe_pdf.__file__).parents[1],
            provider_environment={'GEMINI_API_KEY':'','COMPTABLE_LLM_MODEL':scribe_pdf.DEFAULT_MODEL})
        self.assertEqual(response['error'],'scribe_provider_unconfigured')
