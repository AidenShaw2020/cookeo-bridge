"""Single-shot original ready/COMPLETED/finalize with explicit local approval."""
import asyncio
import json
import time
from .ble import provision
from .cloud import APPS


def prepare(cloud,profile):
    if cloud.devices(profile):raise ValueError('V tomto profilu už je připojený Cookeo. Nové párování se nespustí.')
    account=profile['rcu']['rcuAccountId'];tokens=cloud.tokens();selection=cloud.selection()
    products=[p for p in (profile.get('household') or {}).get('products') or [] if p.get('appliance')=='APPLIANCE_1232']
    if len(products)>1:raise ValueError('V profilu je více záznamů stejného modelu.')
    body={'deviceCode':account,'openIdToken':tokens['id_token'],'accessToken':tokens['access_token'],
          'apiKey':APPS[selection['brand']]['api_key'],'market':'GS_'+selection['market'],'lang':selection['lang'],
          'appliance':'APPLIANCE_1232','name':'Cookeo Infinity Autostir'}
    if products:
        product=products[0];identifier=product.get('identifier') or {}
        if str(product.get('cmmf') or '7211419888')!='7211419888' or identifier.get('sourceSystem')!='PRO':
            raise ValueError('Neověřený existující produkt.')
        from .cloud import safe_id
        body['identifier']={'functionalId':safe_id(identifier.get('functionalId')),'sourceSystem':'PRO'}
        body['name']=str(product.get('name') or body['name'])[:256]
    return account+'/COO002/'+account+'/deviceAuthFlow/',body


class Pairing:
    def __init__(self,cloud,on_done):
        self.cloud=cloud;self.on_done=on_done;self.task=None;self.approved=asyncio.Event();self.cancelled=asyncio.Event()
        self.state={'phase':'idle','message':'Párování není spuštěné.'};self.page_available=False

    def public(self):return {**self.state,'page_available':self.page_available}

    def progress(self,message,phase=None):
        if phase:self.state['phase']=phase
        self.state['message']=message

    async def start(self,value):
        if self.task and not self.task.done():raise ValueError('Jeden párovací pokus už běží.')
        if not isinstance(value,dict):raise ValueError('Neplatný vstup.')
        # Verify before Bluetooth writes, even for the code-only branch.
        await asyncio.to_thread(lambda:prepare(self.cloud,self.cloud.profile()))
        use_ble=value.get('use_ble',True)
        if use_ble:
            from .ble import validate_wifi
            validate_wifi(value.get('ssid'),value.get('password'))
            from .cloud import re
            if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value.get('address','')):
                raise ValueError('Zadej Bluetooth MAC adresu hrnce.')
        self.approved.clear();self.cancelled.clear();self.page_available=False
        self.state={'phase':'starting','message':'Připravuji jeden pokus.','ready_sent':False,'finalize_sent':False}
        self.task=asyncio.create_task(self.run(dict(value)))

    async def run(self,value):
        connection=None;resources=None;events=asyncio.Queue(maxsize=100)
        try:
            prefix,body=await asyncio.to_thread(lambda:prepare(self.cloud,self.cloud.profile()))
            loop=asyncio.get_running_loop()
            connection,resources,_=await asyncio.to_thread(self.cloud.mqtt_connection,lambda **kwargs:None)
            from awscrt import mqtt
            def enqueue(topic,data):
                try:events.put_nowait((topic,data))
                except asyncio.QueueFull:pass
            def callback(**kwargs):
                if kwargs.get('retain') or len(kwargs.get('payload',b''))>65536:return
                try:
                    data=json.loads(kwargs['payload'])
                    if isinstance(data,dict):loop.call_soon_threadsafe(enqueue,kwargs['topic'],data)
                except (ValueError,KeyError):pass
            result=await asyncio.to_thread(lambda:connection.subscribe(prefix+'status',mqtt.QoS.AT_LEAST_ONCE,callback)[0].result(timeout=10))
            if result.get('qos') is None:raise RuntimeError('Výrobce odmítl odběr párování.')
            if value.get('use_ble',True):
                self.progress('Předávám Wi-Fi přes Bluetooth…','ble')
                await provision(value['address'],value['ssid'],value['password'],self.progress)
            value.clear()
            if self.cancelled.is_set():raise InterruptedError()
            self.page_available=True
            self.progress('Zadej nový kód z hrnce na stránce výrobce a zde potvrď přijetí.','await_code')
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                if self.cancelled.is_set():raise InterruptedError()
                if self.approved.is_set() and not self.state['ready_sent']:
                    fresh_prefix,body=await asyncio.to_thread(lambda:prepare(self.cloud,self.cloud.profile()))
                    if fresh_prefix!=prefix:raise ValueError('Účet se změnil.')
                    while not events.empty():events.get_nowait()
                    self.state['ready_sent']=True
                    payload={k:body[k] for k in ('deviceCode','market','lang','apiKey','appliance')}
                    await asyncio.to_thread(lambda:connection.publish(prefix+'ready',payload=json.dumps(payload),qos=mqtt.QoS.AT_MOST_ONCE)[0].result(timeout=10))
                    self.progress('Čekám na schválení výrobce…','ready');deadline=time.monotonic()+60
                try:topic,data=await asyncio.wait_for(events.get(),.5)
                except asyncio.TimeoutError:continue
                if not self.state['ready_sent'] or topic!=prefix+'status':continue
                if data.get('accountId') not in (None,'',body['deviceCode']) or data.get('thingType') not in (None,'','COO002'):continue
                if data.get('errorCode') or data.get('isError'):
                    self.state['error_code']=data.get('errorCode')
                    raise RuntimeError('Výrobce odmítl párování (kód '+str(data.get('errorCode',0))+').')
                if data.get('status')=='COMPLETED' and not self.state['finalize_sent']:
                    self.state['finalize_sent']=True
                    await asyncio.to_thread(lambda:connection.publish(prefix+'finalize',payload=json.dumps(body),qos=mqtt.QoS.AT_MOST_ONCE)[0].result(timeout=10))
                    self.progress('Dokončuji přiřazení…','finalize');deadline=time.monotonic()+45
                if data.get('status')=='FINALIZED' and self.state['finalize_sent']:break
            devices=[]
            for attempt in range(3):
                devices=await asyncio.to_thread(self.cloud.devices)
                if devices:break
                await asyncio.sleep(2)
            if not devices:raise RuntimeError('Skutečná IoT vazba nebyla potvrzená. Pokus se automaticky neopakuje.')
            self.progress('Hrnec je přiřazený a IoT vazba ověřená.','finished');self.on_done()
        except InterruptedError:self.progress('Čekání ukončeno. Původní cloudová adresa zůstává.','cancelled')
        except asyncio.CancelledError:raise
        except Exception as error:
            # Our errors are bounded text; external errors may contain URLs.
            self.state['error_class']=type(error).__name__
            self.progress(str(error) if type(error) in (ValueError,RuntimeError) else 'Párování skončilo chybou '+type(error).__name__+'.','error')
        finally:
            value.clear();self.page_available=False
            if connection:
                try:await asyncio.to_thread(lambda:connection.disconnect().result(timeout=5))
                except Exception:pass

    async def stop(self):
        self.cancelled.set()
        if self.task and not self.task.done():
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
