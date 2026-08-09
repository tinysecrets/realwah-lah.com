#!/usr/bin/env bash
set -euo pipefail
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
say(){ echo -e "${G}▶ $*${N}"; }; warn(){ echo -e "${Y}! $*${N}"; }; die(){ echo -e "${R}✖ $*${N}"; exit 1; }
need(){ command -v "$1" >/dev/null || die "missing dep: $1"; }
for t in curl jq git python3; do need "$t"; done
[ -d backend ] && [ -d frontend ] || die "run from repo root of realwah-lah.com"

prompt(){ local v; read -rp "$1: " v; echo "$v"; }
promptS(){ local v; read -rsp "$1: " v; echo >&2; echo "$v"; }
: "${RENDER_API_KEY:=$(promptS 'Render API key (rnd_...)')}"
: "${CLOUDFLARE_API_TOKEN:=$(promptS 'Cloudflare API token')}"
: "${CLOUDFLARE_ZONE_ID:=$(prompt  'Cloudflare Zone ID')}"
: "${MONGO_URL:=$(promptS 'MongoDB Atlas connection string')}"
: "${RESEND_API_KEY:=$(promptS 'Resend API key (enter to skip)')}"
: "${CEREBRAS_API_KEY:=$(promptS 'Cerebras API key (enter to skip)')}"
: "${CASHAPP_TAG:=REDACTED}"
: "${CHIME_TAG:=REDACTED}"
: "${LIGHTNING_ADDRESS:=$(prompt 'Lightning address (enter to skip)')}"

RH=(-H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" -H "Accept: application/json")
CH=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")
REPO_URL=$(git config --get remote.origin.url | sed 's/git@github.com:/https:\/\/github.com\//;s/\.git$//')

say "1/10 Cleanup"
rm -f fly.toml wrangler.toml Inside What cashier_api.py cashier_connect.js
rm -f scripts/deploy-all.sh scripts/deploy-secrets.sh scripts/verify-wahlah-domain.sh 2>/dev/null || true
sed -i.bak -E '/fly\.io|flyctl|fly deploy|stripe/Id' README.md 2>/dev/null || true
sed -i.bak -E '/^stripe/Id' backend/requirements.txt 2>/dev/null || true
rm -f README.md.bak backend/requirements.txt.bak

say "2/10 render.yaml"
cat > render.yaml << 'YAML'
services:
  - type: web
    name: wah-lah-api
    runtime: python
    plan: free
    region: oregon
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
  - type: web
    name: wah-lah-genie
    runtime: python
    plan: free
    region: oregon
    rootDir: genie-sidekick/backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
  - type: web
    name: wah-lah-web
    runtime: static
    rootDir: frontend
    buildCommand: yarn install --frozen-lockfile && yarn build
    staticPublishPath: ./build
    routes:
      - { type: rewrite, source: /*, destination: /index.html }
YAML

say "3/10 Backend patches"
CASHAPP_TAG="$CASHAPP_TAG" CHIME_TAG="$CHIME_TAG" LIGHTNING_ADDRESS="$LIGHTNING_ADDRESS" python3 << 'PY'
import os
from pathlib import Path
p = Path("backend/server.py")
s = p.read_text() if p.exists() else "from fastapi import FastAPI\napp = FastAPI()\n"
cashapp = os.environ["CASHAPP_TAG"]; chime = os.environ["CHIME_TAG"]; ln = os.environ.get("LIGHTNING_ADDRESS","")
if "CORS_ORIGINS" not in s:
    s += ("\nimport os as _os\nfrom fastapi.middleware.cors import CORSMiddleware as _CM\n"
          "_o=[x.strip() for x in _os.getenv('CORS_ORIGINS','https://wah-lah.com,https://www.wah-lah.com').split(',') if x.strip()]\n"
          "try: app.add_middleware(_CM, allow_origins=_o, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])\n"
          "except Exception: pass\n")
if "/api/health" not in s:
    s += "\n@app.get('/api/health')\ndef _health(): return {'status':'ok','service':'wah-lah'}\n"
if "/api/pay/cashapp" not in s:
    s += (f"\n@app.get('/api/pay/cashapp')\ndef _pcash(amount: float = 0):\n"
          f"    return {{'method':'cashapp','tag':'{cashapp}','url': f'https://cash.app/${cashapp}/{{amount}}' if amount>0 else 'https://cash.app/${cashapp}'}}\n"
          f"\n@app.get('/api/pay/chime')\ndef _pchime(): return {{'method':'chime','tag':'{chime}','instructions':'Chime > Pay Anyone > send to ${chime}'}}\n"
          f"\n@app.get('/api/pay/lightning')\ndef _pln(amount: float = 0):\n"
          f"    a='{ln}'\n    return {{'method':'lightning','address':a,'enabled':bool(a),'amount_sats':amount}}\n"
          f"\n@app.get('/api/pay')\ndef _pall(): return {{'cashapp':{{'tag':'{cashapp}','url':'https://cash.app/${cashapp}'}},'chime':{{'tag':'{chime}'}},'lightning':{{'address':'{ln}','enabled':bool('{ln}')}}}}\n")
p.write_text(s); print("backend patched")
PY

say "4/10 Frontend"
mkdir -p frontend/src/components
cat > frontend/src/config.ts << 'TS'
const v:any=(typeof import.meta!=='undefined'&&(import.meta as any).env)||{};
const p:any=(typeof process!=='undefined'&&(process as any).env)||{};
export const BACKEND_URL=v.VITE_BACKEND_URL||v.REACT_APP_BACKEND_URL||p.REACT_APP_BACKEND_URL||'https://api.wah-lah.com';
TS
cat > frontend/.env.production << 'ENV'
REACT_APP_BACKEND_URL=https://api.wah-lah.com
VITE_BACKEND_URL=https://api.wah-lah.com
ENV
cat > frontend/src/components/PayPicker.tsx << 'TSX'
import React, {useEffect, useState} from 'react';
import {BACKEND_URL} from '../config';
export default function PayPicker({amount=0}:{amount?:number}){
  const [d,setD]=useState<any>(null);
  useEffect(()=>{fetch(`${BACKEND_URL}/api/pay`).then(r=>r.json()).then(setD).catch(()=>{});},[]);
  if(!d) return <div>Loading payment options…</div>;
  const btn:React.CSSProperties={padding:'12px 16px',border:'1px solid #333',borderRadius:8,textDecoration:'none',color:'#fff',background:'#111',cursor:'pointer',textAlign:'center'};
  return (<div style={{display:'grid',gap:12,padding:16}}>
    <a href={`${d.cashapp.url}/${amount||''}`} target="_blank" rel="noreferrer" style={btn}>Pay with Cash App (${d.cashapp.tag})</a>
    <button onClick={()=>navigator.clipboard.writeText(d.chime.tag)} style={btn}>Pay with Chime — copy ${d.chime.tag}</button>
    {d.lightning.enabled ? <a href={`lightning:${d.lightning.address}`} style={btn}>Bitcoin Lightning ⚡ {d.lightning.address}</a> : <div style={{opacity:.6}}>Bitcoin Lightning coming soon</div>}
  </div>);
}
TSX

say "5/10 GH Actions"
mkdir -p .github/workflows
cat > .github/workflows/deploy.yml << 'YML'
name: Deploy WAH-LAH
on: { push: { branches: [main] } }
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: api
        if: ${{ secrets.RENDER_DEPLOY_HOOK_API != '' }}
        run: curl -fsSL -X POST "${{ secrets.RENDER_DEPLOY_HOOK_API }}"
      - name: genie
        if: ${{ secrets.RENDER_DEPLOY_HOOK_GENIE != '' }}
        run: curl -fsSL -X POST "${{ secrets.RENDER_DEPLOY_HOOK_GENIE }}"
      - name: web
        if: ${{ secrets.RENDER_DEPLOY_HOOK_WEB != '' }}
        run: curl -fsSL -X POST "${{ secrets.RENDER_DEPLOY_HOOK_WEB }}"
YML

say "6/10 Commit + push"
git add -A
git commit -m "chore: ship-ready — Render+CF+Atlas, CashApp+Chime+Lightning" || warn "nothing to commit"
git push origin HEAD || warn "push skipped"

say "7/10 Provision Render services"
OWNER_ID=$(curl -fsSL "${RH[@]}" https://api.render.com/v1/owners | jq -r '.[0].owner.id')
[ -n "$OWNER_ID" ] || die "Render auth failed"

create_svc(){
  local name=$1 type=$2 root=$3 build=$4 start=${5:-} envs=$6 id body
  id=$(curl -fsSL "${RH[@]}" "https://api.render.com/v1/services?name=$name" | jq -r '.[0].service.id // empty')
  if [ -z "$id" ]; then
    if [ "$type" = "static_site" ]; then
      body=$(jq -n --arg n "$name" --arg r "$root" --arg b "$build" --arg o "$OWNER_ID" --arg u "$REPO_URL" --argjson e "$envs" '{type:"static_site",name:$n,ownerId:$o,repo:$u,branch:"main",rootDir:$r,serviceDetails:{buildCommand:$b,publishPath:"./build",envVars:$e,routes:[{type:"rewrite",source:"/*",destination:"/index.html"}]}}')
    else
      body=$(jq -n --arg n "$name" --arg r "$root" --arg b "$build" --arg s "$start" --arg o "$OWNER_ID" --arg u "$REPO_URL" --argjson e "$envs" '{type:"web_service",name:$n,ownerId:$o,repo:$u,branch:"main",rootDir:$r,serviceDetails:{env:"python",plan:"free",region:"oregon",buildCommand:$b,startCommand:$s,healthCheckPath:"/api/health",envVars:$e}}')
    fi
    id=$(curl -fsSL "${RH[@]}" -X POST -d "$body" https://api.render.com/v1/services | jq -r '.service.id // empty')
    [ -n "$id" ] || die "Render service create failed: $name"
  fi
  echo "$id"
}

API_ENVS=$(jq -n --arg m "$MONGO_URL" --arg r "$RESEND_API_KEY" --arg c "$CEREBRAS_API_KEY" '[{key:"PYTHON_VERSION",value:"3.11.9"},{key:"MONGO_URL",value:$m},{key:"DB_NAME",value:"wahlah"},{key:"CORS_ORIGINS",value:"https://wah-lah.com,https://www.wah-lah.com"},{key:"RESEND_API_KEY",value:$r},{key:"CEREBRAS_API_KEY",value:$c}]')
GENIE_ENVS=$(jq -n --arg m "$MONGO_URL" '[{key:"PYTHON_VERSION",value:"3.11.9"},{key:"MONGO_URL",value:$m},{key:"DB_NAME",value:"genie"}]')
WEB_ENVS=$(jq -n '[{key:"REACT_APP_BACKEND_URL",value:"https://api.wah-lah.com"},{key:"NODE_VERSION",value:"20"},{key:"CI",value:"false"}]')

API_ID=$(create_svc   wah-lah-api    web_service backend                "pip install -r requirements.txt" "uvicorn server:app --host 0.0.0.0 --port \$PORT" "$API_ENVS")
GENIE_ID=$(create_svc wah-lah-genie  web_service genie-sidekick/backend "pip install -r requirements.txt" "uvicorn server:app --host 0.0.0.0 --port \$PORT" "$GENIE_ENVS")
WEB_ID=$(create_svc   wah-lah-web    static_site frontend               "yarn install --frozen-lockfile && yarn build" "" "$WEB_ENVS")

say "8/10 Custom domains"
attach(){ curl -fsSL "${RH[@]}" -X POST -d "{\"name\":\"$2\"}" "https://api.render.com/v1/services/$1/custom-domains" >/dev/null 2>&1 || true; }
attach "$WEB_ID"   "wah-lah.com"
attach "$WEB_ID"   "www.wah-lah.com"
attach "$API_ID"   "api.wah-lah.com"
attach "$GENIE_ID" "genie.wah-lah.com"

say "9/10 Cloudflare DNS"
dns(){
  local name=$1 target=$2 existing body
  existing=$(curl -fsSL "${CH[@]}" "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records?name=$name" | jq -r '.result[0].id // empty')
  body="{\"type\":\"CNAME\",\"name\":\"$name\",\"content\":\"$target\",\"proxied\":false,\"ttl\":1}"
  if [ -n "$existing" ]; then
    curl -fsSL "${CH[@]}" -X PUT  -d "$body" "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records/$existing" >/dev/null
  else
    curl -fsSL "${CH[@]}" -X POST -d "$body" "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records" >/dev/null
  fi
}
dns wah-lah.com       wah-lah-web.onrender.com
dns www.wah-lah.com   wah-lah-web.onrender.com
dns api.wah-lah.com   wah-lah-api.onrender.com
dns genie.wah-lah.com wah-lah-genie.onrender.com

say "10/10 Trigger deploys"
for id in "$API_ID" "$GENIE_ID" "$WEB_ID"; do
  curl -fsSL "${RH[@]}" -X POST "https://api.render.com/v1/services/$id/deploys" >/dev/null || true
done

echo
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo -e "${G}✓ WAH-LAH is shipping.${N}"
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo "  Frontend:  https://wah-lah.com          (Render: $WEB_ID)"
echo "  API:       https://api.wah-lah.com      (Render: $API_ID)"
echo "  Genie:     https://genie.wah-lah.com    (Render: $GENIE_ID)"
echo "  Payments:  Cash App \$$CASHAPP_TAG · Chime \$$CHIME_TAG · Lightning ${LIGHTNING_ADDRESS:-'(disabled)'}"
echo
echo "  Build ETA: 5-8 min. SSL: 2-5 min after DNS resolves."
echo "  Verify:    curl https://api.wah-lah.com/api/health"
