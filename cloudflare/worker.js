export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/config') {
      return Response.json({ supabaseUrl: env.SUPABASE_URL, supabaseAnonKey: env.SUPABASE_ANON_KEY }, { headers: { 'Cache-Control': 'no-store' } });
    }
    if (url.pathname.startsWith('/api/')) {
      if (!env.FASTAPI_URL) return Response.json({ error: 'FASTAPI_URL is not configured' }, { status: 503 });
      const target = new URL(url.pathname + url.search, env.FASTAPI_URL.replace(/\/$/, '') + '/');
      const headers = new Headers(request.headers);
      headers.delete('host');
      return fetch(new Request(target, { method: request.method, headers, body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body }));
    }
    return env.ASSETS.fetch(request);
  }
};
