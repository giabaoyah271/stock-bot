"""DS01 immutable private objects + atomic PostgreSQL head; no trading logic."""
import hashlib
import json
import re
import urllib.request
import urllib.error
import urllib.parse
import uuid
from dataclasses import dataclass

MAX_OBJECT=47*1024*1024
KINDS=("reference","paper","scan","single","preferences")
BUCKET="stock-bot-private"

class StorageError(Exception):
    pass
class Conflict(StorageError):
    pass
class Missing(StorageError):
    pass

def sha(data):
    return hashlib.sha256(data).hexdigest()

def json_bytes(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":"),sort_keys=True).encode("utf-8")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

@dataclass(frozen=True,repr=False)
class Config:
    url: str
    anon_key: str
    service_role_key: str
    owner_id: str
    namespace: str
    market_storage_allowed: bool=False
    def __post_init__(self):
        if not re.fullmatch(r"https://[a-z0-9]+\.supabase\.co",self.url):
            raise StorageError("Project URL Supabase không hợp lệ")
        if not re.fullmatch(r"[a-z0-9-]{1,40}",self.namespace):
            raise StorageError("Namespace không hợp lệ")
        try: uuid.UUID(self.owner_id)
        except (ValueError,AttributeError): raise StorageError("Owner UUID không hợp lệ") from None
        if not self.anon_key or not self.service_role_key or self.anon_key==self.service_role_key:
            raise StorageError("Thiếu khóa máy chủ hoặc khóa Auth")
        if type(self.market_storage_allowed) is not bool:
            raise StorageError("market_storage_allowed phải là boolean")

class SupabaseBackend:
    def __init__(self,config):
        self.c=config
        self.opener=urllib.request.build_opener(NoRedirect())
    def request(self,path,method="GET",data=None,content_type="application/json",auth=False,raw=False):
        key=self.c.anon_key if auth else self.c.service_role_key
        headers={"apikey":key,"Content-Type":content_type}
        if key.startswith("eyJ"): headers["Authorization"]="Bearer "+key
        req=urllib.request.Request(self.c.url+path,data=data,headers=headers,method=method)
        try:
            with self.opener.open(req,timeout=25) as response:
                result=response.read(MAX_OBJECT+1)
        except urllib.error.HTTPError as e:
            if e.code==404: raise Missing("Không tìm thấy dữ liệu Cloud") from None
            if e.code==400 and "/storage/v1/object/authenticated/" in path:
                try: body=json.loads(e.read(4096))
                except Exception: body={}
                if str(body.get("statusCode"))=="404" or body.get("error")=="not_found":
                    raise Missing("Không tìm thấy object") from None
            if e.code in (409,): raise Conflict("Object đã tồn tại hoặc xung đột") from None
            raise StorageError("Supabase HTTP "+str(e.code)) from None
        except (OSError,TimeoutError):
            raise StorageError("Không kết nối được Supabase") from None
        if len(result)>MAX_OBJECT: raise StorageError("Object vượt giới hạn")
        if raw: return result
        try: return json.loads(result) if result else None
        except (UnicodeError,ValueError): raise StorageError("Phản hồi Supabase không hợp lệ") from None
    def authenticate(self,email,password):
        r=self.request("/auth/v1/token?grant_type=password","POST",json_bytes({"email":email,"password":password}),auth=True)
        if not isinstance(r,dict) or r.get("user",{}).get("id")!=self.c.owner_id:
            raise StorageError("Không đúng tài khoản chủ sở hữu")
    def check(self):
        r=self.request("/storage/v1/bucket/"+BUCKET)
        if not isinstance(r,dict) or r.get("public") is not False:
            raise StorageError("Bucket chưa được xác minh Private")
        self.head("paper")
    def usage(self):
        r=self.request("/rest/v1/rpc/ds01_usage","POST",json_bytes({"p_namespace":self.c.namespace}))
        if type(r) is not int or r<0: raise StorageError("Không đọc được dung lượng")
        return r
    def log(self,kind,result):
        self.request("/rest/v1/ds01_sync_logs","POST",json_bytes({"namespace":self.c.namespace,"kind":kind,"result":result}))
    def logs(self):
        return self.query("ds01_sync_logs",select="kind,result,created_at",order="id.desc",limit="20")
    def path(self,kind,digest):
        if kind not in KINDS or not re.fullmatch(r"[0-9a-f]{64}",digest): raise StorageError("Object path không hợp lệ")
        return "/storage/v1/object/"+BUCKET+"/"+self.c.namespace+"/"+kind+"/"+digest
    def download(self,kind,digest):
        path=self.path(kind,digest).replace("/object/","/object/authenticated/",1)
        return self.request(path,raw=True)
    def upload(self,kind,digest,data):
        self.request(self.path(kind,digest),"POST",data,"application/octet-stream")
    def query(self,table,**params):
        return self.request("/rest/v1/"+table+"?"+urllib.parse.urlencode({"namespace":"eq."+self.c.namespace,**params}))
    def head(self,kind):
        r=self.query("ds01_heads",kind="eq."+kind,select="version")
        if not isinstance(r,list) or len(r)>1: raise StorageError("Head không hợp lệ")
        return int(r[0]["version"]) if r else 0
    def version(self,kind,version):
        r=self.query("ds01_versions",kind="eq."+kind,version="eq."+str(version),select="version,sha,size_bytes,created_at")
        if not isinstance(r,list) or len(r)!=1: raise StorageError("Metadata phiên bản không tồn tại")
        return r[0]
    def history(self,kind,limit=30):
        return self.query("ds01_versions",kind="eq."+kind,select="version,sha,size_bytes,created_at",order="version.desc",limit=str(limit))
    def commit(self,kind,expected,digest,size):
        r=self.request("/rest/v1/rpc/ds01_commit","POST",json_bytes({"p_namespace":self.c.namespace,"p_kind":kind,"p_expected":expected,"p_sha":digest,"p_size":size}))
        if type(r) is not int: raise StorageError("RPC không trả phiên bản")
        return r

class Repository:
    def __init__(self,backend):
        self.b=backend
    def load(self,kind,version=None):
        if kind not in KINDS: raise StorageError("Loại dữ liệu không hợp lệ")
        v=self.b.head(kind) if version is None else version
        if not v: return 0,None
        m=self.b.version(kind,v)
        data=self.b.download(kind,m["sha"])
        if len(data)!=m["size_bytes"] or sha(data)!=m["sha"]: raise StorageError("Checksum Cloud không khớp")
        return v,data
    def save(self,kind,data,expected):
        if kind not in KINDS or not isinstance(data,bytes) or not 0<len(data)<=MAX_OBJECT:
            raise StorageError("Dữ liệu rỗng hoặc vượt giới hạn 47 MiB")
        if type(expected) is not int or expected<0: raise StorageError("Thiếu phiên bản dự kiến")
        digest=sha(data)
        current=self.b.head(kind)
        if current:
            m=self.b.version(kind,current)
            if m["sha"]==digest:
                self.load(kind,current)
                return current
        if current!=expected: raise Conflict("Dữ liệu Cloud đã thay đổi; tải lại trước khi ghi")
        try:
            existing=self.b.download(kind,digest)
        except Missing:
            try: self.b.upload(kind,digest,data)
            except (StorageError,Conflict):
                # A timed-out request may already have uploaded immutable bytes.
                pass
            existing=self.b.download(kind,digest)
        if sha(existing)!=digest or len(existing)!=len(data):
            raise StorageError("Không xác minh được object sau upload")
        try: v=self.b.commit(kind,expected,digest,len(data))
        except StorageError:
            # Resolve an ambiguous commit only if the exact object is current.
            v=self.b.head(kind)
            if not v or self.b.version(kind,v)["sha"]!=digest:
                raise StorageError("Chưa xác nhận được commit; tải lại trước khi thử") from None
        if v<1: raise Conflict("Xung đột phiên bản; tải lại trước khi ghi")
        return v
