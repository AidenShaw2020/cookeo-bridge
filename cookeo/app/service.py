"""Credential rotation, device subscriptions and truthful state projection."""
import asyncio
from dataclasses import dataclass,field
import json
import time
import secrets
from .models import CookeoStatus,CookeoShadow
from .programs import program_name


@dataclass
class DeviceState:
    device:dict
    status:CookeoStatus=field(default_factory=CookeoStatus)
    shadow:CookeoShadow=field(default_factory=CookeoShadow)
    last_event:float|None=None
    source_connected:bool=False
    last_recipe_event:float|None=None

    def receive(self,topic,data):
        if topic.endswith('/cookingStatus'):
            incoming=CookeoStatus.from_json(data)
            if incoming.version is not None and self.status.version is not None and incoming.version<self.status.version:return
            self.status=self.status.merge(incoming)
            if isinstance(data.get('currentRecipe'),dict):self.last_recipe_event=time.time()
            if 'error' in data:self.status.error=data['error']
        elif '/shadow/' in topic:self.shadow=self.shadow.merge(CookeoShadow.from_json(data))
        elif topic.endswith('/alert'):
            self.status.alert_description=str(data.get('description') or data.get('message') or '')[:256]
        self.last_event=time.time()

    def public(self,language='en'):
        current=self.status;phase=current.normalized_status
        online=self.shadow.connected
        active=phase in ('warming','cooking','keep_warm','depressurization','paused','delayed','ready','done','alert')
        return {'connected':online,'source_connected':self.source_connected,'status':phase,
                'mode':current.mode if active else None,'program':program_name(current.program.key,current.program.name,language) if active and current.program else None,
                'program_id':current.display_program_id,'duration':current.display_duration,
                'recipe':current.display_recipe_title,'step':current.display_recipe_step,
                'remaining':current.display_remaining_time,'elapsed':current.elapsed_time if active else None,
                'progress':current.display_progress,'temperature':current.display_target_temperature,
                'firmware':self.shadow.firmware.ui_version or self.shadow.firmware.wifi_version,
                'error':str(current.error)[:256] if current.error else None,'last_event':self.last_event}


class Service:
    def __init__(self,cloud,bridge):
        self.cloud=cloud;self.bridge=bridge;self.states={};self.running=False;self.connection=None
        self.resources=None;self.connected=False;self.last_error=None;self.events=asyncio.Queue(maxsize=500)
        self.wake=asyncio.Event();self.task=None;self.expiration=0
        self.pending_recipe_updates={}

    @property
    def language(self):
        store=getattr(self.cloud,'store',None)
        return store.get('ui_language','en') if store else 'en'

    def start(self):
        self.running=True;self.task=asyncio.create_task(self.loop())

    def changed(self):self.wake.set()

    async def disconnect(self):
        for _,future in self.pending_recipe_updates.values():
            if not future.done():future.set_result({'accepted':False,'code':'disconnected'})
        if self.connection:
            old=self.connection;self.connection=None
            try:await asyncio.to_thread(lambda:old.disconnect().result(timeout=5))
            except Exception:pass
        self.connected=False;self.resources=None
        for state in self.states.values():state.source_connected=False;self.bridge.publish(state.device['id'],state.public(self.language))

    async def connect(self):
        loop=asyncio.get_running_loop()
        def interrupted(**kwargs):loop.call_soon_threadsafe(self.wake.set)
        connection,resources,expiration=await asyncio.to_thread(self.cloud.mqtt_connection,interrupted)
        self.connection=connection;self.resources=resources;self.expiration=expiration
        profile=await asyncio.to_thread(self.cloud.profile)
        devices=self.cloud.devices(profile)
        self.states={d['id']:DeviceState(d) for d in devices};self.bridge.register(devices)
        from awscrt import mqtt
        def callback(**kwargs):
            if kwargs.get('retain') or len(kwargs.get('payload',b''))>65536:return
            try:
                data=json.loads(kwargs['payload'])
                if isinstance(data,dict):loop.call_soon_threadsafe(enqueue,kwargs['topic'],data)
            except (ValueError,KeyError):pass
        def enqueue(topic,data):
            try:self.events.put_nowait((topic,data))
            except asyncio.QueueFull:pass
        for device in devices:
            prefix='$aws/things/'+device['thing_type']+'-'+device['id']+'/shadow'
            topics=[prefix+'/get/accepted',prefix+'/update/accepted',prefix+'/update/rejected',prefix+'/update/documents',
                    device['thing_type']+'/'+device['id']+'/cookingStatus',device['thing_type']+'/'+device['id']+'/alert']
            for topic in topics:
                response=await asyncio.to_thread(lambda t=topic:connection.subscribe(t,mqtt.QoS.AT_LEAST_ONCE,callback)[0].result(timeout=10))
                if response.get('qos') is None:raise RuntimeError('Odběr stavu byl odmítnut.')
            await asyncio.to_thread(lambda p=prefix:connection.publish(p+'/get',payload='{}',qos=mqtt.QoS.AT_MOST_ONCE)[0].result(timeout=10))
            await asyncio.to_thread(lambda d=device:connection.publish(d['thing_type']+'/'+d['id']+'/getCookingStatus',
                payload='{}',qos=mqtt.QoS.AT_LEAST_ONCE)[0].result(timeout=10))
        self.connected=True;self.last_error=None
        for state in self.states.values():state.source_connected=True

    async def loop(self):
        while self.running:
            if not self.cloud.store.get('tokens'):
                await self.disconnect();self.states={};self.bridge.register([])
                self.wake.clear()
                try:await asyncio.wait_for(self.wake.wait(),5)
                except asyncio.TimeoutError:pass
                continue
            try:
                self.wake.clear();await self.connect()
                next_publish=time.monotonic()+30
                while self.running and not self.wake.is_set() and time.time()<self.expiration-300:
                    try:
                        topic,data=await asyncio.wait_for(self.events.get(),1)
                        self.shadow_response(topic,data)
                        for identifier,state in self.states.items():
                            if topic.startswith(state.device['thing_type']+'/'+identifier+'/') or topic.startswith('$aws/things/'+state.device['thing_type']+'-'+identifier+'/'):
                                state.receive(topic,data);self.bridge.publish(identifier,state.public(self.language))
                    except asyncio.TimeoutError:pass
                    if time.monotonic()>=next_publish:
                        for identifier,state in self.states.items():self.bridge.publish(identifier,state.public(self.language))
                        next_publish=time.monotonic()+30
            except asyncio.CancelledError:break
            except Exception as error:
                self.last_error=type(error).__name__
            finally:await self.disconnect()
            if self.running:
                try:await asyncio.wait_for(self.wake.wait(),15 if self.last_error else .1)
                except asyncio.TimeoutError:pass

    async def stop(self):
        self.running=False;self.wake.set()
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
        await self.disconnect()

    def public(self):
        return {'cloud_connected':self.connected,'mqtt_connected':self.bridge.connected,'last_error':self.last_error,
                'devices':[{**s.device,**s.public(self.language)} for s in self.states.values()]}

    def transfer_state(self,device_id,confirm_idle=False):
        state=self.states.get(device_id)
        if not self.connected or not state or not state.shadow.connected:raise ValueError('Hrnec není připojený.')
        if state.status.normalized_status not in ('idle','menu','ready','done') and not (state.status.normalized_status is None and confirm_idle is True):
            raise ValueError('Přenos je povolený až při známém klidovém stavu hrnce. Během vaření se neodesílá.')
        return state

    def shadow_response(self,topic,data):
        pending=self.pending_recipe_updates.get(data.get('clientToken'))
        if not pending:return
        prefix,future=pending
        if topic not in (prefix+'/accepted',prefix+'/rejected') or future.done():return
        future.set_result({'accepted':topic.endswith('/accepted'),'code':data.get('code')})

    async def send_recipe(self,device_id,recipe_id,confirm_idle=False):
        from .cloud import recipe_reference,CloudError
        state=self.transfer_state(device_id,confirm_idle)
        profile=await asyncio.to_thread(self.cloud.profile)
        if not any(d['id']==device_id for d in self.cloud.devices(profile)):raise ValueError('Zařízení nepatří tomuto profilu.')
        group=await asyncio.to_thread(self.cloud.appliance_group,state.device['appliance'])
        recipe=await asyncio.to_thread(self.cloud.recipe,recipe_reference(recipe_id),group)
        if not any(g.get('key')==group for g in recipe.get('applianceGroups',[])):
            raise ValueError('Recept nemá ověřenou kompatibilitu s tímto modelem.')
        top=recipe_reference((recipe.get('groupingId') or {}).get('functionalId'))
        variant=recipe_reference((recipe.get('fid') or {}).get('functionalId'))
        payload={'state':{'desired':{'recipe':{'functionalId':top,'variant':{'functionalId':variant}}}}}
        topic='$aws/things/'+state.device['thing_type']+'-'+device_id+'/shadow/update'
        from awscrt import mqtt
        connection=self.connection
        if not connection:raise ValueError('Cloudové spojení se přerušilo.')
        token=secrets.token_hex(16);payload['clientToken']=token
        future=asyncio.get_running_loop().create_future();self.pending_recipe_updates[token]=(topic,future)
        sent=time.time()
        try:
            await asyncio.to_thread(lambda:connection.publish(topic,payload=json.dumps(payload),qos=mqtt.QoS.AT_LEAST_ONCE)[0].result(timeout=10))
            try:accepted=await asyncio.wait_for(asyncio.shield(future),10)
            except asyncio.TimeoutError:raise CloudError('Cloud nepotvrdil přijetí receptu. Pokus se automaticky neopakuje.') from None
            if not accepted['accepted']:raise CloudError('Cloud odmítl recept (kód '+str(accepted.get('code'))+').')
        finally:
            self.pending_recipe_updates.pop(token,None)
            if not future.done():future.cancel()
        # Publishing is not proof the cooker loaded it. Never automatically retry.
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if state.last_recipe_event and state.last_recipe_event>=sent and state.status.recipe_id in (top,variant):
                return {'published':True,'cloud_accepted':True,'device_confirmed':True}
            await asyncio.sleep(.5)
        return {'published':True,'cloud_accepted':True,'device_confirmed':False}
