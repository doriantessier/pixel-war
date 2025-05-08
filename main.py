from copy import deepcopy
import time
from uuid import uuid4
from fastapi import Cookie, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()

app.add_middleware(CORSMiddleware,
                   allow_origins=["*", "http://localhost:8000"],
                   allow_credentials=True
                   )

class UserInfo :
    last_edited_time_nanos: int
    last_seen_map: list[list[tuple[int,int,int]]]

    def __init__(self, carte):
        self.last_seen_map = deepcopy(carte)
        self.last_edited_time_nanos = 0


class Carte:
    keys: set[str]
    users: dict[str, UserInfo]
    nx: int
    ny: int
    data: list[list[tuple[int,int,int]]]
    timeout_nanos: int

    def __init__(self, nx: int, ny: int, timeout_nanos: int = 10e9):
        self.keys = set()
        self.nx = nx 
        self.ny = ny
        self.data = [
            [(0,0,0) for _ in range(ny)]
            for _ in range(nx)
        ]
        self.timeout_nanos = timeout_nanos
        self.users = dict[str, UserInfo]()
        
    
    def create_new_key(self):
        key = str(uuid4())
        self.keys.add(key)
        return key
    
    def is_valid_key(self, key: str):
        return key in self.keys
    
    def create_new_user_id(self: str):
        user_id = str(uuid4())
        self.users[user_id] = UserInfo(self.data)
        return user_id
    
    def is_valid_user_id(self, user_id:str):
        return user_id in self.users
    
    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, user_id: str):
        if not self.is_valid_user_id(user_id):
            return {"error": "ID utilisateur invalide"}
        now = time.time_ns()
        user_info = self.users[user_id]
        if now - user_info.last_edited_time_nanos < self.timeout_nanos:
            wait_s = int((self.timeout_nanos - (now - user_info.last_edited_time_nanos))/1e9)
            return {"error": f"Attends {wait_s} s avant de remettre un pixel"}
        self.data[x][y] = (r, g, b)
        user_info.last_edited_time_nanos = now
        return {"status": "ok", "x": x, "y": y, "color": (r, g, b)}


cartes: dict[str, Carte] = {"0000": Carte(nx = 10, ny = 10)}





@app.get("/api/v1/{nom_carte}/preinit")
async def preinit(nom_carte: str):
    if not nom_carte in cartes:
        return {'error': "Je n'ai pas trouvé la carte."}
   
    key = cartes[nom_carte].create_new_key()
    res = JSONResponse({"key": key})
    res.set_cookie("key", key, samesite="none", secure=True, max_age = 3600)
    return res



@app.get("/api/v1/{nom_carte}/init")
async def init(nom_carte: str, 
               query_key: str = Query(alias = "key"),
               cookie_key: str = Cookie(alias = "key")):
    carte = cartes[nom_carte]
    if not nom_carte in cartes:
        return {'error': "Je n'ai pas trouvé la nom_carte."}
    if query_key != cookie_key:
        return {'error': "Les clés ne correspondent pas"}
    if not carte.is_valid_key(cookie_key):
        return {"error":"La clé n'est pas valide"}
    
    user_id = carte.create_new_user_id()
    res = JSONResponse({"id": user_id,
            "nx": carte.nx,
            "ny": carte.ny,
            "data":carte.data}
            )
    res.set_cookie("user_id", user_id, samesite= 'none', secure=True, max_age = 3600)
    return res


@app.get("/api/v1/{nom_carte}/deltas")
async def deltas(nom_carte: str, 
               query_user_id: str = Query(alias = "id"),
               cookie_key: str = Cookie(alias = "key"),
               cookie_user_id: str = Cookie(alias = "id")):
    carte = cartes[nom_carte]
    if carte is None:
        return {'error': "Je n'ai pas trouvé la nom_carte."}
    if not carte.is_valid_key(cookie_key):
        return {"error":"La clé n'est pas valide"}
    if query_user_id != cookie_user_id:
        return {'error': "Les identifiants utilisateurs ne correspondent pas"}
    if not carte.is_valid_user_id(query_user_id):
        return {"error": "La clé n'est pas valide"}
    
    user_info = carte.users[query_user_id]
    user_carte = user_info.last_seen_map

    deltas: list[tuple[int,int,int,int,int]] = []
    for y in range(carte.ny):
        for x in range(carte.nx):
            if carte.data[x][y] != user_carte[x][y]:
                deltas.append((x, y, *carte.data[x][y]))
   
    user_info.last_seen_map = deepcopy(carte.data)

    return {
        "id" : query_user_id,
        "nx": carte.nx,
        "ny": carte.ny,
        "deltas": deltas
    }



@app.post("/api/v1/{nom_carte}/set_pixel")
async def set_pixel(nom_carte: str,
                    x: int = Query(...),
                    y: int = Query(...),
                    r: int = Query(...),
                    g: int = Query(...),
                    b: int = Query(...),
                    cookie_key: str = Cookie(alias="key"),
                    cookie_user_id: str = Cookie(alias="id")):
    
    if nom_carte not in cartes:
        return {"error" : "Je n'ai pas trouvé la carte"}
    
    carte = cartes[nom_carte]
    
    if not carte.is_valid_key(cookie_key):
        return {"error": "la clé n'est pas valide"}
    
    if not carte.is_valid_user_id(cookie_user_id):
        return {"error": "l'identifiant utilisateur n'est pas valide"}
    
    if not (0 <= x < carte.nx and 0 <= y < carte.ny):
        return {"error" : "les coordonnées ne sont pas sur la carte"}

    result = carte.set_pixel(x, y, r, g, b, user_id=cookie_user_id)

    if "error" in result:
        return {"error": result["error"]}

    return result