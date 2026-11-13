"""Actual broker/worker/store contracts on three separate synthetic installs."""
import base64
import json
import unittest

from AutoCua.saccade.business_contract import BusinessError, digest
from AutoCua.saccade.capabilities import catalogue
from AutoCua.saccade.operator_requests import OperatorRequests
from AutoCua.saccade.platform_learning import PlatformLearningControl
from tests.business_fixtures import BusinessFixture
from tests.platform_learning_fixtures import install_synthetic


class UniversalExecutionContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.contexts = []
        for i in range(3):
            platform = 'execution_' + str(i)
            context = install_synthetic(self.fixture.root, platform_id=platform,
                host=f'portal-{i}.example.test', landmarks=[{'id':'section','label':f'Section {i}','aliases':[]}])
            root = self.fixture.root / 'platforms' / platform
            (root / 'functions').mkdir()
            data = root / 'data'
            data.mkdir()
            (data / 'private.txt').write_text('SYNTHETIC', encoding='utf-8')
            owned = (data / 'private.txt').as_posix()
            if i == 0:
                source = 'def transform(text: str) -> str:\n    return "PLATFORM-0:" + text.upper()\n'
            elif i == 1:
                source = f'def transform(text: str) -> str:\n    with open({owned!r}, encoding="utf-8") as data:\n        return "PLATFORM-1:" + data.read()\n'
            else:
                source = f'def transform(text: str) -> str:\n    result = "PLATFORM-2:" + text.upper()\n    with open({owned!r}, "w", encoding="utf-8") as data:\n        data.write(result)\n    return result\n\ndef verify(result: str) -> bool:\n    with open({owned!r}, encoding="utf-8") as data:\n        return data.read() == result\n'
            (root / 'functions/tool.py').write_text(source, encoding='utf-8')
            effect = ('compute','read','mutation')[i]
            entry = {'id':platform + '.transform','source':'tool.py','symbol':'transform','effect':effect,
                'destination':'local platform implementation','description':'Synthetic local transform', 'output_visibility':'public' if i == 0 else 'operator'}
            if i == 2: entry['verify'] = 'verify'
            (root / 'capabilities.json').write_text(json.dumps({'schema_version':1,'platform_id':platform,'functions':[entry]}), encoding='utf-8')
            (root / 'execution.json').write_text(json.dumps({'schema_version':1,'navigation':[{'name':f'Section {i}','role':'link'}] if i != 1 else []}), encoding='utf-8')
            self.contexts.append(context)

    def control(self, i, session='chat'):
        return PlatformLearningControl(self.contexts[i], session, project_root=self.fixture.root)

    def stamp(self, i, **changes):
        context = self.contexts[i]
        return {'platform_id':context['platform_id'],'profile':context['browser_profile'],
            'config_revision':context['config_revision'],'tab':'1','observer':'generation','session':f'browser-{i}', **changes}

    def event(self, broker, text):
        item = broker.status('chat')
        return {**{k:item[k] for k in ('run_id','intervention_id','revision','token')},
            'action':'chat','answer':text,'non_sensitive':True,'presentation_digest':item.get('presentation_digest')}

    def approval(self, broker, control, action, elements, i):
        self.assertFalse(control.authorize_execution(action, self.stamp(i), elements)['allowed'])
        broker.suspend('chat', 'run', {'platform_id':control.context['platform_id'],'task':'Original synthetic task'},
            {'category':'confirmation','reason':'condition_confirmation','request':'May I execute this exact action?'})
        broker.present_execution('chat', control)
        phrase = broker.status('chat')['execution_phrase']
        self.assertEqual(broker.chat('chat', self.event(broker, 'Yes, remember this'), control=control)[0], 'waiting')
        event = self.event(broker, phrase)
        self.assertEqual(broker.chat('chat', event, control=control)[0], 'resume')
        with self.assertRaises(BusinessError): broker.chat('chat', event, control=control)
        resumed = self.control(i)
        broker.configure_teaching('chat', resumed)
        self.assertIs(resumed.execution, control.execution)
        self.assertTrue(resumed.authorize_execution(action, self.stamp(i, observer='fresh-generation'), elements)['allowed'])
        return resumed

    def test_three_platform_actual_worker_execution_exact_approval_and_learning(self):
        for i in range(3):
            with self.subTest(platform=i):
                control, broker = self.control(i), OperatorRequests()
                broker.configure_teaching('chat', control)
                action = {'type':'call_function','version':1,'name':self.contexts[i]['platform_id'] + '.transform','arguments':{'text':'synthetic'}}
                resumed = self.approval(broker, control, action, {}, i)
                result = resumed.execute_capability(action)
                self.assertEqual(result['status'], 'success')
                if i == 0: self.assertEqual(result['result'], f'PLATFORM-{i}:SYNTHETIC')
                else:
                    self.assertNotIn('result', result)
                    self.assertEqual(resumed.execution.receipts[result['result_receipt']], f'PLATFORM-{i}:SYNTHETIC')
                with self.assertRaises(BusinessError): resumed.authorize_execution(action, self.stamp(i), {})
                proposal = resumed.store.propose_steps(resumed.store.adapter.steps(['section']), resumed.run_id)
                resumed.store.review(proposal['proposal_id'],proposal['base_revision'],proposal['candidate_revision'],True)
                self.assertEqual(resumed.overlay(), '')
                self.assertIn(f'Section {i}', self.control(i,'future').overlay())

    def test_target_approval_does_not_cross_platform_browser_or_target(self):
        control = self.control(0)
        action = {'type':'click','id':1,'times':1}
        target = {'1':{'name':'Unclassified control','role':'button','line':'<button>Unclassified control</button>'}}
        control.authorize_execution(action,self.stamp(0),target)
        control.execution.review(control.execution.pending['id'],True)
        with self.assertRaises(BusinessError): control.authorize_execution(action,self.stamp(1),target)
        self.assertFalse(control.authorize_execution(action,self.stamp(0,session='replacement'),target)['allowed'])
        self.assertFalse(control.authorize_execution(action,self.stamp(0),{'1':{**target['1'],'name':'Different'}})['allowed'])
        other = self.control(1)
        self.assertFalse(other.authorize_execution(action,self.stamp(1),target)['allowed'])

    def test_registered_navigation_policy_is_not_learned_authority(self):
        action = {'type':'click','id':1,'times':1}
        for i in range(3):
            target = {'1':{'name':f'Section {i}','role':'link','line':'<a>Section</a>'}}
            self.assertEqual(self.control(i).authorize_execution(action,self.stamp(i),target)['allowed'], i != 1)
            if i != 1:
                self.assertFalse(self.control(i).authorize_execution(action,self.stamp(i),{**target,'2':target['1']})['allowed'])
                self.assertFalse(self.control(i).authorize_execution({**action,'times':2},self.stamp(i),target)['allowed'])
        control = self.control(1)
        p = control.store.propose_steps(control.store.adapter.steps(['section']),control.run_id)
        control.store.review(p['proposal_id'],p['base_revision'],p['candidate_revision'],True)
        self.assertFalse(control.authorize_execution(action,self.stamp(1),{'1':{'name':'Section 1','role':'link'}})['allowed'])

    def test_explicit_download_approval_produces_checked_private_receipt_not_business_identity(self):
        for i in range(3):
            control, broker = self.control(i), OperatorRequests()
            broker.configure_teaching('chat',control)
            action = {'type':'download','target_id':1}
            elements = {'1':{'name':'Synthetic PDF','role':'link','tag':'a','line':'<a href="/synthetic.pdf">Synthetic PDF</a>'}}
            with self.assertRaises(BusinessError): control.save_download({})
            resumed = self.approval(broker,control,action,elements,i)
            body = b'%PDF-1.4\nSynthetic isolated fixture\n%%EOF'
            result = resumed.save_download({'base64':base64.b64encode(body).decode(),'size':len(body),'mime':'application/pdf'})
            self.assertEqual(result['sha256'],digest(body))
            self.assertFalse(result['record_identity_verified'])
            receipt = resumed.execution.receipts[result['receipt_id']]
            self.assertEqual(__import__('pathlib').Path(receipt['path']).read_bytes(),body)
            self.assertIn(self.contexts[i]['platform_id'],receipt['path'])
            self.assertNotIn(self.contexts[(i+1)%3]['platform_id'],receipt['path'])
            with self.assertRaises(BusinessError): resumed.authorize_execution(action,self.stamp(i),elements)

    def test_foreign_function_unknown_arguments_and_revision_changes_fail_before_execution(self):
        control = self.control(0)
        self.assertTrue(control.authorize_execution({'type':'call_function','name':self.contexts[1]['platform_id']+'.transform','arguments':{}},self.stamp(0),{})['unavailable'])
        action={'type':'call_function','version':1,'name':self.contexts[0]['platform_id']+'.transform','arguments':{'text':'x','path':'private-other-platform'}}
        with self.assertRaises(BusinessError): control.authorize_execution(action,self.stamp(0),{})
        action['arguments']={'text':'x'}
        control.authorize_execution(action,self.stamp(0),{})
        control.execution.review(control.execution.pending['id'],True)
        path=self.fixture.root/'platforms'/self.contexts[0]['platform_id']/'functions/tool.py'
        path.write_text('def transform(text: str) -> str:\n    return "CHANGED"\n',encoding='utf-8')
        self.assertFalse(control.authorize_execution(action,self.stamp(0),{})['allowed'])
        with self.assertRaises(BusinessError): control.execute_capability(action)

    def test_bad_download_and_expired_approval_do_not_claim_success(self):
        control=self.control(0)
        action={'type':'download','target_id':1}
        elements={'1':{'name':'Document','role':'link'}}
        control.authorize_execution(action,self.stamp(0),elements)
        control.execution.pending['expires']=0
        with self.assertRaises(BusinessError): control.execution.review(control.execution.pending['id'],True)
        control.authorize_execution(action,self.stamp(0),elements)
        control.execution.review(control.execution.pending['id'],True)
        control.authorize_execution(action,self.stamp(0),elements)
        with self.assertRaises(BusinessError): control.save_download({'base64':'bm90LXBkZg==','size':7,'mime':'application/pdf'})

    def test_private_state_and_legacy_registration_are_not_merged_or_modified(self):
        before = (self.fixture.data / 'registration.json').read_bytes()
        control, broker = self.control(2), OperatorRequests()
        broker.configure_teaching('chat',control)
        action = {'type':'call_function','version':1,'name':self.contexts[2]['platform_id']+'.transform','arguments':{'text':'changed'}}
        control = self.approval(broker,control,action,{},2)
        self.assertEqual(control.execute_capability(action)['status'],'success')
        self.assertEqual((self.fixture.data / 'registration.json').read_bytes(),before)
        for i in (0,1):
            path=self.fixture.root/'platforms'/self.contexts[i]['platform_id']/'data/private.txt'
            self.assertEqual(path.read_text(encoding='utf-8'),'SYNTHETIC')

    def test_document_function_only_receives_its_own_verified_download(self):
        control, broker = self.control(0), OperatorRequests()
        broker.configure_teaching('chat',control)
        action={'type':'download','target_id':1}
        elements={'1':{'name':'Document','role':'link','line':'<a href="/document.pdf">Document</a>'}}
        control=self.approval(broker,control,action,elements,0)
        body=b'%PDF-1.4\nSynthetic\n'
        result=control.save_download({'base64':base64.b64encode(body).decode(),'size':len(body),'mime':'application/pdf'})
        reference='receipt:'+result['receipt_id']
        root=self.fixture.root/'platforms'/self.contexts[0]['platform_id']
        registry=json.loads((root/'capabilities.json').read_text(encoding='utf-8'))
        registry['functions'].append({'id':self.contexts[0]['platform_id']+'.document','source':'document.py','symbol':'inspect_document',
            'effect':'compute','destination':'local document inspection','description':'Inspect the exact downloaded synthetic PDF',
            'output_visibility':'operator','document_input':'document'})
        (root/'functions/document.py').write_text('def inspect_document(document: str) -> str:\n    with open(document, "rb") as data:\n        return "PDF" if data.read(5) == b"%PDF-" else "OTHER"\n',encoding='utf-8')
        (root/'capabilities.json').write_text(json.dumps(registry),encoding='utf-8')
        action={'type':'call_function','version':1,'name':self.contexts[0]['platform_id']+'.document','arguments':{'document':reference}}
        broker.suspend('chat','next-run',{'platform_id':self.contexts[0]['platform_id'],'task':'Inspect this exact document'},
            {'category':'confirmation','reason':'condition_confirmation','request':'May I inspect this document?'})
        self.assertFalse(control.authorize_execution(action,self.stamp(0),{})['allowed'])
        broker.present_execution('chat',control)
        broker.chat('chat',self.event(broker,'Approve this action'),control=control)
        self.assertTrue(control.authorize_execution(action,self.stamp(0),{})['allowed'])
        inspected=control.execute_capability(action)
        self.assertEqual(inspected['status'],'success')
        self.assertEqual(control.execution.receipts[inspected['result_receipt']],'PDF')
        registry['functions'][-1]['requires_verified_record']=True
        (root/'capabilities.json').write_text(json.dumps(registry),encoding='utf-8')
        with self.assertRaisesRegex(BusinessError,'verified_record_identity_required'):
            control.authorize_execution(action,self.stamp(0),{})
        from AutoCua.saccade.capabilities import verified_download
        with self.assertRaises(BusinessError): verified_download(self.fixture.root,self.contexts[1],'chat',reference)
        with self.assertRaises(BusinessError): verified_download(self.fixture.root,self.contexts[0],'other-chat',reference)
        path=__import__('pathlib').Path(control.execution.receipts[result['receipt_id']]['path'])
        path.write_bytes(b'changed')
        with self.assertRaises(BusinessError): verified_download(self.fixture.root,self.contexts[0],'chat',reference)

    def test_registry_cannot_override_legacy_function_or_escape_its_platform(self):
        root=self.fixture.root/'platforms/dext'
        (root/'capabilities.json').write_text(json.dumps({'schema_version':1,'platform_id':'dext','functions':[
            {'id':'dext.bank','source':'tool.py','symbol':'transform','effect':'compute','destination':'local',
             'description':'Forbidden replacement','output_visibility':'public'}]}),encoding='utf-8')
        with self.assertRaisesRegex(BusinessError,'legacy_capability_override_denied'): catalogue(self.fixture.root,'dext')
        root=self.fixture.root/'platforms'/self.contexts[0]['platform_id']
        value=json.loads((root/'capabilities.json').read_text(encoding='utf-8'))
        value['functions'][0]['source']='../execution_1/functions/tool.py'
        (root/'capabilities.json').write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaises(BusinessError): catalogue(self.fixture.root,self.contexts[0]['platform_id'])

    def test_expired_chat_decision_requires_reobservation_and_new_approval(self):
        control, broker = self.control(0), OperatorRequests()
        broker.configure_teaching('chat',control)
        action={'type':'click','id':2,'times':1}
        elements={'2':{'name':'Unclassified control','role':'button'}}
        control.authorize_execution(action,self.stamp(0),elements)
        broker.suspend('chat','run',{'platform_id':control.context['platform_id'],'task':'Original task'},
            {'category':'confirmation','reason':'condition_confirmation','request':'Review the exact operation.'})
        broker.present_execution('chat',control)
        old=control.execution.pending['id']
        control.execution.pending['expires']=0
        self.assertEqual(broker.chat('chat',self.event(broker,'Approve this interaction'),control=control),('waiting',None))
        self.assertNotIn('execution_summary',broker.status('chat'))
        kind,data=broker.chat('chat',self.event(broker,'Continue'),control=control)
        self.assertEqual(kind,'resume')
        self.assertIn('Original task',data['task'])
        self.assertFalse(control.authorize_execution(action,self.stamp(0),elements)['allowed'])
        self.assertNotEqual(control.execution.pending['id'],old)

    def test_action_presentation_tampering_does_not_grant_authority(self):
        control,broker=self.control(0),OperatorRequests()
        broker.configure_teaching('chat',control)
        action={'type':'click','id':2,'times':1}
        control.authorize_execution(action,self.stamp(0),{'2':{'name':'Unclassified control','role':'button'}})
        broker.suspend('chat','run',{'platform_id':control.context['platform_id'],'task':'Original task'},
            {'category':'confirmation','reason':'condition_confirmation','request':'Review the exact action.'})
        broker.present_execution('chat',control)
        broker.pending['chat']['execution_summary']='Altered presentation'
        with self.assertRaisesRegex(BusinessError,'stale_execution_presentation'):
            broker.chat('chat',self.event(broker,'Approve this interaction'),control=control)
        self.assertEqual(control.execution.pending['state'],'pending')

    def test_page_focus_policy_and_dependency_boundaries_fail_closed(self):
        control=self.control(0)
        for value in ('ctrl+l','ctrl+shift+j','alt+f4','ctrl+o'):
            self.assertFalse(control.authorize_execution({'type':'keyboard','value':value},self.stamp(0,focus={'type':'text','digest':'one'}),{})['allowed'])
        for kind in ('password','file'):
            with self.assertRaisesRegex(BusinessError,'private_manual_input_required'):
                control.authorize_execution({'type':'keyboard','value':'enter'},self.stamp(0,focus={'type':kind}),{})
        action={'type':'keyboard','value':'enter'}
        control.authorize_execution(action,self.stamp(0,focus={'type':'text','digest':'one'}),{})
        control.execution.review(control.execution.pending['id'],True)
        self.assertFalse(control.authorize_execution(action,self.stamp(0,focus={'type':'text','digest':'two'}),{})['allowed'])
        root=self.fixture.root/'platforms'/self.contexts[0]['platform_id']
        (root/'execution.json').write_text('{"schema_version":1,"navigation":[]}',encoding='utf-8')
        with self.assertRaisesRegex(BusinessError,'execution_policy_changed'): control.execution.validate()
        (root/'functions/tool.py').write_text('def transform(text: str) -> str:\n    return __import__("os").getcwd()\n',encoding='utf-8')
        with self.assertRaisesRegex(BusinessError,'unsupported_capability_dependency'): catalogue(self.fixture.root,self.contexts[0]['platform_id'])

    def test_operational_back_correction_is_not_reusable_action_authority(self):
        from AutoCua.saccade.operator_language import recovery_correction
        control,broker=self.control(0),OperatorRequests()
        recovery=recovery_correction('Non, reviens en arrière puis ouvre Section 0.',control.store.adapter)
        self.assertEqual(recovery,{'action':'back','routes':['section']})
        broker.configure_teaching('chat',control)
        broker.propose_correction('chat','run',{'platform_id':control.context['platform_id'],'task':'Original task'},
            recovery['routes'],active=True,recovery=recovery)
        broker.suspend('chat','run',broker.pending['chat']['data'],
            {'category':'question','reason':'missing_information','request':'Navigation is paused at a verified checkpoint.'})
        broker.complete_correction_pause('chat','run',available=True,control=control)
        self.assertEqual(broker.chat('chat',self.event(broker,'Continue'),control=control)[0],'resume')
        self.assertIn('browser Back',broker.pending['chat']['data']['task'])
        self.assertIsNone(control.execution.pending)
        self.assertEqual(broker._teaching['chat'].routes,['section'])
        self.assertEqual(broker._teaching['chat'].evidence,[])
        self.assertIsNone(recovery_correction('Go back and export all private data',control.store.adapter))

    def test_merged_tool_keeps_strict_schema_and_legacy_names(self):
        from AutoCua.saccade.capabilities import merge_tools, tool
        old=tool(catalogue(self.fixture.root,self.contexts[0]['platform_id']))
        new=tool(catalogue(self.fixture.root,self.contexts[1]['platform_id']))
        # A legacy field and a generic field must both be declared required
        # (nullable per-function), as strict provider schemas require.
        old['parameters']['properties']['arguments']['properties']['legacy_field']={'type':'null'}
        combined=merge_tools(old,new)
        arguments=combined['parameters']['properties']['arguments']
        self.assertEqual(set(arguments['required']),set(arguments['properties']))
        self.assertEqual(len(combined['parameters']['properties']['name']['enum']),2)

    def test_supervised_grants_do_not_change_auto_permissions(self):
        auto=PlatformLearningControl({**self.contexts[0],'execution_mode':'auto'},'auto-chat',project_root=self.fixture.root)
        self.assertIsNone(auto.execution_tools())
        action={'type':'click','id':2,'times':1}
        self.assertTrue(auto.authorize_execution(action,self.stamp(0),{})['unavailable'])
        with self.assertRaisesRegex(BusinessError,'supervised_execution_required'):
            auto.execution.decide(action,self.stamp(0),{},effect='interaction')

    def test_unverified_effect_is_failed_and_never_published_as_success(self):
        root=self.fixture.root/'platforms'/self.contexts[2]['platform_id']
        path=root/'functions/tool.py'
        source=path.read_text(encoding='utf-8')
        path.write_text(source.replace('return data.read() == result','return False'),encoding='utf-8')
        control,broker=self.control(2),OperatorRequests()
        broker.configure_teaching('chat',control)
        action={'type':'call_function','version':1,'name':self.contexts[2]['platform_id']+'.transform','arguments':{'text':'uncertain'}}
        control=self.approval(broker,control,action,{},2)
        result=control.execute_capability(action)
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['error'],'capability_effect_unverified')
        self.assertEqual(control.execution.pending['state'],'failed')
        self.assertEqual(control.execution.receipts,{})
        with self.assertRaises(BusinessError): control.authorize_execution(action,self.stamp(2),{})

    def test_three_platform_conversational_corrections_require_verified_transitions_and_independent_reviews(self):
        from AutoCua.saccade.operator_language import spontaneous_correction
        for i in range(3):
            with self.subTest(platform=i):
                control,broker=self.control(i),OperatorRequests()
                broker.configure_teaching('chat',control)
                kind,routes=spontaneous_correction(f'No, open Section {i}.',eligible=True,navigation=True,adapter=control.store.adapter)
                self.assertEqual(kind,'correction')
                broker.propose_correction('chat','run',{'platform_id':control.context['platform_id'],'task':'Original task'},routes,active=False)
                broker.complete_correction_pause('chat','run',available=True,control=control)
                self.assertEqual(broker.chat('chat',self.event(broker,'Continue'),control=control)[0],'resume')
                resumed=self.control(i)
                broker.configure_teaching('chat',resumed)
                resumed.freeze_decision()
                source={'2':{'name':f'Section {i}','role':'link','rect':[1,1,50,20]}}
                resumed.observe_native(source,self.stamp(i))
                action={'type':'click','id':2,'times':1}
                decision=resumed.authorize_execution(action,self.stamp(i),source)
                if not decision['allowed']:
                    broker.suspend('chat','click',broker.pending['chat']['data'],
                        {'category':'confirmation','reason':'condition_confirmation','request':'Review this exact click.'})
                    broker.present_execution('chat',resumed)
                    self.assertEqual(broker.chat('chat',self.event(broker,'Approve this interaction'),control=resumed)[0],'resume')
                    self.assertTrue(resumed.authorize_execution(action,self.stamp(i),source)['allowed'])
                self.assertIsNone(resumed.proposal)
                resumed.observe_native({'2':{'name':f'Section {i}','role':'heading','rect':[1,1,50,20]}},self.stamp(i,observer='new-generation'))
                request=resumed.learning_intervention()
                self.assertEqual(request['category'],'confirmation')
                resumed.close()
                broker.suspend('chat','review',{'platform_id':control.context['platform_id'],'task':'Original task'},request)
                broker.present_procedure('chat',resumed)
                self.assertIn(f'Section {i}',broker.status('chat')['procedure_summary'])
                self.assertEqual(broker.chat('chat',self.event(broker,'Yes, remember this'),control=resumed)[0],'resume')
                self.assertEqual(resumed.overlay(),'')
                future=self.control(i,'future')
                self.assertIn(f'Section {i}',future.overlay())
                for other in range(3):
                    if other != i: self.assertNotIn(f'Section {other}',future.overlay())
