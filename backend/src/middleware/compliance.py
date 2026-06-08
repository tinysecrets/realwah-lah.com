from fastapi import Request, HTTPException
from geoip2.database import Reader
def verify_region(request: Request):
    ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.client.host
    with Reader('assets/GeoLite2-City.mmdb') as reader:
        try:
            response = reader.city(ip)
            if response.subdivisions.most_specific.iso_code in ['NV', 'WA', 'ID']:
                raise HTTPException(status_code=403, detail="Region blocked")
        except: pass
