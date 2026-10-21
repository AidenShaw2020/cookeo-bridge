"""Encrypted account/settings storage and local recipe library."""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from cryptography.fernet import Fernet
from .recipes import normalize, migrate


class Store:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.RLock()
        path=self.folder/'storage.key'
        with self.state_lock():
            if not path.exists():
                with path.open('xb') as stream:stream.write(Fernet.generate_key())
                if os.name!='nt':path.chmod(0o600)
            self.cipher=Fernet(path.read_bytes())
        self.path=self.folder/'settings.enc'
        self.values=json.loads(self.cipher.decrypt(self.path.read_bytes())) if self.path.exists() else {}
        self.db=sqlite3.connect(self.folder/'recipes.sqlite3',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS recipes (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS recipe_notes (id TEXT PRIMARY KEY, note TEXT NOT NULL)')
        if not self.get('admin_token'):self.set('admin_token',secrets.token_urlsafe(32))

    @contextmanager
    def state_lock(self):
        with self.lock,(self.folder/'settings.lock').open('a+b') as stream:
            if stream.tell()==0:stream.write(b'0');stream.flush()
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
            try:yield
            finally:
                stream.seek(0)
                if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

    def get(self,key,default=None):
        with self.state_lock():
            if self.path.exists():self.values=json.loads(self.cipher.decrypt(self.path.read_bytes()))
            return json.loads(json.dumps(self.values.get(key,default)))

    def set(self,key,value):
        with self.state_lock():
            current=json.loads(self.cipher.decrypt(self.path.read_bytes())) if self.path.exists() else {}
            new={**current,key:value}
            temporary=self.path.with_suffix('.tmp')
            with temporary.open('wb') as stream:stream.write(self.cipher.encrypt(json.dumps(new).encode()))
            if os.name!='nt':temporary.chmod(0o600)
            temporary.replace(self.path);self.values=new

    def all_recipes(self):
        with self.lock:return [migrate(json.loads(row[0])) for row in self.db.execute('SELECT document FROM recipes ORDER BY rowid DESC')]

    def recipe(self,identifier):
        with self.lock:
            row=self.db.execute('SELECT document FROM recipes WHERE id=?',(identifier,)).fetchone()
            if not row:raise KeyError(identifier)
            return migrate(json.loads(row[0]))

    def put_recipe(self,value,identifier=None):
        recipe=normalize(value)
        with self.lock:
            if identifier:
                if str(uuid.UUID(identifier))!=identifier:raise ValueError('Neplatné ID.')
                if not self.db.execute('SELECT 1 FROM recipes WHERE id=?',(identifier,)).fetchone():raise KeyError(identifier)
            recipe['id']=identifier or str(uuid.uuid4())
            recipe['updated']=datetime.now(timezone.utc).isoformat()
            with self.db:self.db.execute('INSERT OR REPLACE INTO recipes VALUES (?,?)',
                                         (recipe['id'],json.dumps(recipe,ensure_ascii=False)))
        return recipe

    def delete_recipe(self,identifier):
        if str(uuid.UUID(identifier))!=identifier:raise ValueError('Neplatné ID.')
        with self.lock,self.db:
            if not self.db.execute('DELETE FROM recipes WHERE id=?',(identifier,)).rowcount:raise KeyError(identifier)

    def close(self):self.db.close()

    def recipe_note(self,key,note=None):
        with self.lock:
            if note is not None:
                if not isinstance(note,str) or len(note)>4000:raise ValueError('Personal notes must contain at most 4000 characters.')
                with self.db:self.db.execute('INSERT OR REPLACE INTO recipe_notes VALUES (?,?)',(key,note))
            row=self.db.execute('SELECT note FROM recipe_notes WHERE id=?',(key,)).fetchone()
            return row[0] if row else ''
