"""Home Assistant MQTT discovery for real cooker telemetry."""
import json
import re
import secrets
import threading

FIELDS=(('status','Stav vaření',None,None),('mode','Režim',None,None),
        ('program','Program',None,None),('recipe','Recept',None,None),
        ('remaining','Zbývající čas','s','duration'),('elapsed','Uplynulý čas','s','duration'),
        ('progress','Průběh','%',None),('temperature','Cílová teplota','°C','temperature'),
        ('step','Krok receptu',None,None),('firmware','Firmware',None,None),
        ('error','Chyba',None,None))


def discovery(device):
    identifier=device['id']
    if not re.fullmatch(r'[a-f0-9-]{36}',identifier):raise ValueError('Neplatné zařízení.')
    node='cookeo_'+identifier.replace('-','')
    base='cookeo_bridge/'+identifier
    info={'identifiers':[base],'name':device['name'],'manufacturer':'Groupe SEB',
          'model':device['cmmf'] or device['thing_type']}
    out={}
    for key,name,unit,kind in FIELDS:
        config={'name':name,'unique_id':node+'_'+key,'device':info,'state_topic':base+'/state',
                'value_template':'{{ value_json.'+key+' if value_json.'+key+' is not none else none }}',
                'availability':[{'topic':'cookeo_bridge/availability'},{'topic':base+'/availability'}],
                'availability_mode':'all','origin':{'name':'Cookeo Bridge','sw_version':'0.4.1'}}
        if unit:config['unit_of_measurement']=unit
        if kind:config['device_class']=kind
        if key in ('firmware','error'):config['entity_category']='diagnostic'
        out['homeassistant/sensor/'+node+'/'+key+'/config']=config
    out['homeassistant/binary_sensor/'+node+'/connected/config']={
        'name':'Připojení hrnce','unique_id':node+'_connected','device':info,
        'state_topic':base+'/state','value_template':"{{ 'ON' if value_json.connected else 'OFF' }}",
        'availability_topic':'cookeo_bridge/availability','device_class':'connectivity'}
    return out


class Bridge:
    def __init__(self):
        self.client=None;self.connected=False;self.states={};self.devices={};self.lock=threading.RLock()

    def start(self,options):
        self.stop()
        if not options.get('host'):return
        import paho.mqtt.client as mqtt
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='cookeo-bridge-'+secrets.token_hex(4))
        if options.get('username'):client.username_pw_set(options['username'],options.get('password',''))
        if options.get('tls'):client.tls_set()
        client.will_set('cookeo_bridge/availability','offline',qos=1,retain=True)
        def connected(client,userdata,flags,code,properties):
            self.connected=not code.is_failure
            if self.connected:
                client.subscribe('homeassistant/status')
                self.announce()
        def message(client,userdata,msg):
            if msg.topic=='homeassistant/status' and msg.payload==b'online':self.announce()
        def disconnected(*args):self.connected=False
        client.on_connect=connected;client.on_message=message;client.on_disconnect=disconnected
        self.client=client
        client.connect_async(options['host'],int(options.get('port',1883)),30);client.loop_start()

    def announce(self):
        with self.lock:
            if not self.client:return
            self.client.publish('cookeo_bridge/availability','online',qos=1,retain=True)
            for device in self.devices.values():
                for topic,config in discovery(device).items():self.client.publish(topic,json.dumps(config),qos=1,retain=True)
            for identifier,value in self.states.items():self.publish(identifier,value)

    def register(self,devices):
        with self.lock:
            previous=self.devices;self.devices={v['id']:v for v in devices}
            if self.client:
                for identifier,device in previous.items():
                    if identifier not in self.devices:
                        for topic in discovery(device):self.client.publish(topic,b'',qos=1,retain=True)
                        self.client.publish('cookeo_bridge/'+identifier+'/availability','offline',qos=1,retain=True)
            self.states={k:v for k,v in self.states.items() if k in self.devices}
            if self.connected:self.announce()

    def publish(self,identifier,state):
        with self.lock:
            self.states[identifier]=dict(state)
            if not self.client or not self.connected:return
            base='cookeo_bridge/'+identifier
            self.client.publish(base+'/availability','online' if state.get('source_connected') and state.get('connected') else 'offline',qos=1,retain=True)
            self.client.publish(base+'/state',json.dumps(state,ensure_ascii=False),qos=1,retain=True)

    def stop(self):
        if self.client:
            try:self.client.publish('cookeo_bridge/availability','offline',qos=1,retain=True).wait_for_publish(timeout=2)
            except (RuntimeError,ValueError):pass
            self.client.disconnect();self.client.loop_stop();self.client=None
        self.connected=False
