"""TEST ONLY: transparent proxy for native integration, NOT the actual WAF."""
import os
import httpx
from fastapi import FastAPI,Request,Response
app=FastAPI()
@app.api_route('/{path:path}',methods=['GET','POST'])
async def forward(path:str,request:Request):
    if path.startswith('auth/'): base=os.environ['AUTH_URL'];target=path[5:]
    elif path.startswith('api/'): base=os.environ['PAYMENT_URL'];target=path[4:]
    elif path=='ops/status':base=os.environ['REMEDIATOR_URL'];target='status'
    else:return Response(status_code=404)
    async with httpx.AsyncClient(trust_env=False,timeout=10) as c:
        r=await c.request(request.method,base+'/'+target,content=await request.body(),
                          headers={k:v for k,v in request.headers.items() if k.lower() in ('authorization','content-type','idempotency-key')})
    return Response(r.content,status_code=r.status_code,media_type='application/json')
