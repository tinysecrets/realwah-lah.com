const v:any=(typeof import.meta!=='undefined'&&(import.meta as any).env)||{};
const p:any=(typeof process!=='undefined'&&(process as any).env)||{};
export const BACKEND_URL=v.VITE_BACKEND_URL||v.REACT_APP_BACKEND_URL||p.REACT_APP_BACKEND_URL||'https://api.wah-lah.com';
