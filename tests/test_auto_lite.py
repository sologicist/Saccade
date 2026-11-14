"""Auto Lite uses observed URLs and real temporary PDF bytes, never PR5 state."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from AutoCua.saccade.automatic_platform import detect_platform
from AutoCua.saccade.downloaded_pdf import resolve_download
from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.business_run import BusinessRun
from AutoCua.saccade.business_functions.platforms.dext.runtime import AccountingContext
from tests.business_fixtures import BusinessFixture


class AutoLite(unittest.TestCase):
    def setUp(self):
        import sys
        sdk=Path(__file__).resolve().parents[1]/'.cache/auto-lite-sdk'
        if sdk.is_dir(): sys.path.insert(0,str(sdk))
        try:
            disabled=patch('dotenv.load_dotenv',return_value=False)
            disabled.start();self.addCleanup(disabled.stop)
        except ImportError:
            pass
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)

    def test_exact_installed_host_matching_and_transitions(self):
        root = self.fixture.root
        for url in ('http://app.dext.com','https://app.dext.com.evil.example','https://fake-app.dext.com',
                    'https://other.example/?next=app.dext.com','https://user@app.dext.com','https://app.dext.com:123/'):
            self.assertIsNone(detect_platform(url,root=root),url)
        for url in ('https://app.dext.com/login','https://app.dext.com/receipt','https://app.dext.com/'):
            self.assertEqual(detect_platform(url,root=root),'dext')
        self.assertIsNone(detect_platform('https://example.com',root=root))

    def test_lookup_unicode_exact_collision_name_and_real_bytes(self):
        root=self.fixture.root
        since=time.time_ns()
        path=root/'Facture été (1).pdf'
        content=b'%PDF-1.4\nSynthetic real bytes\n%%EOF'
        path.write_bytes(content)
        self.assertEqual(resolve_download(path.name,folder=root,since_ns=since),(str(path),content))
        self.assertEqual(resolve_download(str(path),folder=root,since_ns=since),(str(path),content))
        for value in ('../invoice.pdf','sub/invoice.pdf','sub\\invoice.pdf','file.pdf:secret','https://example.com/file.pdf'):
            with self.assertRaises(BusinessError): resolve_download(value,folder=root,since_ns=since)
        with self.assertRaisesRegex(BusinessError,'download_stale'):
            resolve_download(path.name,folder=root,since_ns=time.time_ns()+1_000_000_000)
        path.with_name(path.name+'.crdownload').write_bytes(b'partial')
        with self.assertRaisesRegex(BusinessError,'download_incomplete'): resolve_download(path.name,folder=root)

    def test_another_installed_platform_is_detected_without_dext_function_access(self):
        from AutoCua.saccade.automatic_platform import business_for_platform
        f=self.fixture
        domain=f.root/'AutoCua/default_skills/web/domain_skill'
        (domain/'other.md').write_text('Other synthetic platform instructions.',encoding='utf8')
        (domain/'skills.json').write_text(json.dumps({'app.dext.com':'dext.md','other.example':'other.md'}),encoding='utf8')
        platform=f.root/'platforms/other';platform.mkdir()
        config=json.loads((f.root/'platforms/dext/platform.json').read_text())
        config.update(id='other',name='Other',start_url='https://other.example/',allowed_hosts=['other.example'])
        (platform/'platform.json').write_text(json.dumps(config),encoding='utf8')
        self.assertEqual(detect_platform('https://other.example/path',root=f.root),'other')
        self.assertEqual(detect_platform('https://app.dext.com/path',root=f.root),'dext')
        self.assertIsNone(business_for_platform('other'))

    def test_missing_invalid_partial_and_foreign_paths_are_rejected(self):
        root=self.fixture.root
        with self.assertRaisesRegex(BusinessError,'download_file_missing'): resolve_download('missing.pdf',folder=root)
        for content in (b'not PDF',b'%PDF-1.4 incomplete'):
            (root/'bad.pdf').write_bytes(content)
            with self.assertRaisesRegex(BusinessError,'invalid_download_pdf'): resolve_download('bad.pdf',folder=root)
        with self.assertRaisesRegex(BusinessError,'download_outside_folder'):
            resolve_download(str(root.parent/'foreign.pdf'),folder=root)

    def test_production_scribe_reads_actual_download_and_full_correct_reference(self):
        f=self.fixture
        f.registration['clients']['synthetic-alpha']['synthetic']=False
        f.write_registration()
        since=time.time_ns()
        path=f.root/'invoice (1).pdf'
        content=b'%PDF-1.4\nActual temporary document\n%%EOF'
        path.write_bytes(content)
        reference=f.data/'synthetic-alpha/comptable_achats.md'
        reference.write_text('Full purchase reference '+ 'history '*3000+' FINAL RULE',encoding='utf8')
        run=BusinessRun(f.context,project_root=f.root,automatic=True,downloads_dir=f.root,download_since_ns=since)
        run.refresh()
        action={'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}}
        ticket=run.prepare(action)
        self.assertEqual(ticket['arguments']['pdf'],str(path))
        self.assertEqual(ticket['effect'],'disclosure')
        raw=f.invoice()['fixture-one']['expected']
        class Provider:
            def scribe(self,pdf,markdown,description,expected):
                self.content,self.markdown=pdf,markdown
                return raw
        provider=Provider()
        context=AccountingContext(f.data,{'synthetic-alpha':{'synthetic':False}},automatic=True,downloads_dir=f.root,provider=provider)
        result=context.scribe(str(path),'synthetic-alpha','achat')
        self.assertTrue(result['ecriture'])
        self.assertEqual(provider.content,content)
        self.assertEqual(provider.markdown,reference.read_text())
        with self.assertRaisesRegex(BusinessError,'unauthorized_client'):
            run.prepare({**action,'arguments':{**action['arguments'],'client_id':'synthetic-other'}})
        with self.assertRaisesRegex(BusinessError,'invalid_invoice_direction'):
            context.scribe(str(path),'synthetic-alpha','banque')
        with patch('AutoCua.saccade.accounting_provider.settings',side_effect=BusinessError('accounting_provider_key_missing')):
            self.assertEqual(run.execute(ticket)['code'],'accounting_provider_key_missing')

    def test_provider_failure_is_explicit(self):
        from AutoCua.saccade.accounting_provider import GeminiAccountingProvider
        with patch.dict('os.environ',{'GOOGLE_API_KEY':''}):
            with self.assertRaisesRegex(BusinessError,'accounting_provider_key_missing'):
                GeminiAccountingProvider().complete([], '')

    def test_existing_google_loader_and_selected_model_are_reused_without_extra_settings(self):
        from AutoCua.saccade.accounting_provider import settings
        from AutoCua.llm_provider import llm_manager
        with patch.object(llm_manager,'_key',return_value='existing-app-key') as loader:
            model, environment=settings('gemini-3.8-flash','runtime-google-key')
        self.assertEqual(model,'gemini-3.8-flash')
        self.assertEqual(environment,{'GOOGLE_API_KEY':'existing-app-key'})
        loader.assert_called_once_with('runtime-google-key','GOOGLE_API_KEY')
        run=BusinessRun(self.fixture.context,project_root=self.fixture.root)
        run.set_google_runtime('google',model,'runtime-google-key')
        self.assertNotIn('runtime-google-key',json.dumps(run.refresh()))
        run.set_google_runtime('openai','unrelated-model','not-a-google-key')
        self.assertIsNone(run._google_key)
        self.assertIsNone(run._google_model)

    def test_existing_saved_google_selection_is_used_when_no_runtime_selection_is_supplied(self):
        from AutoCua.saccade.accounting_provider import settings
        from AutoCua.agent_conversation.service import conversation
        from AutoCua.llm_provider import llm_manager
        (self.fixture.root/'settings.json').write_text(json.dumps({'provider':'google','model':'gemini-3.6-flash'}),encoding='utf8')
        with patch.object(conversation,'root',return_value=self.fixture.root),patch.object(llm_manager,'_key',return_value='existing-app-key'):
            self.assertEqual(settings()[0],'gemini-3.6-flash')

    def test_existing_saved_google_key_is_loaded_by_the_shared_loader(self):
        from AutoCua.saccade.accounting_provider import settings
        key_file=self.fixture.root/'synthetic-api-key.txt'
        key_file.write_text('GOOGLE_API_KEY=synthetic-existing-settings-key\nOPENAI_API_KEY=unrelated\n',encoding='utf8')
        with patch('AutoCua.api_key_file',return_value=key_file),patch.dict('os.environ',{'GOOGLE_API_KEY':''}):
            self.assertEqual(settings('gemini-3.8-flash'),('gemini-3.8-flash',{'GOOGLE_API_KEY':'synthetic-existing-settings-key'}))

    def test_unknown_models_are_rejected_and_invalid_saved_settings_use_existing_default(self):
        from AutoCua.saccade.accounting_provider import settings
        from AutoCua.llm_provider.google.view import MODEL_MAPPINGS
        from AutoCua.agent_conversation.service import conversation
        with self.assertRaisesRegex(BusinessError,'accounting_model_unavailable'):
            settings('model-supplied-unregistered-name','synthetic-key')
        (self.fixture.root/'settings.json').write_text('[]',encoding='utf8')
        with patch.object(conversation,'root',return_value=self.fixture.root):
            self.assertEqual(settings(api_key='synthetic-key')[0],next(iter(MODEL_MAPPINGS)))

    def test_windows_known_download_folder_is_resolved_without_reading_customer_files(self):
        import os
        if os.name != 'nt': self.skipTest('Windows Known Folder API')
        from AutoCua.saccade.downloaded_pdf import downloads_folder
        with patch.dict('os.environ',{},clear=False):
            configured=os.environ.pop('SACCADE_DOWNLOADS_DIR',None)
            try:
                self.assertTrue(downloads_folder().is_absolute())
            finally:
                if configured is not None: os.environ['SACCADE_DOWNLOADS_DIR']=configured

    def test_verified_chrome_folder_hint_is_host_only_and_rejects_old_files(self):
        f=self.fixture
        run=BusinessRun(f.context,project_root=f.root,automatic=True)
        custom=f.root/'custom Chrome downloads';custom.mkdir()
        path=custom/'Fresh.pdf';path.write_bytes(b'%PDF-1.4 fresh %%EOF')
        run.note_download(str(path))
        self.assertEqual(run.downloads_dir,custom)
        run.refresh()
        path.write_bytes(b'%PDF-1.4 changed %%EOF')
        with self.assertRaisesRegex(BusinessError,'download_file_changed'):
            run.prepare({'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}})
        with self.assertRaisesRegex(BusinessError,'invalid_download_path'):
            run.note_download(path.name)
        with self.assertRaisesRegex(BusinessError,'download_file_changed'):
            run.prepare({'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}})
        run.begin_download(time.time_ns()+1_000_000_000)
        with self.assertRaisesRegex(BusinessError,'download_stale'):
            run.note_download(str(path))

    def test_production_worker_rejects_file_changed_after_host_preparation(self):
        from AutoCua.saccade.business_worker import execute
        f=self.fixture;since=time.time_ns()
        path=f.root/'Target.pdf';path.write_bytes(b'%PDF-1.4 original %%EOF')
        run=BusinessRun(f.context,project_root=f.root,automatic=True,downloads_dir=f.root,download_since_ns=since)
        run.refresh()
        action={'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}}
        ticket=run.prepare(action)
        def worker(request,**options):
            path.write_bytes(b'%PDF-1.4 changed %%EOF')
            return execute(request)
        run.set_google_runtime('google','gemini-4-argon','synthetic-not-a-key')
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'synthetic-not-a-key'}),patch('AutoCua.saccade.business_process.run_worker',side_effect=worker):
            self.assertEqual(run.execute(ticket)['code'],'download_file_changed')

    def test_real_windows_child_reads_pdf_and_validates_a_stubbed_sdk_proposal(self):
        f=self.fixture
        f.registration['clients']['synthetic-alpha']['synthetic']=False
        f.write_registration()
        since=time.time_ns()
        path=f.root/'Facture école 東京 (1).pdf';content=b'%PDF-1.4 synthetic child document %%EOF'
        path.write_bytes(content)
        proposal=f.invoice()['fixture-one']['expected']
        proposal['piece']['tiers']='Société École 東京'
        raw=json.dumps(proposal)
        # A disposable installed dependency stub, not a production provider
        # hook. The real isolated process/worker/context/validator all execute.
        google=f.package.parent/'google';(google/'genai').mkdir(parents=True)
        (google/'__init__.py').write_text('',encoding='utf8')
        (google/'genai/types.py').write_text('''class HttpOptions:
    def __init__(self,**kwargs): pass
class GenerateContentConfig:
    def __init__(self,**kwargs): pass
class Part:
    @staticmethod
    def from_bytes(**kwargs): return kwargs
''',encoding='utf8')
        stub='''from types import SimpleNamespace as NS
import os
assert os.environ['PYTHON_DOTENV_DISABLED'] == '1'
assert 'OPENAI_API_KEY' not in os.environ
class Client:
    def __init__(self,**kwargs):
        assert kwargs['api_key'] == 'synthetic-not-a-key'
        self.models=self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def generate_content(self,**kwargs):
        assert kwargs['contents'][1]['data'] == CONTENT
        assert kwargs['contents'][0] == REFERENCE
        return NS(candidates=[NS(finish_reason='STOP')],text=RESPONSE)
'''.replace('CONTENT',repr(content)).replace('REFERENCE',repr((f.data/'synthetic-alpha/comptable_achats.md').read_bytes().decode('utf8'))).replace('RESPONSE',repr(raw))
        (google/'genai/__init__.py').write_text(stub,encoding='utf8')
        shared=f.package/'llm_provider';shared.mkdir()
        (shared/'__init__.py').write_text('',encoding='utf8')
        (shared/'google').mkdir()
        (shared/'google/__init__.py').write_text('',encoding='utf8')
        (shared/'google/view.py').write_text("MODEL_MAPPINGS={'gemini-4-argon':{'api_name':'gemini-4-argon'}}",encoding='utf8')
        (shared/'llm_manager.py').write_text("from types import SimpleNamespace\nfrom google.genai import Client\ndef build_provider(*args,**kwargs): return SimpleNamespace(client=Client(api_key=kwargs['api_key']))\n",encoding='utf8')
        run=BusinessRun(f.context,project_root=f.root,package_root=f.package,automatic=True,downloads_dir=f.root,download_since_ns=since)
        run.refresh()
        action={'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}}
        ticket=run.prepare(action)
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'synthetic-not-a-key'}),patch('AutoCua.saccade.accounting_provider.settings',return_value=('gemini-4-argon',{'GOOGLE_API_KEY':'synthetic-not-a-key'})):
            result=run.execute(ticket)
        self.assertEqual(result['status'],'success',result)
        self.assertTrue(result['result']['ecriture'])
        self.assertEqual(result['result']['fournisseur'],'Société École 東京')
        # A frozen launcher uses this same worker with an explicitly configured
        # trusted Python runtime, never the frozen application binary or PATH.
        import sys
        frozen=BusinessRun(f.context,project_root=f.root,package_root=f.package,automatic=True,downloads_dir=f.root,download_since_ns=since)
        frozen.refresh();ticket=frozen.prepare(action)
        with patch('AutoCua.IS_COMPILED',True),patch.dict('os.environ',{'SACCADE_WORKER_PYTHON':sys.executable}),patch('AutoCua.saccade.accounting_provider.settings',return_value=('gemini-4-argon',{'GOOGLE_API_KEY':'synthetic-not-a-key'})):
            result=frozen.execute(ticket)
        self.assertEqual(result['status'],'success',result)

    def test_real_sdk_pdf_envelope_and_worker_validation_without_network(self):
        import sys
        import types as objects
        sdk=Path(__file__).resolve().parents[1]/'.cache/auto-lite-sdk'
        if sdk.is_dir(): sys.path.insert(0,str(sdk))
        try:
            from google import genai
        except ImportError:
            self.skipTest('Google GenAI SDK is not installed in this test interpreter')
        from AutoCua.saccade.business_worker import execute
        f=self.fixture
        since=time.time_ns()
        path=f.root/'Invoice.pdf'; content=b'%PDF-1.4 Actual fixture bytes %%EOF'
        path.write_bytes(content)
        run=BusinessRun(f.context,project_root=f.root,automatic=True,downloads_dir=f.root,download_since_ns=since)
        run.refresh()
        action={'type':'call_function','version':1,'name':'dext.scribe','arguments':{'pdf':path.name,'client_id':'synthetic-alpha','sens':'achat'}}
        ticket=run.prepare(action)
        captured={}
        raw=json.dumps(f.invoice()['fixture-one']['expected'])
        class Client:
            def __init__(self,**options): self.models=self; captured['options']=options
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def generate_content(self,**options):
                captured.update(options)
                return objects.SimpleNamespace(candidates=[objects.SimpleNamespace(finish_reason='STOP')],text=raw)
        def worker(request,**options):
            self.assertEqual(options['timeout'],100)
            self.assertIn('GOOGLE_API_KEY',options['provider_environment'])
            self.assertNotIn('synthetic-not-a-key',json.dumps(request))
            with patch.dict('os.environ',options['provider_environment']):
                return execute(request)
        run.set_google_runtime('google','gemini-4-argon','synthetic-not-a-key')
        with patch.dict('os.environ',{'GOOGLE_API_KEY':''}),patch.object(genai,'Client',Client),patch('AutoCua.saccade.business_process.run_worker',side_effect=worker):
            result=run.execute(ticket)
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(captured['contents'][1].inline_data.data,content)
        self.assertEqual(json.loads(captured['contents'][2]),{'client_id':'synthetic-alpha','sens':'achat'})
        self.assertEqual(captured['contents'][0],(f.data/'synthetic-alpha/comptable_achats.md').read_bytes().decode('utf-8-sig'))
        self.assertEqual(captured['config'].response_mime_type,'application/json')
        self.assertEqual(captured['model'],'gemini-4-argon')
        self.assertEqual(captured['options']['api_key'],'synthetic-not-a-key')
        self.assertNotIn('posted',result)
        from AutoCua.saccade.accounting_provider import GeminiAccountingProvider
        run.set_google_runtime('google','gemini-4-argon','synthetic-not-a-key')
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'synthetic-not-a-key'}),patch.object(genai,'Client',Client),patch.object(Client,'generate_content',side_effect=RuntimeError('PRIVATE provider failure')):
            with self.assertRaisesRegex(BusinessError,'^accounting_provider_failed$'):
                GeminiAccountingProvider('gemini-4-argon').complete([], '')
