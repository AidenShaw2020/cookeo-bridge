"""Explicit CE9821F0 provisioning over local Bluetooth, original SEB host only."""
import asyncio
import base64
import hashlib
import json
import sys
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa

BASE='47656e65-7269-635f-4368-61725f'
INFO=BASE+'315f31';STATUS=BASE+'315f32';KEY=BASE+'325f41'
FAILURES={1120,1140,1160,1180,1210,1220,1240,1250,1260,1270,1310,1450,1460}


def validate_wifi(ssid,password):
    if not isinstance(ssid,str) or not 1<=len(ssid.encode())<=32:raise ValueError('Wi-Fi název musí mít 1–32 bajtů.')
    if not isinstance(password,str) or '\x00' in password or not (8<=len(password)<=63 or
       len(password)==64 and all(c in '0123456789abcdefABCDEF' for c in password)):
        raise ValueError('Pro WPA2 zadej heslo 8–63 znaků nebo 64 hexadecimálních číslic.')


def parse_key(raw):
    if len(raw)>8192:raise ValueError('Neplatný klíč hrnce.')
    der=base64.b64decode(json.loads(raw)['public_key'],validate=True)
    key=serialization.load_der_public_key(der)
    if not isinstance(key,rsa.RSAPublicKey) or key.key_size<2048:raise ValueError('Neplatný RSA klíč.')
    return key,hashlib.sha256(der).hexdigest()


async def provision(address,ssid,password,progress):
    from bleak import BleakClient,BleakScanner
    validate_wifi(ssid,password)
    found={}
    def callback(device,advertisement):
        if device.address.upper()==address.upper():found['device']=device
    progress('Hledám hrnec přes Bluetooth…')
    async with BleakScanner(detection_callback=callback,scanning_mode='passive' if sys.platform=='win32' else 'active'):
        await asyncio.sleep(8)
    if not found:raise RuntimeError('Hrnec není vidět. Zapni párování a zkontroluj Bluetooth serveru.')
    async with BleakClient(found['device'],timeout=20) as client:
        info=json.loads(bytes(await client.read_gatt_char(INFO)))['info']
        if str(info.get('CMMF'))!='7211419888':raise ValueError('Bluetooth zařízení není ověřený model CE9821F0.')
        key,fingerprint=parse_key(bytes(await client.read_gatt_char(KEY)))
        states=[];enabled=[]
        def capture(raw):
            try:
                value=json.loads(bytes(raw)).get('device_st')
                if type(value) is int:
                    if not states or states[-1]!=value:progress('Stav hrnce '+str(value))
                    states.append(value)
            except (ValueError,TypeError):pass
        async def wait(wanted,start,seconds):
            deadline=asyncio.get_running_loop().time()+seconds
            while asyncio.get_running_loop().time()<deadline:
                for state in states[start:]:
                    if state==wanted:return
                    if state in FAILURES:raise RuntimeError('Hrnec vrátil '+str(state))
                start=len(states)
                capture(await asyncio.wait_for(client.read_gatt_char(STATUS),12))
                await asyncio.sleep(.25)
            raise RuntimeError('Vypršel čas čekání na stav '+str(wanted))
        try:
            for char in (STATUS,BASE+'315f33'):
                await asyncio.wait_for(client.start_notify(char,lambda sender,data:capture(data)),12);enabled.append(char)
            _,again=parse_key(bytes(await client.read_gatt_char(KEY)))
            if fingerprint!=again:raise ValueError('Klíč hrnce se změnil; žádný zápis se neprovede.')
            start=len(states)
            await client.write_gatt_char(BASE+'325f42',b'{"abort_pairing":"OK"}',response=True)
            await wait(1040,start,30)
            encrypted=base64.b64encode(key.encrypt(json.dumps({'password':password},separators=(',',':'),ensure_ascii=False).encode(),
                padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)))
            start=len(states)
            await client.write_gatt_char(BASE+'325f32',json.dumps({'ssid':ssid},ensure_ascii=False,separators=(',',':')).encode(),response=True)
            await client.write_gatt_char(BASE+'325f33',encrypted,response=True)
            await wait(1130,start,45)
            start=len(states)
            await client.write_gatt_char(BASE+'325f34',b'{"host_name":"sebplatform.api.groupe-seb.com"}',response=True)
            await wait(1380,start,90)
            return {'broker_confirmed':True,'cmmf':'7211419888'}
        finally:
            for char in enabled:
                try:await asyncio.wait_for(client.stop_notify(char),5)
                except Exception:pass
